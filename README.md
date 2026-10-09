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
- *Petits jours* : sous 0,70 m, la houle reçoit un plancher modeste (1 point
  à 0,45 m, 1,6 à 0,70 m), et le poids du vent passe progressivement de 30 à
  45 % — sur une petite mer, c'est la propreté du plan d'eau qui décide.
  Résultat : 0,45 m à 5 s ressort autour de 2,5 par temps calme, de quoi
  aller jeter un œil, mais retombe vers 1 dès que l'onshore s'en mêle. Rien
  sous 0,30 m. Sous un point de houle, la note globale s'efface
  proportionnellement, pour éviter les sauts près de zéro.
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

**Planche conseillée.** Pour chaque heure, les deux Seaside dont le volume
approche le plus le volume idéal pour la houle du moment. Le volume idéal
part de la hauteur — 47 L à 0,40 m, 38 L à 0,75 m, 33 L à 1,10 m — et gagne
jusqu'à 4 L quand la période est courte, parce qu'une mer molle pousse peu.
Les planches se suivant en volume, la paire proposée contient toujours au
moins une planche que tu possèdes. Une planche pas encore achetée est marquée
d'un astérisque.

**Équipement.** Chaque créneau indique l'épaisseur de combinaison et les
accessoires conseillés. On part de la température de l'eau (au large du
spot), refroidie de 0,25 °C par degré d'écart quand l'air ressenti est plus
froid que l'eau (3 °C au plus) et de 0,1 °C par nœud de vent au-delà de 12
(2 °C au plus). La température effective donne : 3/2 dès 16 °C, 4/3 dès 13,
5/4 dès 10, 6/5 en dessous ; chaussons sous 13 °C, gants sous 11, cagoule
sous 9. Le résumé du jour est prudent : il retient l'eau la plus froide,
l'air ressenti le plus froid et le vent le plus fort de la journée.

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
| `POIDS_SURF_PETIT`, `HAUTEUR_PETIT_JOUR`, `PETITE_HOULE` | réglage des petits jours glassy |
| `VENT_OFFSHORE`, `VENT_ONSHORE` | courbes de note de vent surf selon la force |
| `RIDEUR` | ton poids et tes ailes : les courbes de force wing en dérivent |
| `K_TAILLE` | coefficient de la règle taille ≈ k × poids ÷ vent |
| `WING_RAFALES`, `WING_DIRECTION`, `WING_MAREE`, `WING_MER` | autres courbes de la wing |
| `PLANCHES` | ton quiver de surf : nom, volume, et `possedee` à passer à `True` le jour de l'achat |
| `VOLUME_SELON_HAUTEUR`, `SUPPLEMENT_MER_MOLLE` | règle du volume idéal, à recaler avec le journal |
| `COMBINAISONS`, `CHAUSSONS`, `GANTS`, `SEUIL_CAGOULE` | barème d'équipement selon la température effective |
| `DUREE_SESSION_H` | durée d'une session, 2 h par défaut |
| `FIABILITE_ECHEANCE` | baisse de confiance avec l'échéance |
| `CALIBRATION_HOULE` | facteur correctif de hauteur |
| `CAPE_*`, `LI_*` | seuils de risque orageux |

Les courbes s'écrivent comme des listes de points `(valeur, note)` reliés par
des segments : pour déplacer un seuil, on déplace un point.

## La bouée d'Ambleteuse

La bouée houlographe de Géodunes, mouillée au large d'Ambleteuse à quelques
kilomètres au nord de Wimereux, est lue à chaque calcul. Sa dernière mesure
s'affiche en haut de la page de Wimereux (« En ce moment »), avec la source.

Chaque mesure est aussi archivée dans `observations/ambleteuse.csv`, à côté de
ce que le modèle prévoyait pour la même heure : hauteur, période, direction,
température de l'eau et vent. C'est la base de la calibration à venir — dans
quelques semaines, ce fichier dira de combien le modèle se trompe devant chez
toi, et dans quelles conditions. Une même heure n'est archivée qu'une fois.

Si la bouée est muette (maintenance, perte de signal), l'outil continue sans
elle.

La bouée produit aussi des mesures parasites : environ une heure sur dix, une
période de 20 à 26 s et une hauteur gonflée, par paquets toutes les douze
heures, plutôt vers la basse mer (un artefact du mouillage). Toute mesure dont
la période dépasse 20 s est écartée (`PERIODE_MAX_BOUEE_S`) ; on garde la
dernière mesure plausible.

### Hastings en relais

La bouée Hastings WaveNet (Cefas) est lue à chaque calcul et affichée sous
celle d'Ambleteuse. La comparaison des bouées de la Manche Est montre que, par
houle de sud-ouest (195-285° à Hastings), Ambleteuse mesure à peu près la même
hauteur que Hastings. Dans ce secteur seulement, la mesure de Hastings est
transposée à Wimereux et notée : si Ambleteuse est muette, c'est elle qui
déclenche l'alerte « bonne surprise », en le disant. Chaque mesure est
archivée dans `observations/hastings.csv` : avec `ambleteuse.csv`, ce sera la
base du coefficient de transfert par direction, quand il y aura assez de
semaines communes.

