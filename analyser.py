#!/usr/bin/env python3
"""
analyser.py — Confronte ton journal de sessions aux prévisions archivées.

Le principe : `journal.csv` contient ce que TU as observé, `archives/` contient
ce que le modèle avait prévu. Le script rapproche les deux et te dit :

  - à quel point la note calculée suit ta note réelle ;
  - lequel des critères (houle, marée, vent) prédit le mieux, et lequel
    n'apporte rien ;
  - comment la prévision dérive selon qu'elle date de la veille ou de trois
    jours avant.

Aucune dépendance : bibliothèque standard uniquement.

Usage :
    python analyser.py
    python analyser.py --spot wimereux
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).parent
JOURNAL = RACINE / "journal.csv"
ARCHIVES = RACINE / "archives"

# En dessous de ce nombre de sessions, les corrélations ne veulent rien dire.
MINIMUM_UTILE = 12

# Colonnes numériques comparées à ta note. Le nom affiché, puis la clé.
CRITERES = [
    ("note calculée", "note_totale"),
    ("houle", "note_houle"),
    ("marée", "note_maree"),
    ("  dont position", "note_position"),
    ("  dont stabilité", "note_stabilite"),
    ("vent", "note_vent"),
    ("énergie kJ", "energie_kwm"),
    ("Iribarren", "xi"),
    ("hauteur m", "hauteur_m"),
    ("période s", "tpeak_s"),
    ("translation", "translation_m_min"),
    ("RTR", "rtr"),
]


def lire_journal() -> list[dict]:
    if not JOURNAL.exists():
        raise SystemExit(f"{JOURNAL} introuvable.")
    lignes = []
    with JOURNAL.open(encoding="utf-8") as f:
        for i, ligne in enumerate(csv.DictReader(f), start=2):
            if not (ligne.get("date") or "").strip():
                continue
            if "exemple" in (ligne.get("commentaire") or ""):
                continue
            try:
                lignes.append({
                    "instant": f"{ligne['date'].strip()}T"
                               f"{int(ligne['heure']):02d}:00:00",
                    "spot": ligne["spot"].strip().lower(),
                    "note_reelle": float(ligne["note"]),
                    "commentaire": (ligne.get("commentaire") or "").strip(),
                })
            except (ValueError, KeyError) as e:
                print(f"  ligne {i} ignorée ({e})")
    return lignes


def charger_archives() -> list[tuple[str, dict]]:
    """(date de l'archive, contenu), triées de la plus ancienne à la plus récente."""
    if not ARCHIVES.exists():
        return []
    fichiers = []
    for f in sorted(ARCHIVES.glob("*.json")):
        try:
            fichiers.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            print(f"  archive illisible ignorée : {f.name}")
    return fichiers


def previsions_pour(archives, spot: str, instant: str) -> list[tuple[int, dict]]:
    """
    Toutes les prévisions retrouvées pour ce créneau, avec leur délai en jours.
    Délai 0 = prévision faite le jour même, 3 = trois jours avant.
    """
    jour_session = datetime.fromisoformat(instant).date()
    trouvees = []
    for date_archive, contenu in archives:
        try:
            jour_archive = datetime.fromisoformat(date_archive).date()
        except ValueError:
            continue
        delai = (jour_session - jour_archive).days
        if delai < 0:
            continue
        for sp in contenu.get("spots", []):
            if sp.get("cle") != spot:
                continue
            for c in sp.get("creneaux", []):
                if c.get("instant") == instant:
                    trouvees.append((delai, c))
    trouvees.sort(key=lambda t: t[0])
    return trouvees


def correlation(xs, ys) -> float | None:
    """Coefficient de Pearson, ou None si le calcul n'a pas de sens."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def lire_pour_le_dire(r: float | None) -> str:
    if r is None:
        return "indéterminable"
    a = abs(r)
    sens = "" if r >= 0 else " (en sens inverse)"
    if a >= 0.7:
        return f"lien fort{sens}"
    if a >= 0.4:
        return f"lien net{sens}"
    if a >= 0.2:
        return f"lien faible{sens}"
    return "aucun lien"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spot", help="n'analyser qu'un spot")
    args = p.parse_args()

    sessions = lire_journal()
    if args.spot:
        sessions = [s for s in sessions if s["spot"] == args.spot]
    if not sessions:
        print("Aucune session dans le journal. Ajoute une ligne à journal.csv "
              "après ta prochaine sortie.")
        return 0

    archives = charger_archives()
    if not archives:
        print("Aucune archive dans archives/. Le workflow en dépose une par "
              "jour ; reviens quand il aura tourné quelques jours.")
        return 0

    appariees = []
    orphelines = []
    for s in sessions:
        prevs = previsions_pour(archives, s["spot"], s["instant"])
        if prevs:
            appariees.append((s, prevs))
        else:
            orphelines.append(s)

    print(f"\n{len(sessions)} session(s) au journal, "
          f"{len(appariees)} retrouvée(s) dans les archives.")
    if orphelines:
        print(f"  {len(orphelines)} sans prévision archivée "
              "(session antérieure à l'archive, ou heure hors plage de jour) :")
        for s in orphelines[:5]:
            print(f"    {s['instant'][:16]} {s['spot']}")

    if not appariees:
        return 0

    # --- Détail session par session ---
    print(f"\n{'-' * 74}")
    print(f"{'session':18s} {'spot':10s} {'toi':>4s} {'prévu':>6s} "
          f"{'écart':>6s}  détail")
    print("-" * 74)
    for s, prevs in appariees:
        delai, c = prevs[0]
        ecart = c["note_totale"] - s["note_reelle"]
        print(f"{s['instant'][:16]:18s} {s['spot']:10s} "
              f"{s['note_reelle']:4.1f} {c['note_totale']:6.2f} "
              f"{ecart:+6.2f}  houle {c['note_houle']:.1f} "
              f"marée {c['note_maree']:.1f} vent {c['note_vent']}")
        if s["commentaire"]:
            print(f"{'':18s} « {s['commentaire']} »")

    reelles = [s["note_reelle"] for s, _ in appariees]
    calculees = [p[0][1]["note_totale"] for _, p in appariees]
    biais = sum(c - r for c, r in zip(calculees, reelles)) / len(reelles)
    ecart_moyen = sum(abs(c - r) for c, r in zip(calculees, reelles)) / len(reelles)

    print(f"\nÉcart moyen : {ecart_moyen:.2f} point. "
          f"Biais : {biais:+.2f} "
          f"({'le calcul surestime' if biais > 0 else 'le calcul sous-estime'}).")

    # --- Ce qui prédit quoi ---
    print(f"\n{'-' * 74}")
    print("Ce qui suit le mieux ton ressenti")
    print("-" * 74)
    if len(appariees) < MINIMUM_UTILE:
        print(f"  Attention : {len(appariees)} sessions seulement. En dessous "
              f"de {MINIMUM_UTILE}, ces chiffres sont du bruit.\n"
              "  Ils sont affichés pour que tu voies la mécanique, pas pour "
              "décider quoi que ce soit.")
    resultats = []
    for libelle, cle in CRITERES:
        valeurs = [p[0][1].get(cle) for _, p in appariees]
        if any(v is None for v in valeurs):
            continue
        r = correlation(valeurs, reelles)
        resultats.append((r if r is not None else -9, libelle, r))
    for _, libelle, r in sorted(resultats, reverse=True):
        barre = "" if r is None else "█" * int(abs(r) * 20)
        print(f"  {libelle:18s} {('  n/a' if r is None else f'{r:+.2f}'):>6s}  "
              f"{barre} {lire_pour_le_dire(r)}")

    # --- Dérive de la prévision avec le délai ---
    par_delai = {}
    for s, prevs in appariees:
        for delai, c in prevs:
            par_delai.setdefault(delai, []).append(
                abs(c["note_totale"] - s["note_reelle"]))
    if len(par_delai) > 1:
        print(f"\n{'-' * 74}")
        print("Fiabilité selon l'ancienneté de la prévision")
        print("-" * 74)
        for delai in sorted(par_delai):
            e = par_delai[delai]
            quand = "le jour même" if delai == 0 else f"{delai} jour(s) avant"
            print(f"  {quand:16s} écart moyen {sum(e)/len(e):.2f} "
                  f"sur {len(e)} créneau(x)")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
