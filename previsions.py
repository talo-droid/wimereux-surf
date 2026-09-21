#!/usr/bin/env python3
"""
previsions.py — Notation des sessions de surf à Wimereux et à Calais.

Trois notes sur 5 (houle, marée, vent) plus une note globale, enrichies par
quatre apports de la littérature sur les plages macrotidales à barres et
bâches, dont fait partie la Côte d'Opale :

  - Nombre d'Iribarren (Battjes 1974) : type de déferlement, à partir de la
    cambrure et de la pente locale, laquelle varie avec le niveau de marée.
  - Vitesse de translation de la marée : sur une plage large de plusieurs
    centaines de mètres, la zone de déferlement se déplace vite à mi-marée et
    stationne près des étales. Elle dépend du marnage, donc du coefficient.
  - Amplitude de marée relative RTR = marnage / Hb (Masselink & Short 1993) :
    au-delà de ~8, la plage devient dominée par la marée plutôt que par les
    vagues, et la zone de surf se définit mal.
  - Fetch limité du détroit (croissance JONSWAP) : la période maximale que le
    vent local peut produire dans sa direction. Si la mer observée n'excède
    pas cette limite, il n'y a pas de houle venue d'ailleurs, juste du clapot.

Le courant de marée est calculé et affiché à part, en bonus, sans entrer dans
la note : son effet sur la qualité reste une hypothèse à valider par le journal.

Les deux spots ne se ressemblent pas : Wimereux regarde l'ouest-nord-ouest et
marche sur la houle d'ouest-sud-ouest une heure après la pleine mer ; Calais
regarde le nord, marche sur la houle de nord et au montant avant la pleine
mer. Chacun a donc sa bouée, sa fenêtre de direction, son optimum de marée,
ses secteurs de vent et sa table de fetch — tout est dans SPOTS ci-dessous.

Sources : Open-Meteo (houle, vent, courant), api-maree.fr (marée, clé requise
dans API_MAREE_KEY).

Usage :
    python previsions.py                          # les deux spots, console
    python previsions.py --spot calais            # un seul
    python previsions.py --json docs/data.json    # export pour la page web
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from bisect import bisect_left
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _ZONE = ZoneInfo("Europe/Paris")
except Exception:          # tzdata absent : on retombe sur l'horloge système
    _ZONE = None


def maintenant():
    """
    Heure locale française, quel que soit le fuseau de la machine. Les
    serveurs GitHub tournent en temps universel : sans ça, l'horodatage
    publié serait en retard d'une à deux heures selon la saison.
    """
    return datetime.now(_ZONE) if _ZONE else datetime.now()

# ==========================================================================
# CONFIGURATION DES SPOTS
# ==========================================================================
#
# Chaque spot a sa propre bouée de référence, sa fenêtre de houle, son
# optimum de marée et sa table de fetch. Wimereux regarde l'ouest-nord-ouest
# et marche sur la houle d'ouest-sud-ouest ; Calais regarde le nord et marche
# sur la houle de nord, au montant avant la pleine mer.
#
# fetch_km : fetch approximatif en kilomètres selon la direction D'OÙ vient
# le vent. À affiner sur une carte — c'est la donnée la plus grossière ici.

SPOTS = {
    "wimereux": {
        "nom": "Wimereux",
        # Bouée CEFAS HASTINGSWN. Vérifie la position exacte en haut de la
        # page WaveNet ("The wave conditions at ...").
        "bouee": "Hastings",
        "point_houle": (50.80, 0.65),
        "point_spot": (50.7683, 1.6086),
        # Vent pris un peu au large : une maille de 1,5 à 2 km posée sur le
        # trait de côte mélange terre et mer, et la rugosité du sol freine le
        # vent calculé à 10 m. À vérifier : le point doit tomber en mer.
        "point_vent": (50.7700, 1.5800),
        "point_courant": (50.79, 1.55),
        "site_maree": os.environ.get("SITE_MAREE_WIMEREUX", "boulogne-sur-mer"),
        # Fenêtre de direction de houle : hors de là, la note tombe à zéro.
        "direction_houle": (200.0, 270.0),
        # Optimum de marée, en heures par rapport à la pleine mer.
        # Positif = après la PM.
        "pic_maree_h": 1.0,
        # La terre est à l'est : offshore de l'est-sud-est au sud-sud-ouest.
        "secteur_favorable": (110.0, 225.0),
        "secteur_travers": [(80.0, 110.0), (225.0, 260.0)],
        "pente_haute": 0.035,
        "pente_basse": 0.010,
        "fetch_km": {
            0: 300, 22: 250, 45: 150, 67: 40, 90: 3, 112: 3, 135: 3, 157: 20,
            180: 85, 202: 180, 225: 400, 247: 500, 270: 90, 292: 80,
            315: 90, 337: 180,
        },
        # Liens affichés en haut de la page, pour vérifier la prévision
        # contre la mesure et contre l'œil.
        "liens": {
            "bouee": "https://wavenet.cefas.co.uk/details/HASTINGSWN/INT",
            "webcam": "https://www.youtube.com/watch?v=vBqzSfNFq-k",
            "previsions": "https://www.windguru.cz/48354",
        },
    },
    "calais": {
        "nom": "Calais",
        # Bateau-feu Sandettie, au nord-est du détroit. Position approximative,
        # à vérifier sur la fiche de la station.
        "bouee": "Sandettie",
        "point_houle": (51.15, 1.79),
        "point_spot": (50.9700, 1.8500),
        "point_vent": (50.9850, 1.8400),
        "point_courant": (51.00, 1.83),
        "site_maree": os.environ.get("SITE_MAREE_CALAIS", "calais"),
        # La plage regarde le nord : fenêtre à cheval sur 0°, du nord-ouest
        # au nord-est.
        "direction_houle": (300.0, 60.0),
        # Marche au montant, avant la pleine mer.
        "pic_maree_h": -1.5,
        # La terre est au sud : offshore du sud-est au sud-ouest.
        "secteur_favorable": (135.0, 225.0),
        "secteur_travers": [(100.0, 135.0), (225.0, 260.0)],
        "pente_haute": 0.035,
        "pente_basse": 0.010,
        "fetch_km": {
            0: 300, 22: 250, 45: 200, 67: 120, 90: 80, 112: 10, 135: 3,
            157: 3, 180: 3, 202: 3, 225: 5, 247: 25, 270: 35, 292: 90,
            315: 150, 337: 250,
        },
        "liens": {
            "bouee": "https://www.ndbc.noaa.gov/station_page.php"
                     "?station=62304&uom=M&tz=STN",
            "webcam": "https://www.vision-environnement.com/it/webcam/francia/"
                      "hauts-de-france/1241-sangatte/",
            "previsions": "https://www.windguru.cz/48349",
        },
    },
}

FUSEAU = "Europe/Paris"
CLE_MAREE = os.environ.get("API_MAREE_KEY", "")

# --- Houle : barème commun aux deux spots --------------------------------
# Hauteur : montée progressive plutôt qu'un palier. En dessous du minimum la
# note de houle est nulle (pas surfable) ; entre les deux bornes les 3 points
# de hauteur s'acquièrent linéairement ; au-dessus ils sont pleins.
# Un palier faisait basculer 3 points sur deux centimètres, bien en deçà de la
# précision du modèle.
HAUTEUR_NULLE_M = 0.50     # en dessous : rien à surfer, note 0
HAUTEUR_MIN_M = 0.70       # début des points de hauteur
HAUTEUR_PLEINE_M = 1.00    # les 3 points de hauteur sont acquis
POINTS_HAUTEUR_MAX = 3.0
# Entre HAUTEUR_NULLE_M et HAUTEUR_MIN_M, toute la note de houle est atténuée
# progressivement, pour qu'aucune marche brutale ne subsiste au bas du barème.
SEUIL_TPEAK_1 = 6.0
SEUIL_TPEAK_2 = 7.0
CALIBRATION_HOULE = 1.0

# --- Nombre d'Iribarren ---------------------------------------------------
# Battjes place la limite glissant/plongeant à 0,5. Sur ces plages
# dissipatives xi reste presque toujours en dessous : les seuils ci-dessous
# sont RELATIFS au site, pas les seuils universels.
XI_MOU = 0.15
XI_FRANC = 0.32

# --- Vitesse de translation de la marée, en mètres par minute ------------
TRANSLATION_LENTE = 0.6
TRANSLATION_RAPIDE = 2.2

# --- Amplitude de marée relative (RTR) -----------------------------------
RTR_NEUTRE = 8.0
RTR_SEVERE = 20.0
PENALITE_RTR_MAX = 0.25

# --- Vent -----------------------------------------------------------------
SEUIL_RAFALES_KT = 10.0

# Modèles de vent à haute résolution, du préféré au moins préféré. Les deux
# ne couvrent qu'environ deux jours ; au-delà, on relaie sur les suivants.
#   AROME HD : Météo-France, ~1,5 km, jusqu'à ~42 h
#   UKV      : Met Office, ~2 km, jusqu'à ~48 h, très bon sur la Manche
# Le Met Office fait tourner l'UKV jusqu'à 120 h, mais Open-Meteo n'en
# redistribue que 48. Au-delà, on relaie par le global du Met Office : même
# physique que l'UKV, donc une prévision cohérente de bout en bout.
MODELES_VENT = ["meteofrance_arome_france_hd", "ukmo_uk_deterministic_2km"]
MODELES_VENT_RELAIS = ["ukmo_global_deterministic_10km",
                       "meteofrance_arpege_europe", "best_match"]
NOMS_MODELES = {
    "meteofrance_arome_france_hd": "AROME HD",
    "ukmo_uk_deterministic_2km": "UKV",
    "ukmo_global_deterministic_10km": "UKMO Global",
    "meteofrance_arpege_europe": "ARPEGE",
    "best_match": "Open-Meteo",
}
# "moyenne" : moyenne d'AROME HD et d'UKV quand les deux existent — deux
#             modèles fins indépendants font en général mieux qu'un seul ;
# "arome"   : AROME HD d'abord, UKV en secours ;
# "ukv"     : l'inverse.
MODE_VENT = os.environ.get("MODE_VENT", "moyenne")
# Écart entre AROME et UKV au-delà duquel on signale une prévision incertaine.
ECART_VENT_ALERTE_KT = 5.0

# --- Courant (bonus, hors note) ------------------------------------------
COURANT_SEUIL_KT = 0.4
COURANT_OPPOSE_DEFAVORABLE = True

# --- Orage ----------------------------------------------------------------
CODES_ORAGE = {95, 96, 99}
CAPE_FAIBLE, CAPE_MODEREE, CAPE_FORTE = 150.0, 400.0, 1000.0
LI_MODERE, LI_FORT = -2.0, -4.0
HALO_ORAGE_H = 2
NIVEAUX_ORAGE = ["nul", "faible", "modéré", "élevé"]
ORAGE_VETO = "élevé"
ORAGE_PLAFOND_NOTE = 2.5

# --- Note globale ---------------------------------------------------------
POIDS = {"houle": 0.50, "vent": 0.30, "maree": 0.20}
POIDS_MAREE = {"position": 0.6, "stabilite": 0.4}

G = 9.81

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janv.", "févr.", "mars", "avril", "mai", "juin",
           "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def date_fr(d) -> str:
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]}"


# ==========================================================================
# GRANDEURS PHYSIQUES
# ==========================================================================

def energie_houle(hauteur_m, periode_s) -> float:
    """
    Flux d'énergie, en kW/m de crête — le "kJ" des sites de surf, un kW/m
    valant un kJ par seconde et par mètre.  P = rho g² / (64 pi) Hs² T.
    La puissance croît avec le carré de la hauteur mais seulement
    linéairement avec la période.
    """
    if not hauteur_m or not periode_s:
        return 0.0
    return round(0.49 * hauteur_m ** 2 * periode_s, 1)


def pente_locale(sp, fraction_maree: float) -> float:
    """
    Pente de l'estran au niveau d'eau courant. fraction_maree vaut 0 à basse
    mer et 1 à pleine mer. Sur une plage à barres et bâches, la pente augmente
    vers le haut de plage : c'est pourquoi le déferlement change de nature au
    cours de la marée, à houle constante.
    """
    f = max(0.0, min(1.0, fraction_maree))
    return sp["pente_basse"] + (sp["pente_haute"] - sp["pente_basse"]) * f


def iribarren(hauteur_m, periode_s, pente) -> float:
    """
    Nombre d'Iribarren (surf similarity parameter), xi = pente / sqrt(H/L0)
    avec L0 = g T² / 2pi la longueur d'onde en eau profonde.
    Bas = déferlement glissant et mou ; haut = plongeant et franc.
    """
    if not hauteur_m or not periode_s or hauteur_m <= 0:
        return 0.0
    L0 = G * periode_s ** 2 / (2 * math.pi)
    cambrure = hauteur_m / L0
    if cambrure <= 0:
        return 0.0
    return round(pente / math.sqrt(cambrure), 3)


def fetch_pour(sp, direction_deg: float) -> float:
    """Fetch en mètres pour la direction d'où vient le vent, interpolé."""
    table = sp["fetch_km"]
    d = direction_deg % 360
    cles = sorted(table)
    for i, c in enumerate(cles):
        if d < c:
            c0, c1 = cles[i - 1], c
            break
    else:
        c0, c1 = cles[-1], cles[0] + 360
    f0, f1 = table[c0 % 360], table[c1 % 360]
    t = (d - c0) / max(1e-6, (c1 - c0))
    return (f0 + (f1 - f0) * t) * 1000.0


