#!/usr/bin/env python3
"""
alerter.py — Prépare une notification quand un bon créneau apparaît.

Lit `docs/data.json` produit par previsions.py, et signale les créneaux qui
dépassent le seuil. Un fichier d'état retient ce qui a déjà été annoncé :
comme le calcul tourne toutes les trois heures, sans ça tu recevrais huit fois
par jour la même alerte pour le même créneau.

Le message part sur la sortie standard, vide s'il n'y a rien à dire. C'est le
workflow qui se charge de l'envoyer.

Usage :
    python alerter.py --seuil 3
    python alerter.py --seuil 3.5 --essai     # sans toucher au fichier d'état
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).parent
DONNEES = RACINE / "docs" / "data.json"
ETAT = RACINE / "etat_alertes.json"

# Au-delà, la notification devient illisible sur un écran verrouillé.
MAX_LIGNES = 8

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janv.", "févr.", "mars", "avril", "mai", "juin",
           "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def date_fr(d: datetime) -> str:
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]}"


def charger_etat() -> set[str]:
    if not ETAT.exists():
        return set()
    try:
        return set(json.loads(ETAT.read_text(encoding="utf-8")))
    except Exception:
        return set()


def enregistrer_etat(cles: set[str]) -> None:
    """On ne garde que le futur proche : l'état ne doit pas grossir sans fin."""
    limite = datetime.now() - timedelta(days=1)
    vivantes = []
    for c in cles:
        try:
            if datetime.fromisoformat(c.split("|", 1)[1]) >= limite:
                vivantes.append(c)
        except (ValueError, IndexError):
            continue
    ETAT.write_text(json.dumps(sorted(vivantes), ensure_ascii=False),
                    encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seuil", type=float, default=3.0,
                   help="note à partir de laquelle on prévient (défaut 3)")
    p.add_argument("--essai", action="store_true",
                   help="afficher sans mettre à jour le fichier d'état")
    args = p.parse_args()

    if not DONNEES.exists():
        print(f"{DONNEES} introuvable.", file=sys.stderr)
        return 1

    data = json.loads(DONNEES.read_text(encoding="utf-8"))
    deja = charger_etat()
    maintenant = datetime.now()

    nouveaux = []
    toutes_cles = set(deja)
    for spot in data.get("spots", []):
        for c in spot.get("creneaux", []):
            if c["note_totale"] < args.seuil:
                continue
            instant = datetime.fromisoformat(c["instant"])
            if instant <= maintenant:           # inutile de prévenir pour du passé
                continue
            cle = f"{spot['cle']}|{c['instant']}"
            toutes_cles.add(cle)
            if cle not in deja:
                nouveaux.append((spot["nom"], instant, c))

    if not args.essai:
        enregistrer_etat(toutes_cles)

    if not nouveaux:
        return 0

    nouveaux.sort(key=lambda t: (-t[2]["note_totale"], t[1]))
    lignes = []
    for nom, instant, c in nouveaux[:MAX_LIGNES]:
        lignes.append(
            f"{nom} {date_fr(instant)} {instant:%H}h — {c['note_totale']:.1f}/5"
            f"  ({c['hauteur_m']:.2f} m à {c['tpeak_s']:.1f} s, "
            f"vent {round(c['vitesse_kt'])} nds)")
    if len(nouveaux) > MAX_LIGNES:
        lignes.append(f"et {len(nouveaux) - MAX_LIGNES} autre(s) créneau(x).")

    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
