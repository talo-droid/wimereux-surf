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

## Le journal

Tous les seuils de ce projet sont des hypothèses raisonnables, pas des mesures.
Le journal est ce qui les rendra justes.

### Remplir

Après chaque sortie, ajoute **une ligne** à `journal.csv` :

```
date,heure,spot,note,commentaire
2026-09-20,16,wimereux,4,belles séries sur la barre du milieu
```

- `date` au format AAAA-MM-JJ
- `heure` sur 24 h, sans minutes — l'heure du créneau, pas celle de ta sortie
  de l'eau
- `spot` : `wimereux` ou `calais`
- `note` : ce que TU as pensé de la session, de 1 à 5. C'est la seule donnée
  que le modèle ne peut pas deviner, et la seule qui compte vraiment.
- `commentaire` : libre, et facultatif. Mets une virgule dans du texte et il
  faudra l'entourer de guillemets.

Le plus simple : le bouton **Noter une session** en bas de la page. Tu choisis
le jour, l'heure, le spot et la note, la ligne se construit toute seule, un
bouton la copie et un autre ouvre `journal.csv` en édition sur GitHub. Il ne
reste qu'à coller à la fin du fichier et valider. Trente secondes sur le
parking, sans rien taper de travers.

Le lien vers GitHub se déduit de l'adresse de la page, il n'y a rien à
configurer. Il n'apparaît pas quand tu testes en local.

Ne note que ce que tu as vécu. Une ligne honnête vaut mieux que dix reconstituées
de mémoire, et une mauvaise session est aussi informative qu'une bonne.

### Analyser

```
python3 analyser.py
python3 analyser.py --spot calais
```

Le script rapproche `journal.csv` des copies datées déposées dans `archives/`
par chaque exécution, et affiche trois choses : le détail session par session
avec l'écart entre ta note et la note calculée ; le classement des critères
selon leur lien avec ton ressenti ; et la dérive de la prévision selon qu'elle
datait de la veille ou de trois jours avant.

En dessous d'une douzaine de sessions les corrélations sont du bruit, et le
script te le dit. À partir de vingt ou trente, elles commencent à dire quelque
chose : quel critère porte l'information, lequel n'apporte rien, et à partir de
quel horizon le modèle décroche chez toi. C'est ce qu'aucun site généraliste ne
te donnera.

## Attribution

Données de marée fournies par api-maree.fr sous licence CC BY, calculées à
partir de composantes harmoniques Ifremer / PREVIMER, elles-mêmes sous licence
CC BY. Houle, vent, courant et indices convectifs : Open-Meteo (modèles DWD
EWAM et GWAM pour la houle).

## Modèles de vent

Le vent vient de deux modèles à haute résolution, moyennés quand ils sont
disponibles tous les deux :

- **AROME HD** (Météo-France), environ 1,5 km, jusqu'à ~42 h ;
- **UKV** (Met Office), 2 km, jusqu'à ~48 h, réputé sur la Manche.

Au-delà de deux jours, ARPEGE prend le relais, puis le choix automatique
d'Open-Meteo. Le modèle utilisé s'affiche dans l'infobulle de chaque case de
vent, et un cadre pointillé signale un désaccord d'au moins 5 nœuds.

Le vent est calculé un peu au large (`point_vent` dans `SPOTS`) : posé sur le
trait de côte, une maille de 1,5 à 2 km mélange terre et mer, et la rugosité
du sol freine artificiellement le vent.

Pour privilégier un seul modèle, ajoute la variable de dépôt `MODE_VENT` avec
`arome` ou `ukv` (par défaut : `moyenne`), et ajoute-la à la section `env`
de l'étape « Calculer les notes » du workflow.

## Recevoir une notification

Le workflow prévient quand un créneau dépasse un seuil, par le service
**ntfy** : gratuit, sans compte, et l'application Android reçoit la
notification directement.

1. Installe *ntfy* depuis le Play Store.
2. Choisis un sujet à toi, long et peu devinable — par exemple
   `opale-surf-8kq2vx`. Toute personne connaissant ce mot peut lire tes
   notifications, alors évite `surf` ou ton prénom.
3. Dans l'application, abonne-toi à ce sujet.
4. Dans le dépôt, *Settings → Secrets and variables → Actions → Secrets*,
   crée `NTFY_TOPIC` avec ce même mot.

Le seuil vaut 3 par défaut. Pour le changer, ajoute une *variable* (pas un
secret) nommée `SEUIL_ALERTE`, par exemple `3.5`.

Sans le secret, l'étape est simplement ignorée : le reste du workflow
fonctionne normalement.

`alerter.py` retient dans `etat_alertes.json` les créneaux déjà annoncés.
Sans cette mémoire, le même bon créneau te serait signalé huit fois par jour.
Un créneau n'est annoncé qu'une fois, et seulement s'il est encore à venir.
Pour voir ce qui partirait sans rien envoyer ni rien mémoriser :

```
python3 alerter.py --seuil 3 --essai
```

### Par courriel plutôt que par notification

Si tu préfères un mail, l'astuce sans service tiers consiste à faire créer une
*issue* par le workflow : GitHub envoie nativement un courriel pour chaque
issue ouverte sur un dépôt que tu surveilles. Remplace l'étape « Notifier »
par un appel à `gh issue create` avec le contenu de `message.txt`. Le revers
est que l'onglet Issues se remplit et qu'il faut les refermer.

## Sécurité

Le risque d'orage est un véto : une heure classée « élevé » est notée zéro
quelles que soient les conditions par ailleurs, et les deux heures voisines
passent au moins en « modéré ». Sur l'eau, la règle reste de sortir dès le
premier coup de tonnerre et d'attendre trente minutes après le dernier.