def mer_levee_localement(sp, vitesse_kt, direction_deg):
    """
    Hauteur et période que le vent local peut produire, d'après les lois de
    croissance JONSWAP en fetch limité :
        g Hs / U² = 0.0016 (g F / U²)^0.5
        g Tp / U  = 0.286  (g F / U²)^(1/3)
    Sert de référence : si la mer observée ne dépasse pas ces valeurs, elle
    s'explique entièrement par le vent du moment, sans houle venue d'ailleurs.
    """
    if not vitesse_kt or vitesse_kt <= 0:
        return 0.0, 0.0
    U = vitesse_kt * 0.514444
    F = fetch_pour(sp, direction_deg)
    if F <= 0:
        return 0.0, 0.0
    F_adim = G * F / U ** 2
    hs = 0.0016 * math.sqrt(F_adim) * U ** 2 / G
    tp = 0.286 * F_adim ** (1 / 3) * U / G
    return round(hs, 2), round(tp, 1)


# ==========================================================================
# NOTATION
# ==========================================================================

def score_houle(sp, hauteur_m, tpeak_s, direction_deg, xi=None, mer_locale=False):
    """
    Barème de base : jusqu'à 3 points de hauteur, acquis progressivement
    entre HAUTEUR_MIN_M et HAUTEUR_PLEINE_M, plus 1 point si Tpeak dépasse
    6 s ou 2 points au-delà de 7 s. La direction est un véto ; une hauteur
    sous HAUTEUR_NULLE_M en est un second, et la zone juste au-dessus est
    atténuée pour que la note monte sans à-coup.

    Puis deux corrections :
      - mer entièrement explicable par le vent local : -1 (du clapot, pas
        de la houle, même à hauteur correcte) ;
      - déferlement franc (Iribarren élevé) : +1 ; mer molle : -1.
    """
    if hauteur_m is None or tpeak_s is None or direction_deg is None:
        return 0

    # _dans_secteur gère la fenêtre à cheval sur 0°, comme celle de Calais.
    if not _dans_secteur(direction_deg, *sp["direction_houle"]):
        return 0

    hs = hauteur_m * CALIBRATION_HOULE
    if hs <= HAUTEUR_NULLE_M:
        return 0.0        # rien à surfer, quelle que soit la période

    rampe = (hs - HAUTEUR_MIN_M) / (HAUTEUR_PLEINE_M - HAUTEUR_MIN_M)
    points = POINTS_HAUTEUR_MAX * max(0.0, min(1.0, rampe))

    if tpeak_s > SEUIL_TPEAK_2:
        points += 2
    elif tpeak_s > SEUIL_TPEAK_1:
        points += 1

    if mer_locale:
        points -= 1
    if xi is not None:
        if xi >= XI_FRANC:
            points += 1
        elif xi < XI_MOU:
            points -= 1

    points = max(0.0, min(points, 5.0))

    # Atténuation dans la zone basse, pour éviter une marche à HAUTEUR_MIN_M.
    if hs < HAUTEUR_MIN_M:
        points *= (hs - HAUTEUR_NULLE_M) / (HAUTEUR_MIN_M - HAUTEUR_NULLE_M)

    return round(points, 2)


