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
PRIORITE = RACINE / "priorite.txt"

HAUSSE_NOTABLE = 0.75     # gain qui justifie une nouvelle alerte
MARGE_ANNULATION = 0.5    # sous seuil - marge, une session annoncée est annulée
HORIZON_IMMEDIAT_H = 3    # « c'est bon maintenant » : départ dans ce délai

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
            return etat
    except Exception:
        pass
    # Ancien format (simple liste) ou fichier absent : on repart de zéro.
    return {"annonces": {}, "immediats": []}


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

        for disc, attr in (("surf", "session_surf"), ("wing", "session_wing")):
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

    # Ménage : on oublie ce qui est passé depuis plus d'un jour.
    hier = (ref - timedelta(days=1)).date().isoformat()
    annonces = {k: v for k, v in annonces.items() if k.split("|")[2] >= hier}
    immediats = {k for k in immediats
                 if datetime.fromisoformat(k.split("|")[2]) >= ref - timedelta(days=1)}

    if not args.essai:
        ETAT.write_text(json.dumps({"annonces": annonces,
                                    "immediats": sorted(immediats)},
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
