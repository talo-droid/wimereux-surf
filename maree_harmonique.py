#!/usr/bin/env python3
"""
maree_harmonique.py — La marée calculée, sans aucun service.

La marée est prévisible des années à l'avance : c'est une somme d'ondes
(l'onde lunaire M2, l'onde solaire S2, etc.) dont seules l'amplitude et la
phase dépendent du port. On les ajuste une fois sur des pleines et basses
mers connues (celles d'api-maree.fr, gardées dans les archives), on les range
dans marees_harmoniques.json, et l'on peut ensuite calculer pleines mers,
basses mers et hauteurs d'eau pour n'importe quelle date, sans réseau.

C'est le dernier recours de previsions.py : quand api-maree.fr ne répond
pas et que la copie préparée ne couvre pas la période, les notes sont
calculées quand même.

Usage :
    python maree_harmonique.py --ajuster            # recalcule les constantes
    python maree_harmonique.py --site calais --du 2027-01-01 --jours 2
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _ZONE = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover
    _ZONE = None

ICI = Path(__file__).parent
FICHIER = ICI / "marees_harmoniques.json"

# Ondes : nombres de Doodson (τ, s, h, p) et déphasage (°). Les ondes
# composées (M4, MS4…) sont des sommes d'ondes simples.
SIMPLES = {
    "M2": ((2, 0, 0, 0), 0), "S2": ((2, 2, -2, 0), 0), "N2": ((2, -1, 0, 1), 0),
    "K2": ((2, 2, 0, 0), 0), "K1": ((1, 1, 0, 0), 90), "O1": ((1, -1, 0, 0), -90),
    "P1": ((1, 1, -2, 0), -90), "Q1": ((1, -2, 0, 1), -90), "MU2": ((2, -2, 2, 0), 0),
    "NU2": ((2, -1, 2, -1), 0), "L2": ((2, 1, 0, -1), 180), "M3": ((3, 0, 0, 0), 180),
    "MSF": ((0, 2, -2, 0), 0),
}
COMPOSEES = {
    "MK3": {"M2": 1, "K1": 1}, "M4": {"M2": 2}, "MS4": {"M2": 1, "S2": 1},
    "MN4": {"M2": 1, "N2": 1}, "M6": {"M2": 3}, "2MS6": {"M2": 2, "S2": 1},
    "2MN6": {"M2": 2, "N2": 1}, "M8": {"M2": 4},
}
# Ondes ajustées sur un mois de données ; les autres sont trop proches d'une
# onde principale pour être séparées sur un mois et en sont déduites (rapport
# d'amplitude du potentiel de marée, même phase).
AJUSTEES = ["M2", "S2", "N2", "K1", "O1", "Q1", "MK3", "M4", "MS4", "MN4",
            "M6", "2MS6", "2MN6"]
# Ondes en plus quand l'historique s'allonge : à chaque recalage, on garde le
# jeu qui prévoit le mieux la dernière semaine sans l'avoir vue.
JEUX = [AJUSTEES, AJUSTEES + ["MU2", "L2"], AJUSTEES + ["MU2", "L2", "MSF", "M3", "M8"]]
DEDUITES = {"K2": ("S2", 0.272), "P1": ("K1", 0.331), "NU2": ("N2", 0.194)}


def _angles(t: datetime):
    """Longitudes moyennes (°) : τ (temps lunaire), s, h, p, et nœud N."""
    j = (t - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400
    T = j / 36525
    s = 218.3164477 + 481267.88123421 * T
    h = 280.46646 + 36000.76983 * T
    p = 83.3532465 + 4069.0137287 * T
    N = 125.04452 - 1934.136261 * T
    ut = t.hour + t.minute / 60 + t.second / 3600 + t.microsecond / 3.6e9
    tau = 15 * ut + 180 + h - s
    return (tau, s, h, p), N


def _nodal(N: float) -> dict:
    """Corrections nodales (cycle de 18,6 ans) : facteur f et phase u (°)."""
    n = math.radians(N)
    c, s_ = math.cos, math.sin
    fm2 = 1.0004 - 0.0373 * c(n) + 0.0002 * c(2 * n)
    um2 = -2.14 * s_(n)
    fk1 = 1.0060 + 0.1150 * c(n) - 0.0088 * c(2 * n) + 0.0006 * c(3 * n)
    uk1 = -8.86 * s_(n) + 0.68 * s_(2 * n) - 0.07 * s_(3 * n)
    fo1 = 1.0089 + 0.1871 * c(n) - 0.0147 * c(2 * n) + 0.0014 * c(3 * n)
    uo1 = 10.80 * s_(n) - 1.34 * s_(2 * n) + 0.19 * s_(3 * n)
    fk2 = 1.0241 + 0.2863 * c(n) + 0.0083 * c(2 * n) - 0.0015 * c(3 * n)
    uk2 = -17.74 * s_(n) + 0.68 * s_(2 * n) - 0.04 * s_(3 * n)
    r = {k: (fm2, um2) for k in ("M2", "N2", "MU2", "NU2", "L2", "MSF")}
    r.update({"S2": (1.0, 0.0), "P1": (1.0, 0.0), "K1": (fk1, uk1), "O1": (fo1, uo1),
              "Q1": (fo1, uo1), "K2": (fk2, uk2), "M3": (fm2 ** 1.5, 1.5 * um2)})
    return r


def _arguments(t: datetime) -> dict:
    """Pour chaque onde : (f, V + u en radians) à l'instant t (UTC)."""
    ang, N = _angles(t)
    nod = _nodal(N)
    out = {}
    for nom, (dood, phase) in SIMPLES.items():
        f, u = nod[nom]
        v = sum(a * b for a, b in zip(dood, ang)) + phase + u
        out[nom] = (f, math.radians(v % 360))
    for nom, comp in COMPOSEES.items():
        f, v = 1.0, 0.0
        for k, n in comp.items():
            f *= out[k][0] ** n
            v += n * out[k][1]
        out[nom] = (f, v)
    return out


