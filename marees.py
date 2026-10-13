#!/usr/bin/env python3
"""
marees.py — Prépare les marées des dix prochains jours, à part.

Les marées se calculent longtemps à l'avance : inutile de dépendre
d'api-maree.fr à chaque calcul des notes. Cette tâche tourne deux fois par
jour, interroge le service par tranches de trois jours pour chaque port, et
range pleines mers, basses mers et hauteurs d'eau dans marees_cache.json.
previsions.py lit ce fichier en premier.

Elle recale aussi les constantes harmoniques (maree_harmonique.py) sur
toutes les pleines et basses mers connues : si api-maree.fr est en panne,
les prévisions calculent la marée elles-mêmes, sans réseau. Une panne du
service n'arrête donc plus rien, et cette tâche reste verte.

Usage :
    python marees.py              # met à jour marees_cache.json
    python marees.py --jours 5    # horizon plus court
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

import previsions

TRANCHE_J = 3


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jours", type=int, default=10)
    a = p.parse_args()

    debut = previsions.maintenant().replace(tzinfo=None, minute=0, second=0, microsecond=0) \
        - timedelta(days=1)
    fin = debut + timedelta(days=a.jours + 1)
    sites = {sp["site_maree"]: sp for sp in previsions.SPOTS.values()}
    essais = echecs = 0
    for site, sp in sites.items():
        n_ext = n_h = 0
        t = debut
        while t < fin:
            u = min(t + timedelta(days=TRANCHE_J), fin)
            try:
                ext = previsions._recuperer_extrema_maree(sp, t, u)
                previsions._cache_maree_ecrire(site, "extrema", {
                    e["instant"].isoformat(): {k: v for k, v in e.items() if k != "instant"}
                    for e in ext})
                hts = previsions._recuperer_hauteurs_eau(sp, t, u)
                previsions._cache_maree_ecrire(site, "hauteurs",
                                               {k.isoformat(): v for k, v in hts.items()})
                n_ext += len(ext)
                n_h += len(hts)
            except Exception as e:
                echecs += 1
                print(f"{site} {t:%d/%m}→{u:%d/%m} : {e}", file=sys.stderr)
            essais += 1
            t = u
        print(f"{site} : {n_ext} pleines/basses mers, {n_h} hauteurs d'eau", file=sys.stderr)
    if essais and echecs == essais:
        print("api-maree.fr injoignable : les prévisions calculeront la marée "
              "(constantes harmoniques).", file=sys.stderr)
    # Plus on accumule de pleines et basses mers, plus le calcul est juste.
    import maree_harmonique
    try:
        maree_harmonique.main_ajuster()
    except Exception as e:
        print(f"constantes harmoniques non recalées : {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
