#!/usr/bin/env python3
"""
alerter.py — Prévient quand une bonne session se profile, en surf ou en wing.

Lit `docs/data.json` et compare à ce qui a déjà été annoncé, conservé dans
`etat_alertes.json`. Quatre sortes de messages :

  - NOUVEAU    une journée passe au-dessus du seuil ;
  - MIEUX      une session déjà annoncée s'améliore nettement ;
  - ANNULÉ     une session annoncée retombe sous le seuil ;
  - MAINTENANT une bonne session commence dans les trois heures, en tenant
               compte du temps de trajet jusqu'au spot.

On raisonne par session de deux heures et par journée : une seule ligne par
spot, discipline et jour, pour que la notification reste lisible sur un
écran verrouillé.

Le message part sur la sortie standard (vide s'il n'y a rien), et le fichier
`priorite.txt` indique au workflow s'il faut sonner plus fort.

Usage :
    python alerter.py --seuil 3 --seuil-wing 3
    python alerter.py --essai        # affiche sans rien mémoriser
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _ZONE = ZoneInfo("Europe/Paris")
except Exception:
    _ZONE = None

RACINE = Path(__file__).parent
DONNEES = RACINE / "docs" / "data.json"
ETAT = RACINE / "etat_alertes.json"
ETAT_MAREE = RACINE / "etat_maree.json"       # tenu par verif_maree.py
PRIORITE = RACINE / "priorite.txt"

HAUSSE_NOTABLE = 0.75     # gain qui justifie une nouvelle alerte
MARGE_ANNULATION = 0.5    # sous seuil - marge, une session annoncée est annulée
HORIZON_IMMEDIAT_H = 3    # « c'est bon maintenant » : départ dans ce délai

# « Bonne surprise » : la bouée d'Ambleteuse mesure des conditions très
# favorables que la prévision n'avait pas vues.
SEUIL_SURPRISE = 3.5      # note surf de la mesure à partir de laquelle on prévient
ECART_SURPRISE = 1.0      # avance minimale de la mesure sur la prévision
AGE_MAX_MESURE_H = 2      # une mesure plus vieille n'est plus « maintenant »
PAUSE_SURPRISE_H = 6      # pas de nouvelle alerte surprise avant ce délai

# Disciplines qui déclenchent une notification. La wing reste notée sur la
# page, mais ne prévient plus. Pour la réactiver, ajoute
# ("wing", "session_wing") à cette liste.
DISCIPLINES_ALERTE = (("surf", "session_surf"),)

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def maintenant() -> datetime:
    d = datetime.now(_ZONE) if _ZONE else datetime.now()
    return d.replace(tzinfo=None)


def charger_etat() -> dict:
    try:
        etat = json.loads(ETAT.read_text(encoding="utf-8"))
        if isinstance(etat, dict):
            etat.setdefault("annonces", {})
            etat.setdefault("immediats", [])
            etat.setdefault("surprise", None)
            return etat
    except Exception:
        pass
    # Ancien format (simple liste) ou fichier absent : on repart de zéro.
    return {"annonces": {}, "immediats": [], "surprise": None}


def derniere_surprise(etat: dict) -> str | None:
    """
    Dernière alerte surprise, qu'elle vienne du calcul toutes les trois heures
    (etat_alertes.json) ou du contrôle aux pleines mers (etat_maree.json) :
    la pause vaut pour les deux, jamais deux alertes pour le même épisode.
    """
    dates = [etat.get("surprise")]
    try:
        dates.append(json.loads(ETAT_MAREE.read_text(encoding="utf-8")).get("surprise"))
    except Exception:
        pass
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def message_surprise(b, ref, derniere, seuil=SEUIL_SURPRISE,
                     ecart=ECART_SURPRISE, contexte="") -> str | None:
    """
    Le texte de l'alerte si la mesure de la bouée est une bonne surprise
    (récente, bien notée, nettement au-dessus de la prévision, hors pause),
    sinon None.
    """
    b = b or {}
    if b.get("note_mesuree") is None or b.get("note_prevue") is None:
        return None
    mesure = datetime.fromisoformat(b["instant"])
    if mesure.tzinfo and _ZONE:
        mesure = mesure.astimezone(_ZONE)
    mesure = mesure.replace(tzinfo=None)
    en_pause = bool(derniere) and (
        ref - datetime.fromisoformat(derniere) < timedelta(hours=PAUSE_SURPRISE_H))
    if (ref - mesure > timedelta(hours=AGE_MAX_MESURE_H)
            or b["note_mesuree"] < seuil
            or b["note_mesuree"] - b["note_prevue"] < ecart
            or en_pause):
        return None
    v = lambda x, d=1: f"{x:.{d}f}".replace(".", ",")
    bouee = ("la bouée de Hastings (relais, Ambleteuse muette)"
             if b.get("nom") == "Hastings" else "la bouée d'Ambleteuse")
    return (f"SURPRISE Wimereux{contexte} : {bouee} mesure "
            f"{v(b['hauteur_m'], 2)} m à {v(b['periode_pic_s'])} s ({mesure:%Hh%M}), "
            f"note {v(b['note_mesuree'])}/5 contre {v(b['note_prevue'])} prévue. "
            f"C'est maintenant.")


def mesure_a_juger(ambleteuse, hastings, ref):
    """
    Ambleteuse si elle a une mesure notée et récente ; sinon Hastings en
    relais, qui n'est noté que par houle de sud-ouest.
    """
    for b in (ambleteuse, hastings):
        if not b or b.get("note_mesuree") is None or b.get("note_prevue") is None:
            continue
        mesure = datetime.fromisoformat(b["instant"])
        if mesure.tzinfo and _ZONE:
            mesure = mesure.astimezone(_ZONE)
        if ref - mesure.replace(tzinfo=None) <= timedelta(hours=AGE_MAX_MESURE_H):
            return b
    return None


def meilleures_sessions(spot, attr, depart_min):
    """Meilleure session de chaque jour, parmi celles qui commencent assez tard."""
    par_jour = {}
    for c in spot.get("creneaux", []):
        note = c.get(attr)
        if note is None:
            continue
        debut = datetime.fromisoformat(c["instant"])
        if debut < depart_min:
            continue
        jour = debut.date().isoformat()
        if jour not in par_jour or note > par_jour[jour][0]:
            par_jour[jour] = (note, debut, c)
    return par_jour


def ligne(etiquette, nom, disc, debut, note, duree, c=None):
    fin = debut + timedelta(hours=duree)
    detail = ""
    if c is not None:
        if disc == "surf":
            detail = f"  {c['hauteur_m']:.1f} m à {c['tpeak_s']:.0f} s"
            pls = c.get("planches") or []
            if pls:
                detail += ", " + " ou ".join(
                    pl["nom"] + ("" if pl.get("possedee", True) else "*") for pl in pls)
            if c.get("equipement"):
                detail += ", " + c["equipement"]["combi"]
        else:
            detail = f"  {round(c['vitesse_kt'])}-{round(c['rafales_kt'])} nds"
            if c.get("aile_m2"):
                detail += f", aile {str(c['aile_m2']).replace('.', ',')} m²"
    return (f"{etiquette} {nom} {disc} {JOURS[debut.weekday()]} {debut.day} "
            f"{debut:%H}h-{fin:%H}h : {note:.1f}/5{detail}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seuil", type=float, default=3.0, help="seuil surf")
    p.add_argument("--seuil-wing", type=float, default=3.0, help="seuil wing")
    p.add_argument("--seuil-surprise", type=float, default=SEUIL_SURPRISE,
                   help="note mesurée à la bouée pour l'alerte surprise")
    p.add_argument("--ecart-surprise", type=float, default=ECART_SURPRISE,
                   help="avance minimale de la mesure sur la prévision")
    p.add_argument("--essai", action="store_true",
                   help="afficher sans mettre à jour l'état")
    args = p.parse_args()

    if not DONNEES.exists():
        print(f"{DONNEES} introuvable.", file=sys.stderr)
        return 1

    data = json.loads(DONNEES.read_text(encoding="utf-8"))
    etat = charger_etat()
    annonces = etat["annonces"]
    immediats = set(etat["immediats"])
    ref = maintenant()
    aujourd_hui = ref.date().isoformat()

    urgents, lignes = [], []
    seuils = {"surf": args.seuil, "wing": args.seuil_wing}

    for spot in data.get("spots", []):
        if not spot.get("creneaux"):
            continue
        nom = spot["nom"]
        duree = spot.get("duree_session_h", 2)
        depart_min = ref + timedelta(minutes=spot.get("trajet_min", 0))

        for disc, attr in DISCIPLINES_ALERTE:
            seuil = seuils[disc]
            sessions = meilleures_sessions(spot, attr, depart_min)

            # MAINTENANT : une bonne session démarre bientôt. Elle vaut aussi
            # annonce de la journée, pour ne pas la répéter en NOUVEAU.
            for jour, (note, debut, c) in sessions.items():
                if note >= seuil and debut <= ref + timedelta(hours=HORIZON_IMMEDIAT_H):
                    cle = f"{spot['cle']}|{disc}|{debut.isoformat()}"
                    if cle not in immediats:
                        urgents.append(ligne("MAINTENANT", nom, disc, debut,
                                             note, duree, c))
                        immediats.add(cle)
                        annonces.setdefault(f"{spot['cle']}|{disc}|{jour}",
                                            {"note": note, "debut": debut.isoformat()})

            # NOUVEAU / MIEUX
            for jour, (note, debut, c) in sorted(sessions.items()):
                cle = f"{spot['cle']}|{disc}|{jour}"
                deja = annonces.get(cle)
                if note >= seuil and deja is None:
                    lignes.append(ligne("NOUVEAU", nom, disc, debut, note, duree, c))
                    annonces[cle] = {"note": note, "debut": debut.isoformat()}
                elif deja is not None and note >= deja["note"] + HAUSSE_NOTABLE:
                    lignes.append(ligne("MIEUX", nom, disc, debut, note, duree, c)
                                  + f" (était {deja['note']:.1f})")
                    annonces[cle] = {"note": note, "debut": debut.isoformat()}

            # ANNULÉ : annoncé, encore à venir, mais retombé.
            for cle, deja in list(annonces.items()):
                s_cle, s_disc, jour = cle.split("|")
                if s_cle != spot["cle"] or s_disc != disc or jour < aujourd_hui:
                    continue
                if datetime.fromisoformat(deja["debut"]) < ref:
                    continue
                actuel = sessions.get(jour)
                if actuel is None or actuel[0] < seuil - MARGE_ANNULATION:
                    debut = datetime.fromisoformat(deja["debut"])
                    note_act = actuel[0] if actuel else 0.0
                    lignes.append(ligne("ANNULÉ", nom, disc, debut, note_act, duree)
                                  + f" (était {deja['note']:.1f})")
                    del annonces[cle]

    # SURPRISE : la mesure réelle est très bonne et la prévision ne l'avait
    # pas vue. Une seule alerte par épisode, grâce à la pause.
    msg = message_surprise(mesure_a_juger(data.get("bouee_ambleteuse"),
                                          data.get("bouee_hastings"), ref), ref,
                           derniere_surprise(etat), args.seuil_surprise,
                           args.ecart_surprise)
    if msg:
        urgents.insert(0, msg)
        etat["surprise"] = ref.isoformat(timespec="minutes")

    # Ménage : on oublie ce qui est passé depuis plus d'un jour.
    hier = (ref - timedelta(days=1)).date().isoformat()
    annonces = {k: v for k, v in annonces.items() if k.split("|")[2] >= hier}
    immediats = {k for k in immediats
                 if datetime.fromisoformat(k.split("|")[2]) >= ref - timedelta(days=1)}

    if not args.essai:
        ETAT.write_text(json.dumps({"annonces": annonces,
                                    "immediats": sorted(immediats),
                                    "surprise": etat.get("surprise")},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        PRIORITE.write_text("high" if urgents else "default", encoding="utf-8")

    sortie = urgents + lignes
    if sortie:
        print("\n".join(sortie[:10]))
        if len(sortie) > 10:
            print(f"… et {len(sortie) - 10} autre(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
