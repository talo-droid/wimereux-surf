# Prévisions de surf et de wing — Côte d'Opale

Notation des sessions de **surf** et de **wing** à **Wimereux** et à
**Calais**, calculée toutes les 3 heures par GitHub Actions et publiée sur une
page consultable au téléphone, avec des alertes quand une bonne session se
profile.

Les deux spots ne se ressemblent pas et sont paramétrés séparément :

| | Wimereux | Calais |
|---|---|---|
| Bouée de référence | Hastings (CEFAS) | Sandettie |
| La plage regarde vers | l'ouest-nord-ouest | le nord |
| Fenêtre de houle | 200-270° | 300-60° |
| Optimum de marée (surf) | 1 h après la PM | 1 h 30 avant la PM |
| Période de houle visée | 5,5 à 7,5 s | 4,5 à 6,5 s |
| Port de marée | Boulogne-sur-Mer | Calais |
| Trajet depuis chez toi | 0 min | 35 min |

## Comment la note est construite

**Principe commun.** Chaque note est une *moyenne géométrique* de sous-notes
sur 5. Contrairement à une moyenne ordinaire, un critère mauvais n'y est pas
compensé par les autres : une houle parfaite ne sauve pas un vent pourri. Tous
les barèmes sont continus, sans marche où deux centimètres ou un degré
feraient basculer la note. Le seul véto restant est l'orage, parce qu'il
relève de la sécurité : risque élevé, note nulle ; risque modéré, note
plafonnée à 2,5.

**Surf** = houle (poids 0,5) × vent (0,3) × marée (0,2).

