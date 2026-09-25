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
# optimum de marée, son orientation et son barème. Wimereux regarde
# l'ouest-nord-ouest et marche sur la houle d'ouest-sud-ouest ; Calais regarde
# le nord et marche sur la houle de nord, au montant avant la pleine mer.

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
        # Fenêtre de direction de houle. Au-delà, la note décroît sur
        # "marge_direction" degrés au lieu de tomber d'un coup à zéro.
        "direction_houle": (200.0, 270.0),
        "marge_direction": 15.0,
        # Optimum de marée, en heures par rapport à la pleine mer.
        # Positif = après la PM.
        "pic_maree_h": 1.0,
        # Axe de vent idéal pour le SURF, issu de ton expérience : le vent de
        # sud y est bon. C'est le centre de l'ancien secteur favorable.
        "axe_offshore_surf": 167.0,
        # Direction vers laquelle la plage regarde, c'est-à-dire vers le large.
        # Sert à la WING, où compte la géométrie réelle : un vent qui vient de
        # la direction opposée pousse vers le large. Estimation à vérifier.
        "face_plage": 285.0,
        # Temps pour être à l'eau depuis chez toi, en minutes.
        "trajet_min": 0,
        # Barème de houle propre au spot.
        "seuils_houle": {
            "h_nulle": 0.50, "h_min": 0.70, "h_pleine": 1.00,
            "t_min": 5.5, "t_pleine": 7.5,
            "xi_mou": 0.15, "xi_franc": 0.32,
        },
        "pente_haute": 0.035,
        "pente_basse": 0.010,
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
        "marge_direction": 15.0,
        # Marche au montant, avant la pleine mer.
        "pic_maree_h": -1.5,
        "axe_offshore_surf": 180.0,
        "face_plage": 350.0,
        "trajet_min": 35,
        # La houle de nord en mer du Nord est courte par nature : avec les
        # seuils de Wimereux, Calais serait sous-noté par construction.
        # Période décalée d'une seconde, point de départ à valider au journal.
        "seuils_houle": {
            "h_nulle": 0.50, "h_min": 0.70, "h_pleine": 1.00,
            "t_min": 4.5, "t_pleine": 6.5,
            "xi_mou": 0.15, "xi_franc": 0.32,
        },
        "pente_haute": 0.035,
        "pente_basse": 0.010,
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

# --- Houle ----------------------------------------------------------------
# Le barème lui-même est dans SPOTS["…"]["seuils_houle"].
CALIBRATION_HOULE = 1.0

# --- Vitesse de translation de la marée, en mètres par minute ------------
TRANSLATION_LENTE = 0.6
TRANSLATION_RAPIDE = 2.2

# --- Amplitude de marée relative (RTR) : affichée, n'entre plus dans la note.
# Elle dépend du coefficient, comme la vitesse de translation : la garder
# dans la note pénalisait deux fois la même cause.

# --- Vent -----------------------------------------------------------------

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

# --- Notes globales : moyennes géométriques --------------------------------
# Un critère très mauvais tire fortement la note vers le bas, et un zéro
# donne zéro. Ce principe remplace les anciens plafonds et vétos de confort.
POIDS_SURF = {"houle": 0.50, "vent": 0.30, "maree": 0.20}
POIDS_MAREE = {"position": 0.6, "stabilite": 0.4}
POIDS_WING = {"force": 0.40, "rafales": 0.20, "maree": 0.25, "mer": 0.15}

# --- Session ---------------------------------------------------------------
# On surfe des sessions, pas des heures : la note de session est la moyenne
# de deux heures consécutives de jour.
DUREE_SESSION_H = 2

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


# ==========================================================================
# NOTATION
# ==========================================================================

# ---------- Outils ----------

def _interp(x, points):
    """Interpolation linéaire par morceaux sur une liste de (x, y) triée."""
    if x is None:
        return None
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _borne(x, bas=0.0, haut=1.0):
    return max(bas, min(haut, x))


def _ecart_angle(a, b) -> float:
    """Écart entre deux directions, entre 0 et 180°."""
    return abs((a - b + 180) % 360 - 180)


def _dans_secteur(direction, debut, fin) -> bool:
    direction, debut, fin = direction % 360, debut % 360, fin % 360
    if debut <= fin:
        return debut <= direction <= fin
    return direction >= debut or direction <= fin


