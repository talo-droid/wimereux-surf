#!/usr/bin/env python3
"""
widget.py — Le résumé à plat pour le widget du téléphone (KWGT).

Lit docs/data.json (prévisions) et docs/weekend.json (Siouville) et écrit
docs/widget.json : une valeur par clé, déjà mise en forme, pour que le widget
n'ait qu'à afficher. Lancé à la fin des tâches « Prévisions » et « Week-end
Siouville ».

Clés :
  maj                    « 16/11 10h43 », heure de Paris
  w_surf, w_surf_q, w_surf_c   Wimereux surf : note, quand, couleur
  w_wing, w_wing_q, w_wing_c   Wimereux wing
  c_surf, c_surf_q, c_surf_c   Calais surf
  c_wing, c_wing_q, c_wing_c   Calais wing
  top                    la meilleure session surf des deux spots, en clair
  siou, siou_c           verdict Siouville et couleur pastel du van
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DOCS = Path(__file__).parent / "docs"
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
# Mêmes couleurs que la page : galet pour 0, puis rouge → vert foncé.
NOTES = ["#6B7F83", "#A6453A", "#C0762A", "#96851B", "#4C8A45", "#1C7A5D"]
VAN = {"GO": "#A8DDB9", "À SURVEILLER": "#F6D29A", "NON": "#F1B3AE"}


def lire(nom: str) -> dict:
    try:
        return json.loads((DOCS / nom).read_text(encoding="utf-8"))
    except Exception:
        return {}


def couleur(n: float) -> str:
    return NOTES[max(0, min(5, round(n)))]


def meilleure(spot: dict, attr: str) -> tuple[float, str]:
    """Comme la page : la meilleure session à venir, sinon la meilleure heure."""
    cr = spot.get("creneaux") or []
    avec = [c for c in cr if c.get(attr) is not None]
    if avec:
        c = max(avec, key=lambda c: c[attr])
        n = c[attr]
    elif cr:
        horaire = "note_totale" if attr == "session_surf" else "note_wing"
        c = max(cr, key=lambda c: c.get(horaire) or 0)
        n = c.get(horaire) or 0
    else:
        return 0.0, "—"
    if n <= 0:
        return 0.0, "—"
    t = datetime.fromisoformat(c["instant"])
    return float(n), f"{JOURS[t.weekday()]} {t.hour:02d}h"


def main() -> int:
    data, we = lire("data.json"), lire("weekend.json")
    w = {}
    try:
        g = datetime.fromisoformat(data["genere_le"])
        w["maj"] = f"{g.day:02d}/{g.month:02d} {g.hour:02d}h{g.minute:02d}"
    except Exception:
        w["maj"] = "?"
    top = (0.0, "")
    for spot in data.get("spots", []):
        p = {"wimereux": "w", "calais": "c"}.get(spot.get("cle"))
        if not p:
            continue
        for disc, attr in (("surf", "session_surf"), ("wing", "session_wing")):
            n, q = meilleure(spot, attr)
            w[f"{p}_{disc}"] = f"{n:.1f}"
            w[f"{p}_{disc}_q"] = q
            w[f"{p}_{disc}_c"] = couleur(n)
            if disc == "surf" and n > top[0]:
                top = (n, f"{spot['nom']} {n:.1f} {q}")
    w["top"] = top[1] or "rien de surfable"
    v = we.get("verdict") or "PAS ENCORE"
    w["siou"] = v.lower() if v != "GO" else "GO"
    w["siou_c"] = VAN.get(v, "#CBD5D6")
    (DOCS / "widget.json").write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
