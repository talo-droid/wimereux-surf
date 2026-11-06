#!/usr/bin/env python3
"""
weekend.py — Le feu vert « week-end à Siouville ».

Siouville-Hague (Cotentin, plage ouverte à l'ouest) est à quatre heures de
route : on n'y va que si le séjour entier vaut le coup, et il faut le savoir
trois ou quatre jours avant. Ce script regarde le prochain week-end, du
vendredi au dimanche, et rend un verdict :

  GO            au moins deux journées bonnes, et aucune journée de tempête ;
  À SURVEILLER  pareil, mais les prévisions de vent ne sont pas d'accord entre
                elles (confiance faible), ou une seule journée bonne et une
                autre tout près ;
  NON           sinon.

Une journée est BONNE quand il existe au moins deux heures de suite, de jour,
avec une houle d'au moins 1 m et 7 s, bien orientée, et un vent faible (ou
offshore, d'est à sud-est, et pas trop fort). Elle est AFFREUSE quand des
rafales de tempête, un vent fort toute la journée ou un orage la rendent
pénible même à terre : c'est le seul cas où un troisième jour gâche le
séjour.

La confiance vient de la prévision d'ensemble du Centre européen (51 versions
du même modèle) : la part des versions qui donnent, elles aussi, un vent
acceptable pendant le meilleur créneau de la journée.

Sorties : docs/weekend.json (pour la page siouville.html), et un message sur
la sortie standard quand il faut prévenir (vide sinon). L'état des alertes
déjà envoyées est gardé dans etat_weekend.json.

Usage :
    python weekend.py               # calcule, écrit, prépare l'alerte
    python weekend.py --essai       # affiche sans rien mémoriser
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import previsions as P

RACINE = Path(__file__).parent
SORTIE = RACINE / "docs" / "weekend.json"
ETAT = RACINE / "etat_weekend.json"

SIOUVILLE = {
    "nom": "Siouville",
    "bouee": "Siouville (modèle)",
    # Le point de houle est pris au large, en eau libre, pour que le modèle
    # régional (EWAM) ne tombe pas sur une maille côtière.
    "point_houle": (49.565, -1.960),
    "point_spot": (49.5590, -1.8460),
    "point_vent": (49.560, -1.880),
    # La plage regarde l'ouest. Les îles Anglo-Normandes abritent une partie
    # de la houle de sud-ouest.
    "direction_houle": (240.0, 320.0),
    "marge_direction": 20.0,
    # Offshore : vent d'est à sud-est.
    "axe_offshore": 105.0,
}

# Critères donnés par Pierre (nov. 2026) : 1 m à 7 s minimum, sans vent.
HOULE_MIN_M = 1.0
PERIODE_MIN_S = 7.0
VENT_CALME_KT = 10.0          # en dessous, la direction importe peu
VENT_OFFSHORE_MAX_KT = 18.0   # offshore franc : acceptable jusque-là
SECTEUR_OFFSHORE = 55.0       # demi-angle autour de l'axe offshore
DUREE_MIN_H = 2               # heures consécutives pour faire une bonne journée

# Journée « affreuse » : celle qui gâche le séjour même si on ne surfe pas.
RAFALES_TEMPETE_KT = 40.0     # environ 75 km/h
VENT_FORT_KT = 25.0
HEURES_VENT_FORT = 4

CONFIANCE_GO = 0.6

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ---------------------------------------------------------------- critères

def _ecart(a, b):
    return abs((a - b + 180) % 360 - 180)


def houle_ok(h) -> bool:
    if h.get("hauteur_m") is None or h.get("tpeak_s") is None:
        return False
    if h["hauteur_m"] < HOULE_MIN_M or h["tpeak_s"] < PERIODE_MIN_S:
        return False
    d = h.get("direction_deg")
    if d is None:
        return True
    lo, hi = SIOUVILLE["direction_houle"]
    centre = (lo + (hi - lo) / 2) % 360
    return _ecart(d, centre) <= (hi - lo) / 2 + SIOUVILLE["marge_direction"] / 2


def vent_ok(vitesse, direction) -> bool:
    if vitesse is None:
        return False
    if vitesse < VENT_CALME_KT:
        return True
    if direction is None:
        return False
    return (_ecart(direction, SIOUVILLE["axe_offshore"]) <= SECTEUR_OFFSHORE
            and vitesse <= VENT_OFFSHORE_MAX_KT)


def journee_affreuse(heures_jour: list[dict]) -> str | None:
    """Raison pour laquelle la journée gâcherait le séjour, ou None."""
    if not heures_jour:
        return None
    raf = max((h.get("rafales_kt") or 0) for h in heures_jour)
    if raf >= RAFALES_TEMPETE_KT:
        return f"rafales à {raf:.0f} nds"
    fort = sum(1 for h in heures_jour if (h.get("vitesse_kt") or 0) >= VENT_FORT_KT)
    if fort >= HEURES_VENT_FORT:
        return f"vent fort ({fort} h à {VENT_FORT_KT:.0f} nds ou plus)"
    if any(h.get("orage") == P.ORAGE_VETO for h in heures_jour):
        return "orage"
    return None


# ---------------------------------------------------------------- données

def prochain_weekend(aujourd_hui: date) -> tuple[date, date]:
    """Le vendredi et le dimanche à venir. Le week-end en cours, s'il a
    commencé, ne compte plus : on regarde le suivant."""
    jours = (4 - aujourd_hui.weekday()) % 7
    if aujourd_hui.weekday() >= 4:      # vendredi, samedi, dimanche
        jours = 7 - aujourd_hui.weekday() + 4
    ven = aujourd_hui + timedelta(days=jours)
    return ven, ven + timedelta(days=2)


def ensemble_vent(heures: int) -> dict[datetime, list[tuple]]:
    """Vent des 51 versions de l'ensemble ECMWF : {instant: [(vit, dir), …]}.
    Facultatif : sans lui, la confiance n'est pas calculée."""
    lat, lon = SIOUVILLE["point_vent"]
    try:
        d = P._get_json("https://ensemble-api.open-meteo.com/v1/ensemble", {
            "latitude": lat, "longitude": lon,
            "hourly": "wind_speed_10m,wind_direction_10m",
            "models": "ecmwf_ifs025", "wind_speed_unit": "kn",
            "timezone": P.FUSEAU, "forecast_hours": min(heures, 240)})
    except Exception as e:
        print(f"  ensemble : indisponible ({e})", file=sys.stderr)
        return {}
    h = d.get("hourly", {})
    vits = sorted(k for k in h if k.startswith("wind_speed_10m"))
    res = {}
    for i, t in enumerate(h.get("time", [])):
        membres = []
        for kv in vits:
            kd = kv.replace("wind_speed_10m", "wind_direction_10m")
            v = h[kv][i] if i < len(h[kv]) else None
            dd = h.get(kd, [None] * (i + 1))[i]
            if v is not None:
                membres.append((v, dd))
        res[datetime.fromisoformat(t)] = membres
    return res