def moyenne_geometrique(notes: dict, poids: dict) -> float:
    """
    Moyenne géométrique pondérée de notes sur 5. Contrairement à la moyenne
    arithmétique, un critère mauvais n'est pas compensé par les autres : la
    qualité d'une session est limitée par son facteur le plus faible.
    """
    total = sum(poids.values())
    log = 0.0
    for cle, w in poids.items():
        n = notes[cle]
        if n is None or n <= 0:
            return 0.0
        log += (w / total) * math.log(n / 5.0)
    return round(5.0 * math.exp(log), 2)


# ---------- Surf : houle ----------

def facteur_direction(sp, direction_deg) -> float:
    """1 dans la fenêtre, puis décroissance linéaire sur la marge."""
    if direction_deg is None:
        return 0.0
    debut, fin = sp["direction_houle"]
    if _dans_secteur(direction_deg, debut, fin):
        return 1.0
    d = min(_ecart_angle(direction_deg, debut), _ecart_angle(direction_deg, fin))
    return round(_borne(1 - d / sp["marge_direction"]), 3)


def part_houle_longue(hauteur_m, houle_longue_m):
    """
    Part de l'énergie portée par la houle longue, entre 0 et 1. L'énergie
    variant comme le carré de la hauteur, on compare des carrés. Mesurée au
    même point que la mer totale, contrairement à l'ancien test de fetch qui
    mélangeait la mer de Hastings et le vent de Wimereux.
    """
    if not hauteur_m or houle_longue_m is None:
        return None
    return round(_borne((houle_longue_m / hauteur_m) ** 2), 2)


def score_houle(sp, hauteur_m, tpeak_s, direction_deg, xi=None, part_houle=None):
    """
    Barème continu, sans marche :
      - hauteur : jusqu'à 3 points entre h_min et h_pleine ;
      - période : jusqu'à 2 points entre t_min et t_pleine ;
      - déferlement (Iribarren) : de -0,5 à +0,5 ;
      - part de houle longue : de -0,5 à +0,5 ;
    le tout atténué sous h_min, et multiplié par le facteur de direction.
    """
    if hauteur_m is None or tpeak_s is None:
        return 0.0
    s = sp["seuils_houle"]
    f_dir = facteur_direction(sp, direction_deg)
    hs = hauteur_m * CALIBRATION_HOULE
    if f_dir == 0 or hs <= s["h_nulle"]:
        return 0.0

    points = (3.0 * _borne((hs - s["h_min"]) / (s["h_pleine"] - s["h_min"]))
              + 2.0 * _borne((tpeak_s - s["t_min"]) / (s["t_pleine"] - s["t_min"])))
    if xi is not None:
        points += _borne(-0.5 + (xi - s["xi_mou"]) / (s["xi_franc"] - s["xi_mou"]),
                         -0.5, 0.5)
    if part_houle is not None:
        points += _borne(-0.5 + (part_houle - 0.1) / 0.5, -0.5, 0.5)
    points = _borne(points, 0.0, 5.0)

    if hs < s["h_min"]:
        points *= (hs - s["h_nulle"]) / (s["h_min"] - s["h_nulle"])
    return round(points * f_dir, 2)


# ---------- Surf : vent ----------

# Note de vent selon la force, pour un vent parfaitement offshore et pour un
# vent plein onshore. Entre les deux, on passe continûment selon l'angle.
VENT_OFFSHORE = [(0, 5), (9, 5), (12, 3), (16, 3), (20, 2), (25, 1), (40, 1)]
VENT_ONSHORE = [(0, 5), (4, 5), (9, 2), (13, 1), (18, 0.5), (40, 0.5)]


def categorie_vent(sp, direction_deg: float) -> str:
    theta = _ecart_angle(direction_deg or 0, sp["axe_offshore_surf"])
    if theta < 60:
        return "offshore"
    if theta < 105:
        return "travers"
    return "onshore"