def _dans_secteur(direction, debut, fin) -> bool:
    direction, debut, fin = direction % 360, debut % 360, fin % 360
    if debut <= fin:
        return debut <= direction <= fin
    return direction >= debut or direction <= fin


def categorie_vent(sp, direction_deg: float) -> str:
    if _dans_secteur(direction_deg, *sp["secteur_favorable"]):
        return "offshore"
    for debut, fin in sp["secteur_travers"]:
        if _dans_secteur(direction_deg, debut, fin):
            return "travers"
    return "onshore"


def score_vent(sp, vitesse_kt, direction_deg, rafales_kt=None) -> int:
    """
        vitesse      offshore   travers   onshore
        < 5 nds         5          5         5
        5-10 nds        5          3         2
        10-15 nds       3          2         1
        15-20 nds       2          1         1
        > 20 nds        1          1         1
    Puis -1 si les rafales dépassent la moyenne de plus de 10 nds.
    """
    if vitesse_kt is None or direction_deg is None:
        return 1
    if vitesse_kt < 5:
        note = 5
    else:
        cat = categorie_vent(sp, direction_deg)
        if vitesse_kt < 10:
            note = {"offshore": 5, "travers": 3, "onshore": 2}[cat]
        elif vitesse_kt <= 15:
            note = {"offshore": 3, "travers": 2, "onshore": 1}[cat]
        elif vitesse_kt <= 20:
            note = {"offshore": 2, "travers": 1, "onshore": 1}[cat]
        else:
            note = 1
    if rafales_kt is not None and rafales_kt - vitesse_kt > SEUIL_RAFALES_KT:
        note -= 1
    return max(1, min(note, 5))


ANCRAGES_MAREE = [(-1.0, 1.0), (-0.5, 3.0), (0.5, 3.0), (1.0, 1.0)]


def score_position_maree(sp, heures_depuis_pm, duree_demi_cycle_h=6.2) -> float:
    """
    Position dans le cycle. L'optimum n'est pas au même endroit selon le
    spot : une heure APRÈS la pleine mer à Wimereux, une heure et demie
    AVANT à Calais, qui marche au montant.
    """
    if duree_demi_cycle_h <= 0:
        return 1.0
    x = max(-1.0, min(1.0, heures_depuis_pm / duree_demi_cycle_h))
    pic = sp["pic_maree_h"] / duree_demi_cycle_h
    fraction_pic = max(-0.45, min(0.45, pic))
    ancrages = sorted(ANCRAGES_MAREE + [(fraction_pic, 5.0)])
    xs = [a for a, _ in ancrages]
    ys = [b for _, b in ancrages]
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_left(xs, x)
    return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])


def translation_m_min(dh_dt_m_h, pente) -> float:
    """
    Vitesse de déplacement horizontal du bord de l'eau. Sur un estran de
    plusieurs centaines de mètres, elle atteint quelques mètres par minute à
    mi-marée de vive-eau : la zone de déferlement ne stationne alors au-dessus
    d'aucune barre. Près des étales elle tend vers zéro.
    """
    if pente <= 0:
        return 0.0
    return round(abs(dh_dt_m_h) / pente / 60.0, 2)


def score_stabilite(vitesse_m_min: float) -> float:
    """5 quand la zone de surf stationne, 1 quand elle balaie le profil."""
    if vitesse_m_min <= TRANSLATION_LENTE:
        return 5.0
    if vitesse_m_min >= TRANSLATION_RAPIDE:
        return 1.0
    t = (vitesse_m_min - TRANSLATION_LENTE) / (TRANSLATION_RAPIDE - TRANSLATION_LENTE)
    return round(5.0 - 4.0 * t, 2)


def score_maree(position: float, stabilite: float) -> float:
    return round(position * POIDS_MAREE["position"]
                 + stabilite * POIDS_MAREE["stabilite"], 2)


