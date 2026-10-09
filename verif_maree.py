#!/usr/bin/env python3
"""
verif_maree.py — Contrôle de la bouée d'Ambleteuse autour de la pleine mer.

Le calcul complet tourne toutes les trois heures : une embellie peut passer
entre deux. Ce petit contrôle se réveille souvent (toutes les vingt minutes en
journée) mais ne fait presque jamais rien : il regarde dans `docs/data.json`
l'heure des pleines mers de Wimereux et ne lit la bouée qu'à deux moments,

  - une heure avant la pleine mer ;
  - à la pleine mer.

À ces deux moments, il note la mesure avec le barème surf (la houle mesurée
remplace la houle prévue ; vent, marée et orage restent ceux de l'heure),
la compare à la prévision de la même heure, et prévient seulement en cas de
bonne surprise — mêmes critères et même pause que l'alerte d'`alerter.py`,
donc jamais de doublon entre les deux.

La nuit, rien : sans créneau de jour à comparer, il n'y a pas de note.

Le message part sur la sortie standard (vide s'il n'y a rien à dire). L'état,
c'est-à-dire les contrôles déjà faits et la dernière alerte, est gardé dans
`etat_maree.json`.

Usage :
    python verif_maree.py            # ne fait quelque chose que dans une fenêtre
    python verif_maree.py --forcer   # contrôle tout de suite, pour essayer
    python verif_maree.py --essai    # affiche sans rien mémoriser
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import alerter
import previsions

RACINE = Path(__file__).parent
DONNEES = RACINE / "docs" / "data.json"
ETAT = alerter.ETAT_MAREE

# Les moments de contrôle, en minutes par rapport à la pleine mer.
MOMENTS = ((-60, "1 h avant la pleine mer"), (0, "à la pleine mer"))

# Une fenêtre s'ouvre un peu avant le moment visé et reste ouverte assez
# longtemps pour absorber les retards des tâches planifiées de GitHub, qui
# partent souvent avec dix à trente minutes de décalage. Chaque moment n'est
# contrôlé qu'une fois.
AVANCE_MIN = 10
RETARD_MAX_MIN = 45


def charger_etat() -> dict:
    try:
        e = json.loads(ETAT.read_text(encoding="utf-8"))
        if isinstance(e, dict):
            e.setdefault("faits", [])
            e.setdefault("surprise", None)
            e.setdefault("dernier", None)
            return e
    except Exception:
        pass
    return {"faits": [], "surprise": None, "dernier": None}


def creneaux_de(spot: dict) -> list:
    """Les créneaux de data.json, avec l'heure en vrai datetime comme Creneau."""
    return [SimpleNamespace(**{**c, "instant": datetime.fromisoformat(c["instant"])})
            for c in spot.get("creneaux", [])]


def moments_dus(spot: dict, ref: datetime, faits: set) -> list:
    """
    Les moments de contrôle dont la fenêtre est ouverte, pas encore faits, et
    qui tombent de jour (un créneau existe à cette heure-là).
    """
    heures_de_jour = {c["instant"][:13] for c in spot.get("creneaux", [])}
    dus = []
    for m in spot.get("marees", []):
        if m.get("type") != "PM":
            continue
        pm = datetime.fromisoformat(m["instant"]).replace(tzinfo=None)
        for decalage, libelle in MOMENTS:
            vise = pm + timedelta(minutes=decalage)
            cle = f"{pm:%Y-%m-%dT%H:%M}|{decalage}"
            if cle in faits:
                continue
            if not (vise - timedelta(minutes=AVANCE_MIN) <= ref
                    <= vise + timedelta(minutes=RETARD_MAX_MIN)):
                continue
            if vise.isoformat()[:13] not in heures_de_jour:
                continue
            dus.append((cle, libelle, pm))
    return dus


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--forcer", action="store_true",
                   help="contrôler maintenant, même hors fenêtre")
    p.add_argument("--essai", action="store_true",
                   help="afficher sans mettre à jour l'état")
    p.add_argument("--seuil-surprise", type=float, default=alerter.SEUIL_SURPRISE)
    p.add_argument("--ecart-surprise", type=float, default=alerter.ECART_SURPRISE)
    args = p.parse_args()

    if not DONNEES.exists():
        print(f"{DONNEES} introuvable.", file=sys.stderr)
        return 1
    data = json.loads(DONNEES.read_text(encoding="utf-8"))
    spot = next((s for s in data.get("spots", []) if s.get("cle") == "wimereux"), None)
    if not spot or not spot.get("creneaux"):
        print("Pas de prévision pour Wimereux dans data.json.", file=sys.stderr)
        return 0

    etat = charger_etat()
    ref = alerter.maintenant()
    dus = moments_dus(spot, ref, set(etat["faits"]))
    if args.forcer and not dus:
        dus = [(None, "à la demande", None)]
    if not dus:
        print("Hors fenêtre de pleine mer, rien à faire.", file=sys.stderr)
        return 0

    libelle = dus[-1][1]
    print(f"Contrôle {libelle} ({ref:%H:%M}).", file=sys.stderr)

    bouee = previsions.recuperer_bouee()
    creneaux = creneaux_de(spot)
    message = None
    if bouee:
        previsions.noter_mesure(bouee, creneaux, previsions.SPOTS["wimereux"])
        previsions.archiver_observation(bouee, creneaux)
        print(f"  bouée {bouee['instant']} : {bouee.get('hauteur_m')} m, "
              f"{bouee.get('periode_pic_s')} s, note mesurée "
              f"{bouee.get('note_mesuree')}, prévue {bouee.get('note_prevue')}",
              file=sys.stderr)
        message = alerter.message_surprise(
            bouee, ref,
            alerter.derniere_surprise(alerter.charger_etat()),
            args.seuil_surprise, args.ecart_surprise,
            contexte=f", {libelle}")
    else:
        print("  bouée muette, contrôle sans suite.", file=sys.stderr)

    if not args.essai:
        # Les contrôles sont notés faits même si la bouée était muette : on
        # ne relance pas la même fenêtre vingt minutes plus tard pour rien.
        faits = set(etat["faits"]) | {cle for cle, _, _ in dus if cle}
        limite = (ref - timedelta(days=2)).isoformat()[:16]
        etat["faits"] = sorted(f for f in faits if f.split("|")[0] >= limite)
        etat["dernier"] = {
            "le": ref.isoformat(timespec="minutes"), "moment": libelle,
            "mesure": bouee and {k: bouee.get(k) for k in
                                 ("instant", "hauteur_m", "periode_pic_s",
                                  "note_mesuree", "note_prevue")},
        }
        if message:
            etat["surprise"] = ref.isoformat(timespec="minutes")
        ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    if message:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