def score_vent(sp, vitesse_kt, direction_deg, rafales_kt=None) -> float:
    """
    Le vent est projeté sur l'axe de la plage : plus il est offshore, plus on
    se rapproche de la courbe offshore. Plus de secteurs aux frontières
    franches, plus de marche à 10 nœuds de rafales.
    """
    if vitesse_kt is None or direction_deg is None:
        return 1.0
    theta = math.radians(_ecart_angle(direction_deg, sp["axe_offshore_surf"]))
    poids = ((1 + math.cos(theta)) / 2) ** 2
    bas = _interp(vitesse_kt, VENT_ONSHORE)
    haut = _interp(vitesse_kt, VENT_OFFSHORE)
    note = bas + (haut - bas) * poids
    if rafales_kt is not None:
        note -= _borne((rafales_kt - vitesse_kt - 6) / 6, 0.0, 1.5)
    return round(_borne(note, 0.5, 5.0), 2)


# ---------- Surf : marée ----------

ANCRAGES_MAREE = [(-1.0, 1.0), (-0.5, 3.0), (0.5, 3.0), (1.0, 1.0)]


def score_position_maree(sp, heures_depuis_pm, duree_demi_cycle_h=6.2) -> float:
    """
    Position dans le cycle. L'optimum n'est pas au même endroit selon le
    spot : une heure APRÈS la pleine mer à Wimereux, une heure et demie
    AVANT à Calais, qui marche au montant.
    """
    if duree_demi_cycle_h <= 0:
        return 1.0
    x = _borne(heures_depuis_pm / duree_demi_cycle_h, -1.0, 1.0)
    pic = _borne(sp["pic_maree_h"] / duree_demi_cycle_h, -0.45, 0.45)
    return round(_interp(x, sorted(ANCRAGES_MAREE + [(pic, 5.0)])), 2)


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
    return round(_interp(vitesse_m_min, [(TRANSLATION_LENTE, 5.0),
                                         (TRANSLATION_RAPIDE, 1.0)]), 2)


def score_maree(position: float, stabilite: float) -> float:
    return moyenne_geometrique({"position": position, "stabilite": stabilite},
                               POIDS_MAREE)


def rapport_rtr(marnage_m, hauteur_m) -> float:
    """RTR = marnage / hauteur : affiché pour contexte, hors de la note."""
    if not marnage_m or not hauteur_m:
        return 0.0
    return round(marnage_m / hauteur_m, 1)


def appliquer_orage(note: float, orage: str) -> float:
    """
    Le seul véto restant, parce qu'il relève de la sécurité et non du
    confort : risque élevé, zéro ; risque modéré, plafond.
    """
    if orage == ORAGE_VETO:
        return 0.0
    if orage == "modéré":
        return round(min(note, ORAGE_PLAFOND_NOTE), 2)
    return note


def note_surf(houle, maree, vent, orage="nul") -> float:
    n = moyenne_geometrique({"houle": houle, "vent": vent, "maree": maree},
                            POIDS_SURF)
    return appliquer_orage(n, orage)


# ---------- Wing ----------
#
# La wing a d'autres besoins que le surf : du vent, pas trop rafaleux, de
# l'eau sur les bancs, et surtout PAS de vent qui pousse vers le large.
# Les courbes ci-dessous sont un point de départ, pour une wing moyenne.

WING_FORCE = [(0, 0), (9, 0), (11, 1), (13, 2.5), (15, 4.2), (17, 5), (24, 5),
              (28, 3.8), (32, 2.2), (36, 0.8), (50, 0.3)]
# Rafales rapportées au vent moyen.
WING_RAFALES = [(1.0, 5), (1.2, 5), (1.35, 3.5), (1.5, 2), (1.7, 1), (2.0, 0.5)]
# Écart entre le vent et l'axe offshore réel de la plage : 0° = vent qui
# pousse droit vers le large. C'est un facteur de sécurité, pas de confort.
WING_DIRECTION = [(0, 0.1), (45, 0.15), (70, 0.6), (90, 1.0), (145, 1.0), (180, 0.8)]
# Niveau d'eau entre basse mer (0) et pleine mer (1) : à basse mer, les
# bancs affleurent et l'aileron touche.
WING_MAREE = [(0, 0.5), (0.25, 1.5), (0.45, 4), (0.6, 5), (1, 5)]
# Hauteur de mer : au-delà, le shorebreak complique la mise à l'eau.
WING_MER = [(0, 5), (1.2, 5), (1.8, 3.5), (2.5, 2), (3.2, 1), (5, 0.5)]


def facteur_direction_wing(sp, direction_deg) -> float:
    if direction_deg is None:
        return 0.0
    offshore = (sp["face_plage"] + 180) % 360
    return round(_interp(_ecart_angle(direction_deg, offshore), WING_DIRECTION), 2)