def _vers_utc(t: datetime) -> datetime:
    if t.tzinfo is None:
        t = t.replace(tzinfo=_ZONE) if _ZONE else t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


def _vers_local(t: datetime) -> datetime:
    return (t.astimezone(_ZONE) if _ZONE else t).replace(tzinfo=None)


# ---------------------------------------------------------------- calcul

def hauteur(consts: dict, t: datetime) -> float:
    """Hauteur d'eau (m, zéro des cartes) ; t naïf = heure de Paris."""
    arg = _arguments(_vers_utc(t))
    h = consts["Z0"]
    ondes = dict(consts["ondes"])
    for nom, (mere, r) in DEDUITES.items():
        if mere in ondes and nom not in ondes:
            ondes[nom] = [ondes[mere][0] * r, ondes[mere][1]]
    for nom, (H, g) in ondes.items():
        f, vu = arg[nom]
        h += f * H * math.cos(vu - math.radians(g))
    return h


def hauteurs(consts: dict, depuis: datetime, jusqu_a: datetime, pas_min: int = 30) -> dict:
    out = {}
    t = depuis.replace(minute=(depuis.minute // pas_min) * pas_min, second=0, microsecond=0)
    while t <= jusqu_a:
        out[t] = round(hauteur(consts, t), 3)
        t += timedelta(minutes=pas_min)
    return out


def extrema(consts: dict, depuis: datetime, jusqu_a: datetime) -> list[dict]:
    """Pleines et basses mers entre deux instants (heure de Paris, naïves),
    au format d'api-maree.fr : instant, type PM/BM, hauteur_m, coef."""
    pas = timedelta(minutes=10)
    t0 = depuis - timedelta(hours=1)
    pts = []
    t = t0
    while t <= jusqu_a + timedelta(hours=16):
        pts.append((t, hauteur(consts, t)))
        t += pas
    out = []
    for i in range(1, len(pts) - 1):
        (ta, a), (tb, b), (tc, c) = pts[i - 1], pts[i], pts[i + 1]
        if (b > a and b >= c) or (b < a and b <= c):
            # Sommet de la parabole par les trois points, affiné au plus près.
            den = a - 2 * b + c
            x = 0.5 * (a - c) / den if den else 0.0
            ti = tb + x * pas
            hi = hauteur(consts, ti)
            if ti >= depuis:
                out.append({"instant": ti.replace(second=0, microsecond=0),
                            "type": "PM" if b > a else "BM", "hauteur_m": round(hi, 3)})
    # Coefficient de marée des pleines mers : il se calcule à Brest, où la
    # marée a une demi-journée d'avance ; il suit donc le marnage local de la
    # pleine mer SUIVANTE, presque en ligne droite (droite calée à l'ajustement).
    a_b = consts.get("coef_marnage")
    for i, e in enumerate(out):
        e["coef"] = None
        if e["type"] == "PM" and a_b:
            m = _marnage_suivant(out, i)
            if m is not None:
                e["coef"] = max(20, min(120, int(round(a_b[0] * m + a_b[1]))))
    out = [e for e in out if e["instant"] <= jusqu_a]
    return out


def _marnage_suivant(liste: list[dict], i: int):
    """Marnage de la pleine mer qui suit la n° i (avec ses basses mers)."""
    for j in range(i + 1, min(i + 4, len(liste))):
        if liste[j]["type"] == "PM":
            bm = [x["hauteur_m"] for x in liste[j - 1:j + 2] if x["type"] == "BM"]
            if len(bm) == 2:
                return liste[j]["hauteur_m"] - sum(bm) / 2
            return None
    return None


# ---------------------------------------------------------------- ajustement

def _base(t: datetime, noms: list) -> list:
    """Colonnes du modèle linéaire : 1, puis (cos, sin) de chaque onde ajustée
    (les ondes déduites s'ajoutent aux colonnes de leur onde mère)."""
    arg = _arguments(t)
    ligne = [1.0]
    for nom in noms:
        f, vu = arg[nom]
        c, s = f * math.cos(vu), f * math.sin(vu)
        for fille, (mere, r) in DEDUITES.items():
            if mere == nom:
                ff, vv = arg[fille]
                c += r * ff * math.cos(vv)
                s += r * ff * math.sin(vv)
        ligne += [c, s]
    return ligne


def _moindres_carres(A: list, b: list) -> list:
    n = len(A[0])
    M = [[sum(r[i] * r[j] for r in A) for j in range(n)] for i in range(n)]
    v = [sum(r[i] * y for r, y in zip(A, b)) for i in range(n)]
    for i in range(n):
        M[i][i] += 1e-9
    for i in range(n):  # Gauss avec pivot partiel
        p = max(range(i, n), key=lambda k: abs(M[k][i]))
        M[i], M[p], v[i], v[p] = M[p], M[i], v[p], v[i]
        for k in range(i + 1, n):
            q = M[k][i] / M[i][i]
            for j in range(i, n):
                M[k][j] -= q * M[i][j]
            v[k] -= q * v[i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (v[i] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def ajuster(points: list[tuple[datetime, float]], noms=AJUSTEES) -> dict:
    """Ajuste les ondes sur des pleines/basses mers (instant local, hauteur).
    Deux équations par extremum : la hauteur, et une pente nulle."""
    A, b = [], []
    dt = timedelta(minutes=5)
    for t, h in points:
        tu = _vers_utc(t)
        A.append(_base(tu, noms))
        b.append(h)
        b1, b2 = _base(tu + dt, noms), _base(tu - dt, noms)
        # Pente en m/h ; poids 1 : 10 min d'erreur sur l'heure ≈ 15 cm.
        A.append([(x - y) / (2 * dt.total_seconds() / 3600) for x, y in zip(b1, b2)])
        b.append(0.0)
    x = _moindres_carres(A, b)
    ondes = {}
    for i, nom in enumerate(noms):
        c, s = x[1 + 2 * i], x[2 + 2 * i]
        ondes[nom] = [round(math.hypot(c, s), 4), round(math.degrees(math.atan2(s, c)) % 360, 2)]
    return {"Z0": round(x[0], 4), "ondes": ondes}


def _extrema_archives(cle: str) -> tuple[str, dict]:
    """Toutes les pleines/basses mers publiées pour un spot (archives et
    dernière prévision), venues d'api-maree.fr."""
    vus, site = {}, None
    fichiers = sorted(glob.glob(str(ICI / "archives" / "*.json"))) + [str(ICI / "docs" / "data.json")]
    for f in fichiers:
        try:
            spots = json.loads(Path(f).read_text(encoding="utf-8"))["spots"]
        except Exception:
            continue
        for sp in spots:
            if sp.get("cle") != cle:
                continue
            site = sp.get("site_maree") or site
            for e in sp.get("marees") or []:
                if e.get("calcule"):
                    continue  # nos propres calculs : on n'apprend pas sur soi-même
                vus[e["instant"]] = e
    # La copie préparée par la tâche « Marées », si elle existe.
    try:
        cache = json.loads((ICI / "marees_cache.json").read_text(encoding="utf-8"))
        for k, v in cache.get(site, {}).get("extrema", {}).items():
            vus.setdefault(k, {**v, "instant": k})
    except Exception:
        pass
    return site, vus


def _ecarts(c: dict, pts: list) -> tuple[float, float]:
    """Écart moyen (cm, min) entre le calcul et des pleines/basses mers."""
    calc = extrema(c, pts[0][0] - timedelta(hours=3), pts[-1][0] + timedelta(hours=3))
    eh, et = [], []
    for t, h in pts:
        p = min(calc, key=lambda e: abs(e["instant"] - t))
        eh.append(abs(p["hauteur_m"] - h))
        et.append(abs((p["instant"] - t).total_seconds()) / 60)
    return 100 * sum(eh) / len(eh), sum(et) / len(et)


def _meilleur_jeu(pts: list) -> list:
    """Le jeu d'ondes qui prévoit le mieux la dernière semaine, ajusté sur le
    reste (10 min d'erreur comptent comme 10 cm)."""
    coupe = pts[-1][0] - timedelta(days=7)
    appris = [p for p in pts if p[0] < coupe]
    test = [p for p in pts if p[0] >= coupe]
    if len(appris) < 50 or len(test) < 8:
        return AJUSTEES
    def cout(noms):
        h, m = _ecarts(ajuster(appris, noms), test)
        return h + m
    return min(JEUX, key=cout)


def recalculer(cles=("wimereux", "calais")) -> dict:
    res = {}
    for cle in cles:
        site, vus = _extrema_archives(cle)
        if not site or len(vus) < 50:
            print(f"{cle} : trop peu de pleines/basses mers ({len(vus)})", file=sys.stderr)
            continue
        pts = [(datetime.fromisoformat(k), v["hauteur_m"]) for k, v in sorted(vus.items())]
        c = ajuster(pts, _meilleur_jeu(pts))
        # Coefficient en fonction du marnage local de la pleine mer suivante :
        # droite des moindres carrés sur les coefficients publiés.
        ext = [{**v, "instant": k} for k, v in sorted(vus.items())]
        xy = []
        for i, v in enumerate(ext):
            if v.get("type") == "PM" and v.get("coef"):
                m = _marnage_suivant(ext, i)
                if m is not None:
                    xy.append((m, v["coef"]))
        if len(xy) > 10:
            a, b = _moindres_carres([[x, 1.0] for x, _ in xy], [y for _, y in xy])
            c["coef_marnage"] = [round(a, 3), round(b, 2)]
        c["calees_sur"] = f"{pts[0][0]:%Y-%m-%d} → {pts[-1][0]:%Y-%m-%d}, {len(pts)} pleines/basses mers"
        # Écart sur les données d'ajustement, pour mémoire.
        h, m = _ecarts(c, pts)
        c["ecart_moyen"] = {"hauteur_cm": round(h, 1), "heure_min": round(m, 1)}
        res[site] = c
        print(f"{cle} ({site}) : {c['calees_sur']} — écart moyen "
              f"{c['ecart_moyen']['hauteur_cm']} cm, {c['ecart_moyen']['heure_min']} min",
              file=sys.stderr)
    return res


def charger(site: str) -> dict | None:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8")).get(site)
    except Exception:
        return None


def main_ajuster() -> int:
    res = recalculer()
    if not res:
        return 1
    ancien = {}
    try:
        ancien = json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        pass
    ancien.update(res)
    FICHIER.write_text(json.dumps(ancien, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ajuster", action="store_true")
    p.add_argument("--site", default="boulogne-sur-mer")
    p.add_argument("--du")
    p.add_argument("--jours", type=int, default=2)
    a = p.parse_args()
    if a.ajuster:
        return main_ajuster()
    c = charger(a.site)
    if not c:
        print("pas de constantes : lancer --ajuster", file=sys.stderr)
        return 1
    d = datetime.fromisoformat(a.du) if a.du else datetime.now().replace(minute=0, second=0, microsecond=0)
    for e in extrema(c, d, d + timedelta(days=a.jours)):
        print(f"{e['instant']:%a %d/%m %H:%M}  {e['type']}  {e['hauteur_m']:.2f} m"
              + (f"  coef {e['coef']}" if e["coef"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