def heures_utiles(ven: date, dim: date) -> int:
    fin = datetime.combine(dim, datetime.min.time()) + timedelta(days=1)
    return max(24, int((fin - P.maintenant().replace(tzinfo=None)).total_seconds() // 3600) + 2)


# ---------------------------------------------------------------- analyse

def analyser_jour(jour: date, houle: dict, vent: dict, ens: dict) -> dict:
    lever, coucher = P.soleil_calcule(*SIOUVILLE["point_spot"], jour)
    heures = []
    for k in range(24):
        t = datetime.combine(jour, datetime.min.time()) + timedelta(hours=k)
        if not (lever - timedelta(minutes=30) <= t <= coucher - timedelta(minutes=30)):
            continue
        hh, vv = houle.get(t), vent.get(t)
        if not hh or not vv:
            continue
        orage = P.risque_orage(vv.get("code_meteo"), vv.get("cape"), vv.get("lifted_index"))
        heures.append({
            "instant": t, "hauteur_m": hh["hauteur_m"], "tpeak_s": hh["tpeak_s"],
            "dir_houle": hh["direction_deg"], "vitesse_kt": vv["vitesse_kt"],
            "rafales_kt": vv["rafales_kt"], "dir_vent": vv["direction_deg"],
            "orage": orage,
            "ok": houle_ok(hh) and vent_ok(vv["vitesse_kt"], vv["direction_deg"])
                  and orage != P.ORAGE_VETO,
        })

    # Plus longue suite d'heures bonnes.
    meilleure, cour = [], []
    for h in heures:
        cour = cour + [h] if h["ok"] else []
        if len(cour) > len(meilleure):
            meilleure = list(cour)

    confiance = None
    if meilleure and ens:
        parts = []
        for h in meilleure:
            membres = ens.get(h["instant"]) or []
            if membres:
                parts.append(sum(vent_ok(v, d) for v, d in membres) / len(membres))
        if parts:
            confiance = round(sum(parts) / len(parts), 2)

    affreux = journee_affreuse(heures)
    if not heures:
        # Les modèles ne vont pas encore jusque-là (environ 7 jours).
        statut = "pas encore"
    elif affreux:
        statut = "affreux"
    elif len(meilleure) >= DUREE_MIN_H:
        statut = "bon"
    elif any(houle_ok({"hauteur_m": h["hauteur_m"], "tpeak_s": h["tpeak_s"],
                       "direction_deg": h["dir_houle"]}) for h in heures):
        statut = "venté"          # la houle est là, le vent gâche
    else:
        statut = "trop petit"

    def resume(hs):
        if not hs:
            return None
        n = len(hs)
        return {
            "debut": hs[0]["instant"].strftime("%H:%M"),
            "fin": (hs[-1]["instant"] + timedelta(hours=1)).strftime("%H:%M"),
            "hauteur_m": round(sum(h["hauteur_m"] for h in hs) / n, 2),
            "tpeak_s": round(sum(h["tpeak_s"] for h in hs) / n, 1),
            "dir_houle": round(hs[n // 2]["dir_houle"] or 0),
            "vent_kt": round(max(h["vitesse_kt"] for h in hs)),
            "dir_vent": round(hs[n // 2]["dir_vent"] or 0),
        }

    return {
        "date": jour.isoformat(),
        "nom": f"{JOURS[jour.weekday()]} {jour.day}",
        "statut": statut,
        "raison": affreux,
        "creneau": resume(meilleure) if len(meilleure) >= DUREE_MIN_H else None,
        "confiance": confiance,
        "houle_max_m": round(max((h["hauteur_m"] for h in heures), default=0), 2),
        "vent_max_kt": round(max((h["vitesse_kt"] or 0 for h in heures), default=0)),
        "rafales_max_kt": round(max((h["rafales_kt"] or 0 for h in heures), default=0)),
        "heures": [{
            "h": h["instant"].hour, "houle": round(h["hauteur_m"], 2),
            "t": round(h["tpeak_s"], 1), "vent": round(h["vitesse_kt"]),
            "dv": round(h["dir_vent"] or 0), "ok": h["ok"]} for h in heures],
    }


def verdict(jours: list[dict]) -> tuple[str, float | None]:
    if any(j["statut"] == "pas encore" for j in jours):
        return "PAS ENCORE", None
    bons = [j for j in jours if j["statut"] == "bon"]
    affreux = [j for j in jours if j["statut"] == "affreux"]
    confs = sorted((j["confiance"] for j in bons if j["confiance"] is not None),
                   reverse=True)
    conf = confs[1] if len(confs) >= 2 else (confs[0] if confs else None)
    if affreux:
        # Deux bonnes journées ne rattrapent pas une journée de tempête.
        return "NON", conf
    if len(bons) >= 2:
        if conf is not None and conf < CONFIANCE_GO:
            return "À SURVEILLER", conf
        return "GO", conf
    if len(bons) == 1 and any(j["statut"] == "venté" for j in jours):
        return "À SURVEILLER", conf
    return "NON", conf


# ---------------------------------------------------------------- alerte

def ligne_jour(j: dict) -> str:
    if j["statut"] == "bon":
        c = j["creneau"]
        conf = f", confiance {round(100 * j['confiance'])} %" if j["confiance"] is not None else ""
        return (f"{j['nom'].capitalize()} : bon {c['debut']}–{c['fin']}, "
                f"{c['hauteur_m']:.1f} m à {c['tpeak_s']:.0f} s, vent ≤ {c['vent_kt']} nds{conf}")
    if j["statut"] == "affreux":
        return f"{j['nom'].capitalize()} : à éviter ({j['raison']})"
    if j["statut"] == "venté":
        return f"{j['nom'].capitalize()} : de la houle mais trop de vent ({j['vent_max_kt']} nds)"
    if j["statut"] == "pas encore":
        return f"{j['nom'].capitalize()} : pas encore de prévision"
    return f"{j['nom'].capitalize()} : trop petit ({j['houle_max_m']:.1f} m max)"


def message(res: dict, etat: dict, aujourd_hui: date) -> str:
    """Prévient du lundi au jeudi : à la première annonce d'un GO ou d'un
    « à surveiller », quand le verdict change, et quand un GO est annulé."""
    if aujourd_hui.weekday() > 3:
        return ""
    cle = res["vendredi"]
    avant = etat.get(cle)
    v = res["verdict"]
    if v == "PAS ENCORE" or v == avant or (avant is None and v == "NON"):
        return ""
    if v == "NON":
        tete = "Week-end Siouville : finalement NON"
    elif v == "GO":
        tete = "Week-end Siouville : GO 🌊"
    else:
        tete = "Week-end Siouville : à surveiller"
    return "\n".join([tete] + [ligne_jour(j) for j in res["jours"]])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--essai", action="store_true")
    p.add_argument("--du", help="date du jour simulée (AAAA-MM-JJ), pour tester")
    a = p.parse_args()

    aujourd_hui = date.fromisoformat(a.du) if a.du else P.maintenant().date()
    ven, dim = prochain_weekend(aujourd_hui)
    n = heures_utiles(ven, dim)
    houle = P.recuperer_houle(SIOUVILLE, n)
    vent = P.recuperer_vent(SIOUVILLE, n)
    ens = ensemble_vent(n)
    jours = [analyser_jour(ven + timedelta(days=k), houle, vent, ens) for k in range(3)]
    v, conf = verdict(jours)
    res = {
        "maj": P.maintenant().replace(tzinfo=None).isoformat(timespec="minutes"),
        "vendredi": ven.isoformat(), "dimanche": dim.isoformat(),
        "verdict": v, "confiance": conf,
        "criteres": {"houle_min_m": HOULE_MIN_M, "periode_min_s": PERIODE_MIN_S,
                     "vent_calme_kt": VENT_CALME_KT,
                     "vent_offshore_max_kt": VENT_OFFSHORE_MAX_KT},
        "jours": jours,
    }
    try:
        etat = json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:
        etat = {}
    msg = message(res, etat, aujourd_hui)
    print(f"{ven} → {dim} : {v}" + (f" (confiance {conf})" if conf is not None else ""),
          file=sys.stderr)
    for j in jours:
        print("  " + ligne_jour(j), file=sys.stderr)
    if a.essai:
        print(msg)
        return 0
    SORTIE.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if msg:
        etat[res["vendredi"]] = v
        # On ne garde que les week-ends récents.
        limite = (aujourd_hui - timedelta(days=21)).isoformat()
        etat = {k: x for k, x in etat.items() if k >= limite}
        ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