def score_wing(sp, vitesse_kt, rafales_kt, direction_deg, fraction_maree,
               hauteur_m, orage="nul"):
    """Renvoie (note, détail des sous-notes)."""
    if vitesse_kt is None:
        return 0.0, {}
    detail = {
        "force": round(_interp(vitesse_kt, WING_FORCE), 2),
        "rafales": round(_interp((rafales_kt or vitesse_kt) / max(vitesse_kt, 1.0),
                                 WING_RAFALES), 2),
        "maree": round(_interp(fraction_maree, WING_MAREE), 2),
        "mer": round(_interp(hauteur_m or 0.0, WING_MER), 2),
        "direction": facteur_direction_wing(sp, direction_deg),
    }
    n = moyenne_geometrique(detail, POIDS_WING) * detail["direction"]
    return appliquer_orage(round(n, 2), orage), detail


# ---------- Fiabilité ----------

FIABILITE_ECHEANCE = [(0, 1.0), (24, 1.0), (72, 0.75), (120, 0.55), (168, 0.45)]


def fiabilite(echeance_h, ecart_vent_kt, ecart_houle_m) -> float:
    """
    Confiance qu'on peut accorder à la note, entre 0 et 1 : elle baisse avec
    l'échéance, et quand les modèles ne s'accordent pas.
    """
    f = _interp(max(0.0, echeance_h), FIABILITE_ECHEANCE)
    if ecart_vent_kt is not None and ecart_vent_kt >= ECART_VENT_ALERTE_KT:
        f *= 0.85
    if ecart_houle_m is not None and ecart_houle_m >= 0.3:
        f *= 0.85
    return round(f, 2)


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
    # houle
    hauteur_m: float
    tpeak_s: float
    dir_houle: float
    ecart_modeles_m: float | None
    houle_longue_m: float | None
    part_houle: float | None
    energie_kwm: float
    xi: float
    pente: float
    facteur_dir: float
    # vent
    vitesse_kt: float
    dir_vent: float
    rafales_kt: float
    cat_vent: str
    modele_vent: str
    ecart_vent_kt: float | None
    # marée
    heures_depuis_pm: float
    hauteur_eau_m: float | None
    niveau_maree: float
    dh_dt_m_h: float
    translation_m_min: float
    marnage_m: float
    rtr: float
    # courant, orage
    courant_kt: float | None
    courant_dir: float | None
    courant_effet: str
    cape: float | None
    lifted_index: float | None
    proba_pluie: float | None
    risque_orage: str
    # confiance
    echeance_h: float
    fiabilite: float
    # notes surf
    note_houle: float
    note_position: float
    note_stabilite: float
    note_maree: float
    note_vent: float
    note_totale: float              # note surf, nom conservé pour le journal
    # notes wing
    note_wing: float
    wing_detail: dict
    # sessions de DUREE_SESSION_H heures commençant à cette heure
    session_surf: float | None = None
    session_wing: float | None = None

    def ligne(self) -> str:
        def c(n):
            p = int(round(n))
            return "■" * p + "□" * (5 - p)
        return (
            f"{self.instant:%d/%m %Hh}  surf {self.note_totale:4.2f}  "
            f"wing {self.note_wing:4.2f}  |  "
            f"houle {c(self.note_houle)} ({self.hauteur_m:.2f}m "
            f"{self.tpeak_s:.1f}s {self.dir_houle:.0f}° {self.energie_kwm:.0f}kJ "
            f"xi{self.xi:.2f})  "
            f"marée {c(self.note_maree)} (PM{self.heures_depuis_pm:+.1f}h)  "
            f"vent {c(self.note_vent)} ({self.vitesse_kt:.0f}/{self.rafales_kt:.0f}kt "
            f"{self.dir_vent:.0f}° {self.cat_vent})  fiab {self.fiabilite:.2f}"
            + (f"  ORAGE {self.risque_orage}"
               if self.risque_orage in ("modéré", "élevé") else ""))


