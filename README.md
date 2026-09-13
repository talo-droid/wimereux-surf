# Prévisions de surf — Côte d'Opale

Notation des créneaux de surf à **Wimereux** et à **Calais**, sur trois critères
(houle, marée, vent) plus un véto orage, calculée toutes les 3 heures par
GitHub Actions et publiée sur une page consultable au téléphone.

Les deux spots ne se ressemblent pas et sont paramétrés séparément :

| | Wimereux | Calais |
|---|---|---|
| Bouée de référence | Hastings (CEFAS) | Sandettie |
| Orientation | ouest-nord-ouest | nord |
| Fenêtre de houle | 200-270° | 300-60° |
| Optimum de marée | 1 h après la PM | 1 h 30 avant la PM |
| Port de marée | Boulogne-sur-Mer | Calais |
| Fetch dominant | sud-ouest (Manche) | nord (mer du Nord) |

## Mise en route

1. **Crée un dépôt public** sur GitHub et pousse ces fichiers dedans.
   Le dépôt doit être public : GitHub Pages sur dépôt privé est réservé aux
   comptes payants. Aucune donnée sensible n'y circule — la clé d'API reste
   dans les secrets, seul le résultat calculé est publié.

2. **Récupère une clé api-maree.fr** (gratuit) sur https://api-maree.fr/,
   puis dans le dépôt : *Settings → Secrets and variables → Actions →
   New repository secret*, nom `API_MAREE_KEY`.

3. **Vérifie les identifiants des sites de marée.** Appelle une fois
   `https://api-maree.fr/sites?key=TA_CLE` et cherche les points les plus
   proches de chaque spot. Si ce ne sont pas `boulogne-sur-mer` et `calais`,
   ajoute des *variables* (et non des secrets) nommées `SITE_MAREE_WIMEREUX`
   et `SITE_MAREE_CALAIS`.

4. **Active Pages** : *Settings → Pages → Source : Deploy from a branch →
   Branch `main`, dossier `/docs`*. La page sera sur
   `https://TON-COMPTE.github.io/NOM-DU-DEPOT/`.

5. **Lance une première fois à la main** : onglet *Actions → Prévisions
   Wimereux → Run workflow*. Sans ça, `docs/data.json` n'existe pas encore et
   la page affichera un message d'erreur.

6. **Sur ton téléphone** : ouvre la page dans Chrome, menu ⋮ →
   *Ajouter à l'écran d'accueil*. Elle s'ouvrira ensuite comme une application.

## Réglages

Tout se règle en tête de `previsions.py` :

Le dictionnaire `SPOTS` en tête de fichier contient tout ce qui distingue les
deux spots :

| Clé | Rôle |
|---|---|
| `point_houle` | position de la bouée / du point de grille — à garder figé |
| `direction_houle` | fenêtre de direction (véto), gère le passage par 0° |
| `pic_maree_h` | optimum de marée, en heures par rapport à la pleine mer |
| `secteur_favorable`, `secteur_travers` | secteurs de vent |
| `fetch_km` | fetch par direction, la donnée la plus grossière — à affiner |
| `pente_haute`, `pente_basse` | profil de plage, pilote Iribarren et la translation |

Réglages communs aux deux spots :

| Constante | Rôle |
|---|---|
| `CALIBRATION_HOULE` | facteur correctif hauteur, à réajuster d'après tes sessions |
| `HAUTEUR_NULLE_M`, `HAUTEUR_MIN_M`, `HAUTEUR_PLEINE_M` | montée progressive des points de hauteur |
| `SEUIL_TPEAK_1`, `SEUIL_TPEAK_2` | paliers de période (6 s et 7 s) |
| `XI_MOU`, `XI_FRANC` | seuils d'Iribarren, relatifs au site |
| `TRANSLATION_*` | seuils de stabilité de la zone de déferlement |
| `RTR_*` | pénalité d'amplitude de marée relative |
| `CAPE_*`, `LI_*` | seuils de risque orageux |
| `POIDS` | pondération des trois critères dans la note globale |

## L'archive

Chaque exécution dépose une copie datée dans `archives/`. Au bout de quelques
mois, tu pourras comparer ce que le modèle annonçait à J-3 pour un créneau donné
avec ce qu'il annonçait à J-1, et savoir à partir de quel horizon il décroche
à Wimereux. C'est l'information qu'aucun site généraliste ne te donnera.

## Attribution

Données de marée fournies par api-maree.fr sous licence CC BY, calculées à
partir de composantes harmoniques Ifremer / PREVIMER, elles-mêmes sous licence
CC BY. Houle, vent, courant et indices convectifs : Open-Meteo (modèles DWD
EWAM et GWAM pour la houle).

## Sécurité

Le risque d'orage est un véto : une heure classée « élevé » est notée zéro
quelles que soient les conditions par ailleurs, et les deux heures voisines
passent au moins en « modéré ». Sur l'eau, la règle reste de sortir dès le
premier coup de tonnerre et d'attendre trente minutes après le dernier.