- *Houle* : jusqu'à 3 points de hauteur et 2 de période, plus ou moins un
  demi-point selon le type de déferlement (nombre d'Iribarren) et selon la
  part d'énergie portée par la houle longue ; le tout multiplié par la
  fenêtre de direction, qui s'éteint progressivement sur 15° au lieu de
  couper net.
- *Vent* : projeté sur l'axe de la plage, il passe continûment d'une courbe
  « offshore » à une courbe « onshore » selon l'angle ; les rafales retirent
  jusqu'à un point et demi.
- *Marée* : position dans le cycle × stabilité de la zone de déferlement
  (vitesse à laquelle le bord de l'eau se déplace sur l'estran).
- Le RTR (marnage rapporté à la houle) est affiché mais n'entre plus dans la
  note : il dépend du coefficient, comme la stabilité, et le compter deux fois
  pénalisait doublement les vives-eaux.

**Wing** = rafales × niveau d'eau × état de la mer, en moyenne géométrique,
puis multipliés par deux facteurs : la **force du vent**, qui agit comme une
condition (sous-toilé ou débordé, le reste ne compte plus), et un **facteur
de sécurité** qui divise la note par dix quand le vent pousse vers le large.
Ce dernier utilise l'orientation réelle de la plage (`face_plage`), pas l'axe
de préférence du surf.

Les courbes de force sont déduites de ton matériel, déclaré dans `RIDEUR` :
poids et tailles d'ailes. Le vent idéal d'une aile suit la règle usuelle des
fabricants, taille ≈ 1,10 × poids ÷ vent, majorée pour un niveau
intermédiaire. Le bas de la courbe vient de la plus grande aile, le haut de
la plus petite. Pour 75 kg avec 4,5 / 5 / 5,5 m² : rien sous 12 nœuds, bon dès
15, plein régime de 17 à 23, puis déclin rapide au-delà de 25 ou avec des
rafales au-dessus de 28. Chaque créneau indique aussi l'aile conseillée. Si
ton quiver change, modifie seulement `RIDEUR`.

**Sessions.** On note des heures, mais on surfe des sessions : la « meilleure
session » est la meilleure fenêtre de deux heures consécutives de jour.

**Fiabilité.** Chaque note porte une confiance entre 0 et 1, qui baisse avec
l'échéance et quand les modèles se contredisent. Sur la page, les carrés
d'une prévision peu fiable sont plus pâles.

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

Tout se règle en tête de `previsions.py`. Le dictionnaire `SPOTS` contient ce
qui distingue les deux spots :

| Clé | Rôle |
|---|---|
| `point_houle`, `point_vent` | points de calcul — à garder figés |
| `direction_houle`, `marge_direction` | fenêtre de houle et largeur de son extinction |
| `pic_maree_h` | optimum de marée surf, en heures par rapport à la PM |
| `axe_offshore_surf` | direction de vent idéale pour le surf, issue de l'expérience |
| `face_plage` | direction vers laquelle la plage regarde, pour la sécurité wing — **à vérifier** |
| `trajet_min` | temps pour être à l'eau, utilisé par les alertes |
| `seuils_houle` | barème de houle propre au spot |
| `pente_haute`, `pente_basse` | profil de plage, pilote Iribarren et la translation — **estimations** |

Réglages communs :

| Constante | Rôle |
|---|---|
| `POIDS_SURF`, `POIDS_WING`, `POIDS_MAREE` | poids des moyennes géométriques |
| `VENT_OFFSHORE`, `VENT_ONSHORE` | courbes de note de vent surf selon la force |
| `RIDEUR` | ton poids et tes ailes : les courbes de force wing en dérivent |
| `K_TAILLE` | coefficient de la règle taille ≈ k × poids ÷ vent |
| `WING_RAFALES`, `WING_DIRECTION`, `WING_MAREE`, `WING_MER` | autres courbes de la wing |
| `DUREE_SESSION_H` | durée d'une session, 2 h par défaut |
| `FIABILITE_ECHEANCE` | baisse de confiance avec l'échéance |
| `CALIBRATION_HOULE` | facteur correctif de hauteur |
| `CAPE_*`, `LI_*` | seuils de risque orageux |

Les courbes s'écrivent comme des listes de points `(valeur, note)` reliés par
des segments : pour déplacer un seuil, on déplace un point.

## Le journal

Tous les réglages ci-dessus sont des hypothèses raisonnables, pas des mesures.
Le journal est ce qui les rendra justes.

### Remplir

Le plus simple : le bloc **Noter une session ou une observation** en bas de
la page. Il prépare la ligne, la copie, et ouvre `journal.csv` en édition sur
GitHub ; il ne reste qu'à coller à la fin du fichier et valider.

Format d'une ligne :

```
date,heure,spot,discipline,type,conditions,session,commentaire
2026-09-27,16,wimereux,surf,session,4,3,belles séries mais du monde
2026-09-28,11,calais,wing,observation,2,,vent tombé à midi
```

- `discipline` : `surf` ou `wing`.
- `type` : `session` si tu étais à l'eau, `observation` si tu as seulement
  regardé la mer.
- `conditions` : la qualité de la mer et du vent, de 1 à 5. C'est **elle**
  qu'on compare à la note calculée.
- `session` : ton plaisir, de 1 à 5, vide pour une observation. Il dépend
  aussi de la fatigue, du monde à l'eau et du matériel ; il est conservé mais
  jamais comparé au modèle.

**Note aussi les jours où tu n'y vas pas.** Tu iras surtout quand la
prévision est bonne : sans observations, tu n'apprendrais que les erreurs par
excès d'optimisme, jamais les bonnes journées que le calcul a ratées. Depuis
Wimereux, un coup d'œil à la mer suffit.

Les lignes à l'ancien format (`date,heure,spot,note,commentaire`) restent
lues : la note unique vaut alors pour les conditions et la session.

### Analyser

```
python3 analyser.py
python3 analyser.py --spot calais --discipline wing
```

Pour chaque discipline, le script affiche l'écart entre conditions observées
et note calculée, compte les bonnes conditions ratées et les fausses
promesses, classe les critères selon leur lien avec les conditions observées,
et montre comment la prévision se dégrade avec son ancienneté. En dessous
d'une douzaine d'entrées, les corrélations sont du bruit, et le script le
dit.

Règle d'or : ajuster peu de paramètres, les plus influents d'abord. Avec une
vingtaine de réglages et quelques dizaines d'entrées, tout retoucher revient à
caler l'outil sur du bruit.

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

Au-delà de deux jours, le global du Met Office (10 km, 7 jours) prend le
relais : même physique que l'UKV, donc une prévision cohérente. Le Met Office
fait tourner l'UKV jusqu'à 120 h, mais Open-Meteo n'en redistribue que 48.
ARPEGE puis le choix automatique d'Open-Meteo servent de secours ultimes. Le modèle utilisé s'affiche dans l'infobulle de chaque case de
vent, et un cadre pointillé signale un désaccord d'au moins 5 nœuds.

Le vent est calculé un peu au large (`point_vent` dans `SPOTS`) : posé sur le
trait de côte, une maille de 1,5 à 2 km mélange terre et mer, et la rugosité
du sol freine artificiellement le vent.

Pour privilégier un seul modèle, ajoute la variable de dépôt `MODE_VENT` avec
`arome` ou `ukv` (par défaut : `moyenne`), et ajoute-la à la section `env`
de l'étape « Calculer les notes » du workflow.

## Recevoir une notification

Le workflow prévient par **ntfy** : gratuit, sans compte, l'application
Android reçoit la notification directement.

1. Installe *ntfy* depuis le Play Store.
2. Choisis un sujet à toi, long et impossible à deviner. Génère-le plutôt
   que de l'inventer :
   `python3 -c "import secrets; print('opale-' + secrets.token_hex(6))"`.
   Toute personne connaissant ce mot peut lire tes notifications — et en
   envoyer —, alors ne le publie nulle part.
3. Dans l'application, abonne-toi à ce sujet.
4. Dans le dépôt, *Settings → Secrets and variables → Actions → Secrets*,
   crée `NTFY_TOPIC` avec ce même mot.

Seuils, en *variables* du dépôt (pas en secrets) : `SEUIL_ALERTE` pour le surf
et `SEUIL_ALERTE_WING` pour la wing, 3 par défaut tous les deux.

`alerter.py` raisonne par meilleure session de chaque jour, et envoie quatre
sortes de lignes :

- **NOUVEAU** — une journée passe au-dessus du seuil ;
- **MIEUX** — une session déjà annoncée gagne au moins 0,75 point ;
- **ANNULÉ** — une session annoncée retombe nettement sous le seuil ;
- **MAINTENANT** — une bonne session commence dans les trois heures, compte
  tenu du trajet (`trajet_min`). Celle-ci sonne en priorité haute.

Il retient ce qui a déjà été annoncé dans `etat_alertes.json`, pour ne pas
répéter la même alerte huit fois par jour. Sans le secret `NTFY_TOPIC`,
l'étape est simplement ignorée. Pour voir ce qui partirait sans rien envoyer
ni rien mémoriser :

```
python3 alerter.py --seuil 3 --seuil-wing 3 --essai
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