def facteur_rtr(marnage_m, hauteur_m) -> float:
    """
    RTR = marnage / hauteur de houle. Plus il est élevé, plus la plage est
    dominée par la marée et moins la zone de surf se définit. Un même mètre
    de houle ne vaut pas la même chose un jour de coefficient 40 et un jour
    de coefficient 110.
    """
    if not marnage_m or not hauteur_m or hauteur_m <= 0:
        return 1.0
    rtr = marnage_m / hauteur_m
    if rtr <= RTR_NEUTRE:
        return 1.0
    t = min(1.0, (rtr - RTR_NEUTRE) / (RTR_SEVERE - RTR_NEUTRE))
    return round(1.0 - PENALITE_RTR_MAX * t, 3)


def note_globale(houle, maree, vent, facteur=1.0, orage="nul") -> float:
    """
    Trois vétos, dans l'ordre : l'orage d'abord, parce que c'est le seul qui
    relève de la sécurité et non du confort ; puis la houle nulle ; puis un
    vent très défavorable, qui plafonne la note à vent + 1.
    Le facteur RTR s'applique en dernier.
    """
    if orage == ORAGE_VETO:
        return 0.0
    if houle == 0:
        return 0.0
    note = houle * POIDS["houle"] + vent * POIDS["vent"] + maree * POIDS["maree"]
    if vent <= 2:
        note = min(note, vent + 1)
    note *= facteur
    if orage == "modéré":
        note = min(note, ORAGE_PLAFOND_NOTE)
    return round(note, 2)


def risque_orage(code_meteo, cape, lifted_index) -> str:
    """
    Niveau de risque orageux pour une heure donnée, à partir du code météo
    WMO et de deux indices d'instabilité. Le code météo prime : s'il annonce
    un orage, le risque est élevé quelles que soient les autres valeurs.
    """
    if code_meteo is not None and int(code_meteo) in CODES_ORAGE:
        return "élevé"

    niveau = "nul"
    if cape is not None:
        if cape >= CAPE_FORTE:
            niveau = "élevé"
        elif cape >= CAPE_MODEREE:
            niveau = "modéré"
        elif cape >= CAPE_FAIBLE:
            niveau = "faible"
    if lifted_index is not None:
        if lifted_index <= LI_FORT:
            niveau = "élevé"
        elif lifted_index <= LI_MODERE and niveau in ("nul", "faible"):
            niveau = "modéré"
    return niveau


def propager_orage(risques: dict) -> dict:
    """
    Étend le risque aux heures voisines : un orage à 15h rend 13h et 17h
    imprudents aussi, parce que les cellules se déplacent et que la foudre
    précède souvent la pluie.
    """
    etendu = dict(risques)
    for instant, niveau in risques.items():
        if niveau != "élevé":
            continue
        for delta in range(-HALO_ORAGE_H, HALO_ORAGE_H + 1):
            voisin = instant + timedelta(hours=delta)
            if voisin in etendu and NIVEAUX_ORAGE.index(etendu[voisin]) < 2:
                etendu[voisin] = "modéré"
    return etendu


def effet_courant(vitesse_kt, direction_vers_deg, dir_houle_deg):
    """
    Angle entre le courant et le sens de propagation de la houle.
    0° : le courant porte la houle (mer aplanie). 180° : il s'y oppose
    (mer raccourcie et cabrée). Renvoie (libellé, angle).

    Convention : la direction du courant est celle VERS laquelle il va,
    celle de la houle celle d'où elle vient — d'où le +180.
    """
    if not vitesse_kt or vitesse_kt < COURANT_SEUIL_KT or direction_vers_deg is None:
        return "négligeable", None
    houle_vers = (dir_houle_deg + 180) % 360
    ecart = abs((direction_vers_deg - houle_vers + 180) % 360 - 180)
    if ecart <= 45:
        sens = "portant"
    elif ecart >= 135:
        sens = "opposé"
    else:
        sens = "travers"
    if sens == "travers":
        effet = "neutre"
    elif sens == "opposé":
        effet = "défavorable" if COURANT_OPPOSE_DEFAVORABLE else "favorable"
    else:
        effet = "favorable" if COURANT_OPPOSE_DEFAVORABLE else "défavorable"
    return f"{sens} · {effet}", round(ecart)


# ==========================================================================
# RÉCUPÉRATION
# ==========================================================================

# Attentes entre deux tentatives, en secondes. Trois essais au total.
ATTENTES_RESEAU = [3, 10]


def _get_json(url: str, params: dict) -> dict:
    """
    Appel HTTP avec nouvelles tentatives. Une coupure réseau passagère
    (délai dépassé, service surchargé) ne doit pas faire tomber tout un
    spot : on réessaie deux fois en espaçant. Une erreur de requête (4xx,
    hors 429), elle, ne se corrigera pas en réessayant — on abandonne tout
    de suite.
    """
    import time
    import urllib.error

    requete = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "wimereux-surf/1.0"},
    )
    hote = urllib.parse.urlparse(url).netloc
    derniere = None
    for tentative, attente in enumerate([0] + ATTENTES_RESEAU):
        if attente:
            print(f"  {hote} : nouvel essai dans {attente} s ({derniere})",
                  file=sys.stderr)
            time.sleep(attente)
        try:
            with urllib.request.urlopen(requete, timeout=45) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                raise RuntimeError(f"{hote} a refusé la requête ({e.code})") from e
            derniere = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            derniere = str(getattr(e, "reason", e))
    # Le nom du service dans le message : on sait tout de suite qui a flanché.
    raise RuntimeError(f"{hote} injoignable après 3 essais ({derniere})")


def _premier_non_nul(*valeurs):
    for v in valeurs:
        if v is not None:
            return v
    return None


def recuperer_houle(sp, heures: int) -> dict[datetime, dict]:
    """
    Mer TOTALE (wave_*), c'est-à-dire mer du vent et houle longue combinées :
    c'est ce que publie la bouée dans ses colonnes Sig. wave height, Tpeak et
    Peak direction. EWAM (~5 km) d'abord, GWAM (~25 km) au-delà de 4 jours ;
    l'écart entre les deux mesure la fiabilité du créneau.
    """
    champs = ["wave_height", "wave_peak_period", "wave_period", "wave_direction",
              "swell_wave_height", "swell_wave_peak_period"]
    lat, lon = sp["point_houle"]
    donnees = _get_json(
        "https://marine-api.open-meteo.com/v1/marine",
        {"latitude": lat, "longitude": lon, "hourly": ",".join(champs),
         "models": "ewam,gwam", "timezone": FUSEAU,
         "forecast_hours": min(heures, 168), "cell_selection": "sea"},
    )
    h = donnees["hourly"]

    def valeur(champ, i):
        return _premier_non_nul(
            h.get(f"{champ}_ewam", [None] * (i + 1))[i],
            h.get(f"{champ}_gwam", [None] * (i + 1))[i],
            h.get(champ, [None] * (i + 1))[i])

    resultat = {}
    for i, horodatage in enumerate(h["time"]):
        periode = _premier_non_nul(valeur("wave_peak_period", i),
                                   valeur("wave_period", i))
        e = h.get("wave_height_ewam", [None] * (i + 1))[i]
        g = h.get("wave_height_gwam", [None] * (i + 1))[i]
        resultat[datetime.fromisoformat(horodatage)] = {
            "hauteur_m": valeur("wave_height", i),
            "tpeak_s": periode,
            "direction_deg": valeur("wave_direction", i),
            "houle_longue_m": valeur("swell_wave_height", i),
            "houle_longue_s": valeur("swell_wave_peak_period", i),
            "ecart_modeles_m": (round(abs(e - g), 2)
                                if e is not None and g is not None else None),
        }

    if all(v["hauteur_m"] is None for v in resultat.values()):
        raise RuntimeError(
            "L'API Marine n'a renvoyé que des valeurs nulles. Vérifie les "
            f"coordonnées de la bouée {sp['bouee']} : elles doivent tomber en mer.")
    return resultat


