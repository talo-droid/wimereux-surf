#!/usr/bin/env python3
"""
analyser.py — Confronte ton journal aux prévisions archivées.

Le journal distingue deux choses que l'ancienne note unique mélangeait :
  - `conditions` : la qualité de la mer et du vent, ce que le modèle prétend
    prédire. C'est elle qu'on compare à la note calculée.
  - `session` : ton plaisir, qui dépend aussi de la fatigue, du monde à
    l'eau, du matériel. Conservée, mais jamais comparée au modèle.

Et deux types de lignes :
  - `session` : tu étais à l'eau ;
  - `observation` : tu as seulement regardé la mer, sans y aller. C'est ce qui
    permet de repérer les bonnes journées que le modèle a ratées — sans elles,
    tu n'apprendrais que ses erreurs par excès d'optimisme.

Usage :
    python analyser.py
    python analyser.py --spot calais --discipline wing
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
MINIMUM_UTILE = 12

NOTE_MODELE = {"surf": "note_totale", "wing": "note_wing"}

CRITERES = {
    "surf": [("note calculée", "note_totale"), ("houle", "note_houle"),
             ("marée", "note_maree"), ("  position", "note_position"),
             ("  stabilité", "note_stabilite"), ("vent", "note_vent"),
             ("énergie kJ", "energie_kwm"), ("Iribarren", "xi"),
             ("part houle longue", "part_houle"), ("hauteur m", "hauteur_m"),
             ("période s", "tpeak_s"), ("RTR", "rtr")],
    "wing": [("note calculée", "note_wing"), ("vent nds", "vitesse_kt"),
             ("rafales nds", "rafales_kt"), ("niveau de marée", "niveau_maree"),
             ("hauteur mer m", "hauteur_m")],
}


def _nombre(texte):
    texte = (texte or "").strip().replace(",", ".")
    return float(texte) if texte else None


def lire_journal() -> list[dict]:
    if not JOURNAL.exists():
        raise SystemExit(f"{JOURNAL} introuvable.")
    lignes = []
    with JOURNAL.open(encoding="utf-8") as f:
        for i, l in enumerate(csv.DictReader(f), start=2):
            if not (l.get("date") or "").strip():
                continue
            try:
                # Ancien format à note unique : elle vaut pour les deux.
                if "conditions" not in l and "note" in l:
                    l["conditions"] = l["session"] = l["note"]
                lignes.append({
                    "instant": f"{l['date'].strip()}T{int(l['heure']):02d}:00:00",
                    "spot": l["spot"].strip().lower(),
                    "discipline": (l.get("discipline") or "surf").strip().lower(),
                    "type": (l.get("type") or "session").strip().lower(),
                    "conditions": _nombre(l.get("conditions")),
                    "session": _nombre(l.get("session")),
                    "commentaire": (l.get("commentaire") or "").strip(),
                })
            except (ValueError, KeyError) as e:
                print(f"  ligne {i} ignorée ({e})")
    return [l for l in lignes if l["conditions"] is not None]


def charger_archives():
    if not ARCHIVES.exists():
        return []
    sortie = []
    for f in sorted(ARCHIVES.glob("*.json")):
        try:
            sortie.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            print(f"  archive illisible ignorée : {f.name}")
    return sortie


def previsions_pour(archives, spot, instant):
    """Toutes les prévisions retrouvées pour ce créneau, avec leur délai en jours."""
    jour = datetime.fromisoformat(instant).date()
    trouvees = []
    for date_archive, contenu in archives:
        try:
            delai = (jour - datetime.fromisoformat(date_archive).date()).days
        except ValueError:
            continue
        if delai < 0:
            continue
        for sp in contenu.get("spots", []):
            if sp.get("cle") == spot:
                for c in sp.get("creneaux", []):
                    if c.get("instant") == instant:
                        trouvees.append((delai, c))
    return sorted(trouvees, key=lambda t: t[0])


def correlation(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def lecture(r):
    if r is None:
        return "indéterminable"
    a = abs(r)
    sens = "" if r >= 0 else " (en sens inverse)"
    return (f"lien fort{sens}" if a >= 0.7 else f"lien net{sens}" if a >= 0.4
            else f"lien faible{sens}" if a >= 0.2 else "aucun lien")


def analyser(discipline, entrees, archives):
    cle_note = NOTE_MODELE[discipline]
    appariees = [(e, prev) for e in entrees
                 for prev in [previsions_pour(archives, e["spot"], e["instant"])]
                 if prev and prev[0][1].get(cle_note) is not None]
    titre = f" {discipline.upper()} "
    print(f"\n{titre:=^74}")
    print(f"{len(entrees)} entrée(s), {len(appariees)} retrouvée(s) dans les archives.")
    if not appariees:
        return

    print(f"\n{'créneau':17s} {'spot':9s} {'type':5s} {'cond':>4s} {'prévu':>6s} {'écart':>6s}")
    for e, prev in appariees:
        c = prev[0][1]
        print(f"{e['instant'][:16]:17s} {e['spot']:9s} "
              f"{'obs' if e['type'] == 'observation' else 'sess':5s} "
              f"{e['conditions']:4.1f} {c[cle_note]:6.2f} {c[cle_note] - e['conditions']:+6.2f}"
              + (f"   « {e['commentaire']} »" if e["commentaire"] else ""))

    reel = [e["conditions"] for e, _ in appariees]
    prevu = [p[0][1][cle_note] for _, p in appariees]
    biais = sum(p - r for p, r in zip(prevu, reel)) / len(reel)
    ecart = sum(abs(p - r) for p, r in zip(prevu, reel)) / len(reel)
    print(f"\nÉcart moyen {ecart:.2f} point, biais {biais:+.2f} "
          f"({'le calcul surestime' if biais > 0 else 'le calcul sous-estime'}).")

    # Les erreurs qui comptent, dans les deux sens.
    rates = [e for (e, p) in appariees if e["conditions"] >= 3.5 and p[0][1][cle_note] < 2.5]
    faux = [e for (e, p) in appariees if e["conditions"] < 2.5 and p[0][1][cle_note] >= 3.5]
    print(f"Bonnes conditions ratées par le modèle : {len(rates)}   "
          f"fausses promesses : {len(faux)}")
    nb_obs = sum(1 for e, _ in appariees if e["type"] == "observation")
    if nb_obs == 0:
        print("  Aucune observation au journal : les journées ratées par le modèle "
              "restent invisibles.\n  Note aussi les jours où tu n'y vas pas.")

    print("\nCe qui suit le mieux les conditions observées")
    if len(appariees) < MINIMUM_UTILE:
        print(f"  {len(appariees)} entrées seulement : sous {MINIMUM_UTILE}, "
              "c'est du bruit. Affiché pour la mécanique, pas pour décider.")
    lignes = []
    for libelle, cle in CRITERES[discipline]:
        vals = [p[0][1].get(cle) for _, p in appariees]
        if any(v is None for v in vals):
            continue
        r = correlation(vals, reel)
        lignes.append((r if r is not None else -9, libelle, r))
    for _, libelle, r in sorted(lignes, reverse=True):
        barre = "" if r is None else "█" * int(abs(r) * 20)
        print(f"  {libelle:18s} {('  n/a' if r is None else f'{r:+.2f}'):>6s}  {barre} {lecture(r)}")

    par_delai = {}
    for e, prev in appariees:
        for delai, c in prev:
            par_delai.setdefault(delai, []).append(abs(c[cle_note] - e["conditions"]))
    if len(par_delai) > 1:
        print("\nFiabilité selon l'ancienneté de la prévision")
        for d in sorted(par_delai):
            v = par_delai[d]
            print(f"  {('le jour même' if d == 0 else f'{d} jour(s) avant'):16s} "
                  f"écart moyen {sum(v) / len(v):.2f} sur {len(v)} créneau(x)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spot")
    p.add_argument("--discipline", choices=["surf", "wing"])
    args = p.parse_args()

    entrees = lire_journal()
    if args.spot:
        entrees = [e for e in entrees if e["spot"] == args.spot]
    if not entrees:
        print("Journal vide. Ajoute une ligne après ta prochaine sortie, "
              "ou après avoir simplement regardé la mer.")
        return 0
    archives = charger_archives()
    if not archives:
        print("Aucune archive encore : reviens quand le workflow aura tourné quelques jours.")
        return 0
    for disc in ([args.discipline] if args.discipline else ["surf", "wing"]):
        sous = [e for e in entrees if e["discipline"] == disc]
        if sous:
            analyser(disc, sous, archives)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