def calculer_sessions(creneaux) -> None:
    """
    Note de session : moyenne des DUREE_SESSION_H heures consécutives
    commençant à chaque créneau. Nulle si l'une d'elles est sous le véto
    orage, absente si la fenêtre sort du jour.
    """
    index = {c.instant: c for c in creneaux}
    for c in creneaux:
        fenetre = [index.get(c.instant + timedelta(hours=k))
                   for k in range(DUREE_SESSION_H)]
        if any(x is None for x in fenetre):
            continue
        if any(x.risque_orage == ORAGE_VETO for x in fenetre):
            c.session_surf = c.session_wing = 0.0
            continue
        c.session_surf = round(sum(x.note_totale for x in fenetre) / len(fenetre), 2)
        c.session_wing = round(sum(x.note_wing for x in fenetre) / len(fenetre), 2)


def construire_creneaux(sp, heures: int):
    houle = recuperer_houle(sp, heures)
    vent = recuperer_vent(sp, heures)
    soleil = recuperer_soleil(sp, heures)
    courant = recuperer_courant(sp, heures)

    instants = sorted(set(houle) & set(vent))
    if not instants:
        return [], [], []

    # Risque orageux calculé sur TOUTES les heures, y compris la nuit, puis
    # étendu aux heures voisines.
    risques = propager_orage({
        t: risque_orage(vent[t].get("code_meteo"), vent[t].get("cape"),
                        vent[t].get("lifted_index"))
        for t in instants})

    extrema = recuperer_extrema_maree(sp, instants[0] - timedelta(days=1),
                                      instants[-1] + timedelta(days=1))
    hauteurs = recuperer_hauteurs_eau(sp, instants[0] - timedelta(hours=1),
                                      instants[-1] + timedelta(hours=1))
    marnages = {}
    reference = maintenant().replace(tzinfo=None)

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

        # Niveau dans le marnage du jour : 0 à basse mer, 1 à pleine mer.
        eau = hauteurs.get(instant)
        du_jour = [e["hauteur_m"] for e in extrema
                   if e["instant"].date().isoformat() == cle_jour
                   and e["hauteur_m"] is not None]
        if eau is not None and du_jour and max(du_jour) > min(du_jour):
            niveau = _borne((eau - min(du_jour)) / (max(du_jour) - min(du_jour)))
        else:
            niveau = 0.5
        pente = pente_locale(sp, niveau)

        xi = iribarren(h["hauteur_m"], h["tpeak_s"], pente)
        part = part_houle_longue(h["hauteur_m"], h["houle_longue_m"])
        dh = derivee_hauteur(instant, hauteurs)
        trans = translation_m_min(dh, pente)
        orage = risques.get(instant, "nul")

        n_houle = score_houle(sp, h["hauteur_m"], h["tpeak_s"], h["direction_deg"],
                              xi=xi, part_houle=part)
        n_pos = score_position_maree(sp, delta_pm, demi_cycle)
        n_stab = score_stabilite(trans)
        n_maree = score_maree(n_pos, n_stab)
        n_vent = score_vent(sp, v["vitesse_kt"], v["direction_deg"], v["rafales_kt"])
        n_wing, detail_wing = score_wing(sp, v["vitesse_kt"], v["rafales_kt"],
                                         v["direction_deg"], niveau,
                                         h["hauteur_m"], orage)
        libelle_courant, _ = effet_courant(c.get("vitesse_kt"),
                                           c.get("direction_deg"),
                                           h["direction_deg"] or 0)
        echeance = (instant - reference).total_seconds() / 3600.0

        creneaux.append(Creneau(
            instant=instant,
            hauteur_m=round(h["hauteur_m"] or 0.0, 2),
            tpeak_s=round(h["tpeak_s"] or 0.0, 1),
            dir_houle=round(h["direction_deg"] or 0.0),
            ecart_modeles_m=h["ecart_modeles_m"],
            houle_longue_m=(round(h["houle_longue_m"], 2)
                            if h["houle_longue_m"] is not None else None),
            part_houle=part,
            energie_kwm=energie_houle(h["hauteur_m"], h["tpeak_s"]),
            xi=xi, pente=round(pente, 4),
            facteur_dir=facteur_direction(sp, h["direction_deg"]),
            vitesse_kt=round(v["vitesse_kt"] or 0.0, 1),
            dir_vent=round(v["direction_deg"] or 0.0),
            rafales_kt=round(v["rafales_kt"] or 0.0, 1),
            cat_vent=categorie_vent(sp, v["direction_deg"] or 0.0),
            modele_vent=v.get("modele_vent", "—"),
            ecart_vent_kt=v.get("ecart_vent_kt"),
            heures_depuis_pm=round(delta_pm, 2),
            hauteur_eau_m=round(eau, 2) if eau is not None else None,
            niveau_maree=round(niveau, 2),
            dh_dt_m_h=round(dh, 2), translation_m_min=trans,
            marnage_m=marnage, rtr=rapport_rtr(marnage, h["hauteur_m"]),
            courant_kt=c.get("vitesse_kt"), courant_dir=c.get("direction_deg"),
            courant_effet=libelle_courant,
            cape=v.get("cape"), lifted_index=v.get("lifted_index"),
            proba_pluie=v.get("proba_pluie"), risque_orage=orage,
            echeance_h=round(echeance, 1),
            fiabilite=fiabilite(echeance, v.get("ecart_vent_kt"), h["ecart_modeles_m"]),
            note_houle=n_houle, note_position=n_pos, note_stabilite=n_stab,
            note_maree=n_maree, note_vent=n_vent,
            note_totale=note_surf(n_houle, n_maree, n_vent, orage),
            note_wing=n_wing, wing_detail=detail_wing,
        ))

    calculer_sessions(creneaux)
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

        def meilleure(attr_session, attr_heure):
            candidats = [c for c in j if getattr(c, attr_session) is not None]
            if candidats:
                m = max(candidats, key=lambda c: getattr(c, attr_session))
                return m, getattr(m, attr_session)
            m = max(j, key=lambda c: getattr(c, attr_heure))
            return m, getattr(m, attr_heure)

        m_surf, n_surf = meilleure("session_surf", "note_totale")
        m_wing, n_wing = meilleure("session_wing", "note_wing")
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
            "fiabilite": round(sum(c.fiabilite for c in j) / len(j), 2),
            "vent_kt": [min(c.vitesse_kt for c in j), max(c.vitesse_kt for c in j)],
            "rafales_max_kt": max(c.rafales_kt for c in j),
            "dir_vent": round(_direction_moyenne([c.dir_vent for c in j])),
            # Meilleure session de DUREE_SESSION_H heures, par discipline.
            "meilleure_heure": m_surf.instant.strftime("%H:%M"),
            "meilleure_note": n_surf,
            "meilleure_heure_wing": m_wing.instant.strftime("%H:%M"),
            "meilleure_note_wing": n_wing,
            "duree_session_h": DUREE_SESSION_H,
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
                "trajet_min": SPOTS[cle].get("trajet_min", 0),
                "duree_session_h": DUREE_SESSION_H,
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
    aff = [c for c in creneaux if max(c.note_totale, c.note_wing) >= min_note]
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
                      f"  |  surf {r['meilleure_heure']} ({r['meilleure_note']})"
                      f"  wing {r['meilleure_heure_wing']} ({r['meilleure_note_wing']})")
                if r.get("orage_max") in ("modéré", "élevé"):
                    heures = ", ".join(r["heures_orage"]) or ""
                    print(f"  /!\\  RISQUE D'ORAGE {r['orage_max'].upper()}"
                          + (f" : {heures}" if heures else ""))
                print("  " + "-" * 76)
        print("  " + c.ligne())

    if aff:
        for disc, attr in (("surf", "session_surf"), ("wing", "session_wing")):
            sess = [c for c in aff if getattr(c, attr) is not None]
            if sess:
                b = max(sess, key=lambda c: getattr(c, attr))
                print(f"\n  Meilleure session {disc} : {date_fr(b.instant)} "
                      f"{b.instant:%Hh}-{(b.instant + timedelta(hours=DUREE_SESSION_H)):%Hh} "
                      f"({getattr(b, attr)}/5)")
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
    if len(resultats) > 1:
        print(f"\n{'=' * 78}")
        for disc, attr in (("surf", "session_surf"), ("wing", "session_wing")):
            lignes = []
            for cle, r in resultats.items():
                sess = [c for c in r["creneaux"] if getattr(c, attr) is not None]
                if sess:
                    b = max(sess, key=lambda c: getattr(c, attr))
                    lignes.append((getattr(b, attr), SPOTS[cle]["nom"], b.instant))
            for note, nom, quand in sorted(lignes, reverse=True):
                print(f"  {disc:5s} {nom:10s} {note:4.2f}/5  {date_fr(quand)} à {quand:%Hh}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