### Alerte « bonne surprise »

À chaque calcul, la mesure de la bouée est notée avec le barème surf : la houle
mesurée remplace la houle prévue, le vent, la marée et le risque d'orage restent
ceux de l'heure. Si cette note mesurée atteint 3,5 et dépasse d'au moins un
point la note que la prévision donnait pour la même heure, une notification
part en priorité haute : les conditions sont meilleures que prévu, maintenant.

Elle ne part que pour une mesure de moins de deux heures, de jour, et une seule
fois par épisode (pas de nouvelle alerte de ce type pendant six heures). Les
seuils se règlent en tête d'`alerter.py` (`SEUIL_SURPRISE`, `ECART_SURPRISE`).

Le calcul tourne toutes les trois heures : seul, il pourrait laisser passer une
embellie entre deux. D'où un second contrôle, calé sur la marée.

### Contrôle à la pleine mer

Le workflow « Bouée à la pleine mer » (`.github/workflows/maree.yml`, script
`verif_maree.py`) se réveille toutes les 20 minutes en journée. Il regarde dans
`docs/data.json` l'heure de la prochaine pleine mer de Wimereux et ne fait
quelque chose qu'à deux moments : **une heure avant la pleine mer**, puis **à la
pleine mer**. Le reste du temps, il s'arrête en quelques secondes sans rien lire.

À ces deux moments, il lit la bouée, note la mesure avec le barème surf, la
compare à la prévision de la même heure et ne prévient qu'en cas de bonne
surprise, avec les mêmes critères que ci-dessus. La pause de six heures est
commune aux deux alertes : jamais deux notifications pour le même épisode. La
nuit (pas de créneau de jour), il ne fait rien.

Chaque moment n'est contrôlé qu'une fois, même si GitHub lance la tâche en
retard (jusqu'à 45 minutes, ce qui arrive). La mesure lue est archivée dans
`observations/ambleteuse.csv` comme les autres, et le dernier contrôle est
noté dans `etat_maree.json` (heure, mesure, note mesurée et prévue) : c'est là
qu'on vérifie qu'il a bien tourné.

Pour l'essayer tout de suite : onglet Actions → « Bouée à la pleine mer » →
Run workflow, en cochant « Contrôler tout de suite ». Le seuil se règle avec la
variable de dépôt `SEUIL_SURPRISE` (3,5 par défaut).

## Calais : la houle qui contourne le cap Gris-Nez

La fenêtre de houle de Calais est tournée vers le nord. Une houle de sud-ouest
y était donc notée zéro, alors qu'une partie contourne le cap Gris-Nez : à
Gravelines, elle garde environ 55 % de sa hauteur de Hastings et arrive du
nord-ouest (290-310°). Calais calcule donc deux houles et garde la meilleure :
celle du large au point du spot, et celle du sud-ouest contournée (houle du
point de Wimereux × 0,5, venant du 300°). Le créneau porte alors
`houle_contournee: true`. Hypothèse prudente, à confirmer au journal.

La bouée de référence affichée pour Calais est maintenant Goodwin Sands : le
bateau-feu de Sandettie sous-estime la mer courte.

## Le journal

Tous les réglages ci-dessus sont des hypothèses raisonnables, pas des mesures.
Le journal est ce qui les rendra justes.

### Remplir

Le plus simple : le bloc **Noter une session ou une observation** en bas de
la page. Il prépare la ligne, la copie, et ouvre `journal.csv` en édition sur
GitHub ; il ne reste qu'à coller à la fin du fichier et valider.

Format d'une ligne :

```
date,heure,spot,discipline,type,conditions,session,planche,commentaire
2026-09-27,16,wimereux,surf,session,4,3,5'6,belles séries mais du monde
2026-09-28,11,calais,wing,observation,2,,,vent tombé à midi
```

- `discipline` : `surf` ou `wing`.
- `type` : `session` si tu étais à l'eau, `observation` si tu as seulement
  regardé la mer.
- `conditions` : la qualité de la mer et du vent, de 1 à 5. C'est **elle**
  qu'on compare à la note calculée.
- `planche` : la planche utilisée, pour une session de surf seulement.
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
montre comment la prévision se dégrade avec son ancienneté, et dresse un
bilan par planche : dans quelle houle tu l'as prise, ce que tu en as pensé,
et combien de fois elle correspondait au conseil. C'est ce bilan qui servira
à recaler la règle de volume. En dessous
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

Seuil, en *variable* du dépôt (pas en secret) : `SEUIL_ALERTE`, 3 par défaut.
Seul le surf déclenche des notifications : la wing reste notée sur la page,
mais ne prévient plus. Pour la réactiver, ajoute `("wing", "session_wing")` à
`DISCIPLINES_ALERTE` dans `alerter.py` ; son seuil se règle alors avec
`SEUIL_ALERTE_WING`.

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