def recuperer_courant(sp, heures: int) -> dict[datetime, dict]:
    """Courant de surface au large du spot. Facultatif : l'échec est toléré."""
    try:
        donnees = _get_json(
            "https://marine-api.open-meteo.com/v1/marine",
            {"latitude": sp["point_courant"][0], "longitude": sp["point_courant"][1],
             "hourly": "ocean_current_velocity,ocean_current_direction",
             "timezone": FUSEAU, "forecast_hours": min(heures, 168),
             "cell_selection": "sea"},
        )
        h = donnees["hourly"]
        return {
            datetime.fromisoformat(t): {
                # l'API renvoie des km/h, on passe en nœuds
                "vitesse_kt": (round(h["ocean_current_velocity"][i] * 0.539957, 2)
                               if h["ocean_current_velocity"][i] is not None else None),
                "direction_deg": h["ocean_current_direction"][i],
            }
            for i, t in enumerate(h["time"])
        }
    except Exception:
        return {}


def _moyenne_vent(mesures):
    """
    Combine plusieurs prévisions (vitesse, direction, rafales).
    La vitesse et les rafales sont moyennées ; la direction l'est
    vectoriellement, sinon 350° et 10° donneraient 180°.
    """
    n = len(mesures)
    vit = sum(m[0] for m in mesures) / n
    raf = sum(m[2] for m in mesures) / n
    x = sum(math.cos(math.radians(m[1])) for m in mesures)
    y = sum(math.sin(math.radians(m[1])) for m in mesures)
    direction = math.degrees(math.atan2(y, x)) % 360
    return vit, direction, raf


def recuperer_vent(sp, heures: int) -> dict[datetime, dict]:
    """
    Vent horaire issu des modèles fins (AROME HD, UKV), relayé au-delà de
    leur portée par ARPEGE puis par le choix automatique d'Open-Meteo.
    Les indices d'orage viennent du choix automatique, qui les fournit tous.
    """
    lat, lon = sp.get("point_vent", sp["point_spot"])
    tous = MODELES_VENT + MODELES_VENT_RELAIS
    variables = ("wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
                 "weather_code,cape,lifted_index,precipitation_probability")
    try:
        donnees = _get_json(
            "https://api.open-meteo.com/v1/forecast",
            {"latitude": lat, "longitude": lon, "hourly": variables,
             "models": ",".join(tous), "wind_speed_unit": "kn",
             "timezone": FUSEAU, "forecast_hours": min(heures, 168)})
        multi = True
    except Exception:
        # Un modèle indisponible ne doit pas priver la page de vent.
        donnees = _get_json(
            "https://api.open-meteo.com/v1/forecast",
            {"latitude": lat, "longitude": lon, "hourly": variables,
             "wind_speed_unit": "kn", "timezone": FUSEAU,
             "forecast_hours": min(heures, 168)})
        multi = False
    h = donnees["hourly"]

    def col(nom, modele, i):
        cle = f"{nom}_{modele}" if multi and modele else nom
        serie = h.get(cle)
        return serie[i] if serie and i < len(serie) else None

    def mesure(modele, i):
        v = col("wind_speed_10m", modele, i)
        d = col("wind_direction_10m", modele, i)
        r = col("wind_gusts_10m", modele, i)
        if v is None or d is None:
            return None
        return (v, d, r if r is not None else v)

    ordre = {"arome": MODELES_VENT, "ukv": list(reversed(MODELES_VENT))
             }.get(MODE_VENT, MODELES_VENT)

    resultat = {}
    for i, t in enumerate(h["time"]):
        if not multi:
            m = mesure(None, i)
            vit, direc, raf = m if m else (None, None, None)
            source, ecart = "Open-Meteo", None
        else:
            fins = {mod: mesure(mod, i) for mod in MODELES_VENT}
            dispo = [mod for mod in ordre if fins[mod]]
            ecart = None
            if len(dispo) == len(MODELES_VENT):
                vitesses = [fins[mod][0] for mod in MODELES_VENT]
                ecart = round(max(vitesses) - min(vitesses), 1)
            if MODE_VENT == "moyenne" and len(dispo) > 1:
                vit, direc, raf = _moyenne_vent([fins[mod] for mod in dispo])
                source = " + ".join(NOMS_MODELES[mod] for mod in dispo)
            elif dispo:
                vit, direc, raf = fins[dispo[0]]
                source = NOMS_MODELES[dispo[0]]
            else:
                vit = direc = raf = None
                source = "—"
                for mod in MODELES_VENT_RELAIS:
                    m = mesure(mod, i)
                    if m:
                        vit, direc, raf = m
                        source = NOMS_MODELES[mod]
                        break

        def indice(nom):
            # Les indices d'orage : choix automatique d'abord, qui les a tous.
            for mod in (["best_match"] + tous) if multi else [None]:
                v = col(nom, mod, i)
                if v is not None:
                    return v
            return None

        resultat[datetime.fromisoformat(t)] = {
            "vitesse_kt": vit, "direction_deg": direc, "rafales_kt": raf,
            "modele_vent": source, "ecart_vent_kt": ecart,
            "code_meteo": indice("weather_code"),
            "cape": indice("cape"),
            "lifted_index": indice("lifted_index"),
            "proba_pluie": indice("precipitation_probability"),
        }
    return resultat


