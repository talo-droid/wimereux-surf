#!/usr/bin/env python3
"""
houle_carte.py — Relevé des bouées de la Manche Est pour la carte animée.

Toutes les trente minutes en journée, on lit d'un coup toutes les bouées
temps réel entre l'île de Wight et le pas de Calais :

  - le service WaveNet du Cefas, qui regroupe ses propres bouées (Hastings),
    celles du Channel Coastal Observatory (Pevensey, Rye, Folkestone,
    Goodwin…) et les bateaux-phares du Met Office (Sandettie, Greenwich) ;
  - la bouée d'Ambleteuse (Géodunes), avec le filtre des mesures parasites
    de previsions.py.

Ces services ne donnent que la dernière mesure : l'historique, on le
construit nous-mêmes en gardant les 36 dernières heures dans
`docs/houle.json`. La page `docs/houle.html` lit ce fichier ; elle ne peut
pas interroger le Cefas elle-même, qui n'autorise pas les appels depuis un
navigateur.

Usage :
    python houle_carte.py            # relève et met à jour docs/houle.json
    python houle_carte.py --essai    # affiche sans rien écrire
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import previsions

RACINE = Path(__file__).parent
SORTIE = RACINE / "docs" / "houle.json"
GARDER_H = 36

# Zone retenue : la Manche Est, du Solent au pas de Calais. Au nord, on
# s'arrête avant l'estuaire de la Tamise.
LAT = (49.8, 51.45)
LON = (-2.0, 2.8)

# Noms courts : le service ne donne pas toujours le nom des bouées du CCO.
NOMS = {
    "HASTINGSWN": "Hastings", "POOLEBAYWN": "Poole Bay",
    "208": "Boscombe", "209": "Milford", "210": "Sandown Bay",
    "211": "Hayling Island", "212": "Bracklesham Bay", "213": "Rustington",
    "214": "Seaford", "215": "Pevensey Bay", "216": "Rye Bay",
    "217": "Folkestone", "218": "Goodwin Sands",
    "8": "Sandettie (bateau-phare)", "9": "Greenwich (bateau-phare)",
}


def _nombre(r: dict, cle: str):
    v = (r.get(cle) or {}).get("values") or [None]
    try:
        return round(float(v[0]), 2)
    except (TypeError, ValueError):
        return None


def releve_cefas() -> list[dict]:
    try:
        j = previsions._get_json(previsions.HASTINGS_DIRECT, {})
    except Exception as e:
        print(f"WaveNet indisponible : {e}", file=sys.stderr)
        return []
    sortie = []
    for f in j.get("features", []):
        try:
            lon, lat = f["geometry"]["coordinates"][:2]
        except (KeyError, TypeError, ValueError):
            continue
        if not (LAT[0] <= lat <= LAT[1] and LON[0] <= lon <= LON[1]):
            continue
        p = f.get("properties") or {}
        r = p.get("results") or {}
        hm0 = _nombre(r, "Hm0")
        if hm0 is None or not p.get("timestamp"):
            continue
        # Horodatage en temps universel, sans fuseau dans la réponse.
        t = datetime.fromisoformat(p["timestamp"][:19]).replace(tzinfo=timezone.utc)
        ident = str(p.get("id"))
        sortie.append({
            "id": ident,
            "nom": NOMS.get(ident) or p.get("title") or ident,
            "lat": round(lat, 3), "lon": round(lon, 3),
            "mesure": [t.strftime("%Y-%m-%dT%H:%MZ"), hm0,
                       _nombre(r, "Tpeak") or _nombre(r, "Tz"),
                       _nombre(r, "W_PDIR")],
            "phare": ident in ("8", "9"),
        })
    return sortie


def releve_ambleteuse() -> list[dict]:
    b = previsions.recuperer_bouee()
    if not b or b.get("hauteur_m") is None:
        return []
    t = datetime.fromisoformat(b["instant"]).astimezone(timezone.utc)
    return [{
        "id": "AMB", "nom": "Ambleteuse",
        "lat": round(b.get("latitude") or 50.808, 3),
        "lon": round(b.get("longitude") or 1.551, 3),
        "mesure": [t.strftime("%Y-%m-%dT%H:%MZ"), round(b["hauteur_m"], 2),
                   b.get("periode_pic_s"), b.get("direction_pic")],
        "phare": False,
    }]


def fusionner(ancien: dict, releves: list[dict], maintenant: datetime) -> dict:
    limite = (maintenant - timedelta(hours=GARDER_H)).strftime("%Y-%m-%dT%H:%MZ")
    bouees = {b["id"]: b for b in ancien.get("bouees", [])}
    for r in releves:
        b = bouees.setdefault(r["id"], {"serie": []})
        b.update({k: r[k] for k in ("id", "nom", "lat", "lon", "phare")})
        if not any(m[0] == r["mesure"][0] for m in b["serie"]):
            b["serie"].append(r["mesure"])
    for b in bouees.values():
        b["serie"] = sorted((m for m in b["serie"] if m[0] >= limite),
                            key=lambda m: m[0])
    return {
        "maj": maintenant.strftime("%Y-%m-%dT%H:%MZ"),
        "bouees": sorted((b for b in bouees.values() if b["serie"]),
                         key=lambda b: b["lon"]),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--essai", action="store_true", help="afficher sans écrire")
    args = p.parse_args()

    maintenant = datetime.now(timezone.utc)
    releves = releve_cefas() + releve_ambleteuse()
    print(f"{len(releves)} bouées relevées.", file=sys.stderr)
    if not releves:
        return 0
    try:
        ancien = json.loads(SORTIE.read_text(encoding="utf-8"))
    except Exception:
        ancien = {}
    donnees = fusionner(ancien, releves, maintenant)
    texte = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))
    if args.essai:
        print(texte[:2000])
    else:
        SORTIE.write_text(texte, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