def recuperer_soleil(sp, heures: int) -> dict:
    donnees = _get_json(
        "https://api.open-meteo.com/v1/forecast",
        {"latitude": sp["point_spot"][0], "longitude": sp["point_spot"][1],
         "daily": "sunrise,sunset",
         "timezone": FUSEAU, "forecast_days": min(max(1, (heures + 23) // 24), 16)},
    )
    d = donnees["daily"]
    return {d["time"][i]: (datetime.fromisoformat(d["sunrise"][i]),
                           datetime.fromisoformat(d["sunset"][i]))
            for i in range(len(d["time"]))}


def _verifier_cle():
    if not CLE_MAREE:
        raise RuntimeError(
            "Clé api-maree.fr absente. Crée un compte gratuit sur "
            "https://api-maree.fr/ puis définis API_MAREE_KEY.")


def recuperer_extrema_maree(sp, depuis: datetime, jusqu_a: datetime) -> list[dict]:
    _verifier_cle()
    donnees = _get_json("https://api-maree.fr/tide-extrema",
                        {"site": sp["site_maree"], "from": depuis.date().isoformat(),
                         "to": jusqu_a.date().isoformat(), "tz": FUSEAU,
                         "key": CLE_MAREE})
    extrema = []
    for jour in donnees["data"]:
        date_jour = datetime.fromisoformat(jour["date"]).date()
        for e in jour["extrema"]:
            heure, minute = (int(v) for v in e["time"].split(":"))
            extrema.append({
                "instant": datetime.combine(date_jour, datetime.min.time())
                           + timedelta(hours=heure, minutes=minute),
                "type": e["type"], "hauteur_m": e.get("height"),
                "coef": e.get("coef")})
    return sorted(extrema, key=lambda e: e["instant"])


def recuperer_hauteurs_eau(sp, depuis: datetime, jusqu_a: datetime) -> dict:
    """Hauteur d'eau au pas de 30 min : il en faut deux par heure pour
    calculer proprement la dérivée dh/dt."""
    _verifier_cle()
    donnees = _get_json("https://api-maree.fr/water-levels",
                        {"site": sp["site_maree"],
                         "from": depuis.strftime("%Y-%m-%dT%H:%M"),
                         "to": jusqu_a.strftime("%Y-%m-%dT%H:%M"), "step": 30,
                         "tz": FUSEAU, "key": CLE_MAREE})
    return {datetime.fromisoformat(p["time"]).replace(tzinfo=None): p["height"]
            for p in donnees["data"]}


def position_dans_cycle(instant, extrema):
    """(heures depuis la pleine mer la plus proche, durée du demi-cycle)."""
    pm = [e for e in extrema if e["type"] == "PM"]
    bm = [e for e in extrema if e["type"] == "BM"]
    if not pm:
        return 0.0, 6.2
    pm_proche = min(pm, key=lambda e: abs((e["instant"] - instant).total_seconds()))
    delta_h = (instant - pm_proche["instant"]).total_seconds() / 3600.0
    if delta_h >= 0:
        voisines = [e for e in bm if e["instant"] > pm_proche["instant"]]
    else:
        voisines = [e for e in bm if e["instant"] < pm_proche["instant"]]
    if voisines:
        bm_v = min(voisines, key=lambda e: abs(
            (e["instant"] - pm_proche["instant"]).total_seconds()))
        demi = abs((bm_v["instant"] - pm_proche["instant"]).total_seconds() / 3600.0)
    else:
        demi = 6.2
    return delta_h, demi


def derivee_hauteur(instant, hauteurs) -> float:
    """dh/dt en m/h, par différence centrée sur les points à ±30 min."""
    avant = hauteurs.get(instant - timedelta(minutes=30))
    apres = hauteurs.get(instant + timedelta(minutes=30))
    if avant is not None and apres is not None:
        return apres - avant
    ici = hauteurs.get(instant)
    if ici is None:
        return 0.0
    if apres is not None:
        return (apres - ici) * 2
    if avant is not None:
        return (ici - avant) * 2
    return 0.0


def marnage_du_jour(cle_jour: str, extrema) -> float:
    """Écart entre la plus haute PM et la plus basse BM de la journée."""
    du_jour = [e for e in extrema if e["instant"].date().isoformat() == cle_jour
               and e["hauteur_m"] is not None]
    pm = [e["hauteur_m"] for e in du_jour if e["type"] == "PM"]
    bm = [e["hauteur_m"] for e in du_jour if e["type"] == "BM"]
    if not pm or not bm:
        return 0.0
    return round(max(pm) - min(bm), 2)


# ==========================================================================
# ASSEMBLAGE
# ==========================================================================

@dataclass
class Creneau:
    instant: datetime
    hauteur_m: float
    tpeak_s: float
    dir_houle: float
    ecart_modeles_m: float | None
    houle_longue_m: float | None
    energie_kwm: float
    xi: float
    pente: float
    mer_locale: bool
    hs_fetch_m: float
    tp_fetch_s: float
    vitesse_kt: float
    dir_vent: float
    rafales_kt: float
    cat_vent: str
    modele_vent: str
    ecart_vent_kt: float | None
    heures_depuis_pm: float
    hauteur_eau_m: float | None
    dh_dt_m_h: float
    translation_m_min: float
    marnage_m: float
    rtr: float
    facteur_rtr: float
    courant_kt: float | None
    courant_dir: float | None
    courant_effet: str
    cape: float | None
    lifted_index: float | None
    proba_pluie: float | None
    risque_orage: str
    note_houle: float
    note_position: float
    note_stabilite: float
    note_maree: float
    note_vent: int
    note_totale: float

    def ligne(self) -> str:
        def et(n):
            p = int(round(n))
            return "★" * p + "☆" * (5 - p)
        return (
            f"{self.instant:%d/%m %Hh}  {self.note_totale:4.2f}/5  |  "
            f"houle {et(self.note_houle)} ({self.hauteur_m:.2f}m "
            f"{self.tpeak_s:.1f}s {self.dir_houle:.0f}° {self.energie_kwm:.0f}kJ "
            f"xi{self.xi:.2f}{' loc' if self.mer_locale else ''})  "
            f"marée {et(self.note_maree)} (PM{self.heures_depuis_pm:+.1f}h "
            f"{self.translation_m_min:.1f}m/min)  "
            f"vent {et(self.note_vent)} ({self.vitesse_kt:.0f}kt "
            f"{self.dir_vent:.0f}° {self.cat_vent})"
            + (f"  ⚡ ORAGE {self.risque_orage}"
               if self.risque_orage in ("modéré", "élevé") else ""))


def construire_creneaux(sp, heures: int):
    houle = recuperer_houle(sp, heures)
    vent = recuperer_vent(sp, heures)
    soleil = recuperer_soleil(sp, heures)
    courant = recuperer_courant(sp, heures)

    instants = sorted(set(houle) & set(vent))
    if not instants:
        return [], [], []

    # Risque orageux calculé sur TOUTES les heures, y compris la nuit, puis
    # étendu aux heures voisines : la propagation doit voir les cellules qui
    # arrivent avant le lever du jour ou après le coucher.
    risques = propager_orage({
        t: risque_orage(vent[t].get("code_meteo"), vent[t].get("cape"),
                        vent[t].get("lifted_index"))
        for t in instants})

    extrema = recuperer_extrema_maree(sp, instants[0] - timedelta(days=1),
                                      instants[-1] + timedelta(days=1))
    hauteurs = recuperer_hauteurs_eau(sp, instants[0] - timedelta(hours=1),
                                      instants[-1] + timedelta(hours=1))
    marnages = {}

    creneaux = []
    for instant in instants:
        cle_jour = instant.date().isoformat()
        if cle_jour not in soleil:
            continue
        lever, coucher = soleil[cle_jour]
        if not (lever - timedelta(minutes=30) <= instant
                <= coucher + timedelta(minutes=30)):
            continue

        h, v = houle[instant], vent[instant]
        c = courant.get(instant, {})
        delta_pm, demi_cycle = position_dans_cycle(instant, extrema)

        if cle_jour not in marnages:
            marnages[cle_jour] = marnage_du_jour(cle_jour, extrema)
        marnage = marnages[cle_jour]

        # Position dans le marnage, pour la pente locale
        eau = hauteurs.get(instant)
        du_jour = [e["hauteur_m"] for e in extrema
                   if e["instant"].date().isoformat() == cle_jour
                   and e["hauteur_m"] is not None]
        if eau is not None and du_jour and max(du_jour) > min(du_jour):
            fraction = (eau - min(du_jour)) / (max(du_jour) - min(du_jour))
        else:
            fraction = 0.5
        pente = pente_locale(sp, fraction)

        xi = iribarren(h["hauteur_m"], h["tpeak_s"], pente)
        hs_f, tp_f = mer_levee_localement(sp, v["vitesse_kt"], v["direction_deg"])
        locale = bool(h["hauteur_m"] and h["tpeak_s"] and tp_f
                      and h["tpeak_s"] <= tp_f * 1.1
                      and h["hauteur_m"] <= hs_f * 1.1)

        dh = derivee_hauteur(instant, hauteurs)
        trans = translation_m_min(dh, pente)

        n_houle = score_houle(sp, h["hauteur_m"], h["tpeak_s"], h["direction_deg"],
                              xi=xi, mer_locale=locale)
        n_pos = score_position_maree(sp, delta_pm, demi_cycle)
        n_stab = score_stabilite(trans)
        n_maree = score_maree(n_pos, n_stab)
        n_vent = score_vent(sp, v["vitesse_kt"], v["direction_deg"], v["rafales_kt"])
        f_rtr = facteur_rtr(marnage, h["hauteur_m"])
        orage = risques.get(instant, "nul")
        libelle_courant, _ = effet_courant(c.get("vitesse_kt"),
                                           c.get("direction_deg"),
                                           h["direction_deg"] or 0)

        creneaux.append(Creneau(
            instant=instant,
            hauteur_m=round(h["hauteur_m"] or 0.0, 2),
            tpeak_s=round(h["tpeak_s"] or 0.0, 1),
            dir_houle=round(h["direction_deg"] or 0.0),
            ecart_modeles_m=h["ecart_modeles_m"],
            houle_longue_m=(round(h["houle_longue_m"], 2)
                            if h["houle_longue_m"] is not None else None),
            energie_kwm=energie_houle(h["hauteur_m"], h["tpeak_s"]),
            xi=xi, pente=round(pente, 4), mer_locale=locale,
            hs_fetch_m=hs_f, tp_fetch_s=tp_f,
            vitesse_kt=round(v["vitesse_kt"] or 0.0, 1),
            dir_vent=round(v["direction_deg"] or 0.0),
            rafales_kt=round(v["rafales_kt"] or 0.0, 1),
            cat_vent=categorie_vent(sp, v["direction_deg"] or 0.0),
            modele_vent=v.get("modele_vent", "—"),
            ecart_vent_kt=v.get("ecart_vent_kt"),
            heures_depuis_pm=round(delta_pm, 2),
            hauteur_eau_m=round(eau, 2) if eau is not None else None,
            dh_dt_m_h=round(dh, 2), translation_m_min=trans,
            marnage_m=marnage,
            rtr=round(marnage / h["hauteur_m"], 1) if h["hauteur_m"] else 0.0,
            facteur_rtr=f_rtr,
            courant_kt=c.get("vitesse_kt"), courant_dir=c.get("direction_deg"),
            courant_effet=libelle_courant,
            cape=v.get("cape"), lifted_index=v.get("lifted_index"),
            proba_pluie=v.get("proba_pluie"), risque_orage=orage,
            note_houle=n_houle, note_position=round(n_pos, 2),
            note_stabilite=n_stab, note_maree=n_maree, note_vent=n_vent,
            note_totale=note_globale(n_houle, n_maree, n_vent, f_rtr, orage),
        ))

    return creneaux, extrema, resumer_journees(creneaux, extrema, soleil)


def _direction_moyenne(directions) -> float:
    if not directions:
        return 0.0
    x = sum(math.cos(math.radians(d)) for d in directions)
    y = sum(math.sin(math.radians(d)) for d in directions)
    return math.degrees(math.atan2(y, x)) % 360


def resumer_journees(creneaux, extrema, soleil) -> list[dict]:
    par_jour = {}
    for c in creneaux:
        par_jour.setdefault(c.instant.date().isoformat(), []).append(c)

    resumes = []
    for cle in sorted(par_jour):
        j = par_jour[cle]
        lever, coucher = soleil.get(cle, (None, None))
        meilleur = max(j, key=lambda c: c.note_totale)
        resumes.append({
            "date": cle,
            "lever": lever.strftime("%H:%M") if lever else None,
            "coucher": coucher.strftime("%H:%M") if coucher else None,
            "marees": [{"heure": e["instant"].strftime("%H:%M"), "type": e["type"],
                        "hauteur_m": e["hauteur_m"], "coef": e["coef"]}
                       for e in extrema if e["instant"].date().isoformat() == cle],
            "marnage_m": j[0].marnage_m,
            "rtr": round(sum(c.rtr for c in j) / len(j), 1),
            "houle_m": [min(c.hauteur_m for c in j), max(c.hauteur_m for c in j)],
            "tpeak_s": [min(c.tpeak_s for c in j), max(c.tpeak_s for c in j)],
            "dir_houle": round(_direction_moyenne([c.dir_houle for c in j])),
            "energie_max_kwm": max(c.energie_kwm for c in j),
            "xi_max": max(c.xi for c in j),
            "vent_kt": [min(c.vitesse_kt for c in j), max(c.vitesse_kt for c in j)],
            "rafales_max_kt": max(c.rafales_kt for c in j),
            "dir_vent": round(_direction_moyenne([c.dir_vent for c in j])),
            "meilleure_heure": meilleur.instant.strftime("%H:%M"),
            "meilleure_note": meilleur.note_totale,
            "note_moyenne": round(sum(c.note_totale for c in j) / len(j), 2),
            "orage_max": max((c.risque_orage for c in j),
                             key=lambda n: NIVEAUX_ORAGE.index(n)),
            "heures_orage": [c.instant.strftime("%H:%M") for c in j
                             if c.risque_orage == "élevé"],
        })
    return resumes


def exporter_json(resultats: dict, chemin: Path, erreurs: dict | None = None) -> None:
    """
    Un seul fichier pour les deux spots. La page charge tout d'un coup et
    bascule de l'un à l'autre sans nouvelle requête.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    charge = {
        # Avec le décalage explicite : le navigateur sait alors le convertir.
        "genere_le": maintenant().isoformat(timespec="minutes"),
        # Ordre fixe, celui de SPOTS. Un spot en échec reste présent avec sa
        # raison : mieux vaut « Calais indisponible, parce que… » qu'une
        # disparition silencieuse.
        "spots": [
            {
                "cle": cle,
                "nom": SPOTS[cle]["nom"],
                "bouee": SPOTS[cle]["bouee"],
                "site_maree": SPOTS[cle]["site_maree"],
                "pic_maree_h": SPOTS[cle]["pic_maree_h"],
                "liens": SPOTS[cle].get("liens", {}),
                "erreur": (erreurs or {}).get(cle),
                "creneaux": [{**asdict(c), "instant": c.instant.isoformat()}
                             for c in resultats[cle]["creneaux"]]
                            if cle in resultats else [],
                "marees": [{**e, "instant": e["instant"].isoformat()}
                           for e in resultats[cle]["extrema"]]
                          if cle in resultats else [],
                "journees": resultats[cle]["journees"] if cle in resultats else [],
            }
            for cle in SPOTS
            if cle in resultats or cle in (erreurs or {})
        ],
    }
    chemin.write_text(json.dumps(charge, ensure_ascii=False), encoding="utf-8")


def ecrire_journal(cle_spot: str, creneaux, chemin: Path) -> None:
    """Journal CSV, avec une colonne spot et une note réelle à remplir."""
    nouveau = not chemin.exists()
    champs = ["spot"] + list(asdict(creneaux[0]).keys()) + ["note_reelle", "commentaire"]
    with chemin.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        if nouveau:
            w.writeheader()
        for c in creneaux:
            ligne = asdict(c)
            ligne["spot"] = cle_spot
            ligne["instant"] = c.instant.isoformat()
            ligne["note_reelle"] = ""
            ligne["commentaire"] = ""
            w.writerow(ligne)


def afficher_console(cle_spot, creneaux, resumes, min_note):
    sp = SPOTS[cle_spot]
    aff = [c for c in creneaux if c.note_totale >= min_note]
    pic = sp["pic_maree_h"]
    quand = (f"PM{pic:+.1f}h" if pic else "à la pleine mer")
    print(f"\n{'=' * 78}")
    print(f"{sp['nom'].upper()} — {len(aff)} créneau(x) de jour "
          f"| bouée {sp['bouee']} | optimum {quand} "
          f"| houle {sp['direction_houle'][0]:.0f}-{sp['direction_houle'][1]:.0f}°")
    print("=" * 78)

    par_date = {r["date"]: r for r in resumes}
    jour = None
    for c in aff:
        if c.instant.date() != jour:
            jour = c.instant.date()
            r = par_date.get(jour.isoformat())
            print()
            if r:
                marees = "  ".join(
                    f"{m['type']} {m['heure']}"
                    + (f" (coef {m['coef']})" if m.get("coef") else "")
                    for m in r["marees"])
                print(f"  {date_fr(jour)} — jour {r['lever']}-{r['coucher']}"
                      f"  |  {marees}")
                print(f"  marnage {r['marnage_m']:.1f}m  RTR {r['rtr']}"
                      f"  |  houle {r['houle_m'][0]:.2f}-{r['houle_m'][1]:.2f}m "
                      f"{r['tpeak_s'][0]:.1f}-{r['tpeak_s'][1]:.1f}s "
                      f"{r['dir_houle']}° {r['energie_max_kwm']:.0f}kJ max"
                      f"  |  vent {r['vent_kt'][0]:.0f}-{r['vent_kt'][1]:.0f}kt"
                      f"  |  meilleur {r['meilleure_heure']} "
                      f"({r['meilleure_note']}/5)")
                if r.get("orage_max") in ("modéré", "élevé"):
                    heures = ", ".join(r["heures_orage"]) or ""
                    print(f"  /!\\  RISQUE D'ORAGE {r['orage_max'].upper()}"
                          + (f" : {heures}" if heures else ""))
                print("  " + "-" * 76)
        print("  " + c.ligne())

    if aff:
        best = max(aff, key=lambda c: c.note_totale)
        print(f"\n  Meilleur : {date_fr(best.instant)} à "
              f"{best.instant:%Hh} ({best.note_totale}/5)")
    else:
        print("\n  Rien de notable sur la période.")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Prévisions de surf à Wimereux et à Calais")
    p.add_argument("--heures", type=int, default=96)
    p.add_argument("--min-note", type=float, default=0.0)
    p.add_argument("--spot", choices=list(SPOTS), action="append",
                   help="limiter à un spot (répétable). Par défaut : tous.")
    p.add_argument("--json", type=Path)
    p.add_argument("--journal", type=Path)
    args = p.parse_args()

    cles = args.spot or list(SPOTS)
    resultats = {}
    erreurs = {}

    for cle in cles:
        try:
            creneaux, extrema, resumes = construire_creneaux(SPOTS[cle], args.heures)
        except Exception as erreur:
            import traceback
            print(f"[{SPOTS[cle]['nom']}] erreur de récupération : {erreur}",
                  file=sys.stderr)
            traceback.print_exc()          # le détail, pour le journal Actions
            erreurs[cle] = f"{type(erreur).__name__} : {erreur}"
            continue
        resultats[cle] = {"creneaux": creneaux, "extrema": extrema,
                          "journees": resumes}
        if args.journal and creneaux:
            ecrire_journal(cle, creneaux, args.journal)

    if not resultats:
        print("Aucun spot n'a pu être calculé.", file=sys.stderr)
        return 1

    if args.json:
        exporter_json(resultats, args.json, erreurs)
        total = sum(len(r["creneaux"]) for r in resultats.values())
        print(f"{total} créneaux sur {len(resultats)} spot(s) "
              f"écrits dans {args.json}")
        return 0

    for cle, r in resultats.items():
        afficher_console(cle, r["creneaux"], r["journees"], args.min_note)

    # Lequel des deux vaut le déplacement ?
    meilleurs = []
    for cle, r in resultats.items():
        if r["creneaux"]:
            b = max(r["creneaux"], key=lambda c: c.note_totale)
            meilleurs.append((b.note_totale, SPOTS[cle]["nom"], b.instant))
    if len(meilleurs) > 1:
        meilleurs.sort(reverse=True)
        print(f"\n{'=' * 78}")
        for note, nom, quand in meilleurs:
            print(f"  {nom:12s} {note:4.2f}/5  {date_fr(quand)} à {quand:%Hh}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
