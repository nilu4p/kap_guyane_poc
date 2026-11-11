# Bâti par satellite (fusion multi-sources)

La surface bâtie de chaque carreau de 200 m est reconstituée de **1985 à la dernière saison sèche** en fusionnant trois produits satellitaires.

| Période | Source | Résolution | Rôle |
| --- | --- | --- | --- |
| 1985 → 2015 | **WSF Evolution** (DLR, archive Landsat) | 30 m | année d'urbanisation de chaque pixel : croissance historique, tous les 5 ans |
| 2019 | **WSF 2019** (DLR, Sentinel-1 + Sentinel-2) | 10 m | **référence** de surface bâtie |
| 2016 → aujourd'hui | **Sentinel-2 L2A**, composites de saison sèche calculés par la plateforme | 20 m | évolution année par année depuis la référence |
| actuel (dates mixtes) | **Empreintes Microsoft** (Global ML Building Footprints) | bâtiments | nombre de bâtiments par hectare bâti (pour compter) |

Les fichiers WSF sont des COG lus par plages HTTP (seule la fenêtre utile est téléchargée) ; Sentinel-2 est lu dans l'archive publique AWS (Earth Search, sans clé).

## 1. Où lire : les fenêtres d'analyse

Une commune de l'intérieur couvre des milliers de km² de forêt. Un aperçu rapide de WSF 2019 repère les **blocs habités** (6,4 km de côté) ; autour des bourgs importants les blocs voisins sont ajoutés (les nouveaux quartiers poussent en bordure) — jamais de l'autre côté du fleuve. Les blocs contigus sont fusionnés en rectangles, dans la limite de `max_analysis_area_km2` (900 km² par défaut).

## 2. Composite Sentinel-2 de saison sèche

1. **Scènes** : août → décembre (les mois les moins nuageux), nuages < 40 %, les 4 scènes les plus claires de chaque tuile MGRS (une acquisition retraitée n'est comptée qu'une fois).
2. **Bandes** : B11 (SWIR 1,6 µm), B8A (PIR), B4 (rouge), B3 (vert) et la classification SCL, rééchantillonnées à 20 m sur une sous-grille alignée sur les carreaux (10 × 10 pixels par carreau). Réflectance = valeur × échelle + décalage (le décalage de la ligne de traitement 04.00 est géré).
3. **Masques** : nuages, ombres, cirrus, saturation, absence de donnée (SCL). **Eau** : SCL classe 6 **ou** MNDWI = (B3 − B11)/(B3 + B11) > 0,1 — indispensable pour les fleuves turbides (Maroni, Oyapock) que SCL seul manque.
4. Pour chaque pixel, **médiane** des observations claires de la saison : NDBI = (B11 − B8A)/(B11 + B8A), NDVI = (B8A − B4)/(B8A + B4), et le **score de bâti** s = NDBI − NDVI.

## 3. Calibration sur WSF 2019

Le seuil *t* au-delà duquel un pixel est « bâti » est choisi sur l'année de référence (2019, ou l'année observée la plus proche) par **appariement de quantile** : la surface bâtie mesurée par Sentinel-2 égale celle de WSF 2019 sur la même zone. Le calcul se fait sur le **voisinage habité** (carreaux à moins de 1 km d'un carreau bâti en 2019 ou en 2015), pas sur la forêt où la part de bâti serait infime et le seuil instable.

**Qualité** : les deux produits sont comparés carreau par carreau sur ce voisinage (carreaux vus bâtis par au moins l'un des deux) — corrélation, concordance bâti / non bâti, précision, rappel et **F1**. La note affichée partout en découle :

| Note | Condition | Conséquence |
| --- | --- | --- |
| **bonne** | F1 ≥ 0,6 et ≥ 200 carreaux comparés | série appliquée ; contrôle visuel d'un échantillon recommandé |
| **moyenne** | F1 ≥ 0,45 et ≥ 100 carreaux | série appliquée, tendances indicatives |
| **faible** | sinon | **série non appliquée** : la référence WSF 2019 est conservée pour toutes les années après 2016 |

## 4. Harmonisation des saisons

D'une année à l'autre, la pluie, l'angle solaire et la sécheresse des sols changent les indices : avec un seuil unique, des villes entières « grandiraient » ou « rétréciraient ». Chaque saison est normalisée linéairement sur deux **cibles pseudo-invariantes** — le noyau bâti stable (≥ 60 % bâti en 2019 et en 2015) et la végétation stable (jamais habitée) — : le seuil de référence appliqué aux scores normalisés équivaut au seuil `(t − b)/a` sur les scores bruts.

## 5. Part bâtie du carreau

Part des pixels valides du carreau dont le score dépasse le seuil de l'année. Un carreau avec moins de 30 % de pixels clairs est **indéterminé** cette année-là ; un carreau à plus de 90 % d'eau vaut 0.

## 6. Fusion

Pour chaque carreau (part bâtie *F*, entre 0 et 1) :

- **2019** : `F = WSF 2019`.
- **2016 → aujourd'hui** : `F(y) = clip(WSF2019 + Δ(y), 0, 1)` avec `Δ(y) = S̃(y) − S̃(2019)`. Sentinel-2 ne mesure que le **changement** par rapport à la référence, ce qui annule son propre biais. `S̃` est la série du carreau :
    - années indéterminées remplies par l'année observée la plus proche ;
    - **médiane glissante sur 3 ans** (bruit saisonnier) ;
    - **régression isotone** (série non décroissante) : à 200 m, le bâti recule rarement ; une saison qui paraît « plus bâtie » que les suivantes est mise en commun avec elles au lieu de créer un faux pic. *Conséquence : une démolition (résorption d'habitat insalubre) apparaît comme une stagnation de la courbe.*
- **Seuil de bruit** τ : un changement plus petit que τ est ignoré. τ est le 95ᵉ percentile de |Δ| sur les carreaux invariants (jamais habités), borné à [0,05 ; 0,3] : sans lui, le bruit positif de milliers de carreaux de forêt (le négatif étant tronqué à 0) s'additionnerait en fausse croissance.
- **Plausibilité** : un changement n'est retenu qu'**à moins de 1 km du bâti existant** (2019 ou 2015). Les pixels « bâtis » isolés en rizière, savane ou plage sont des sols nus de saison sèche, pas des quartiers. Limite assumée : un lotissement créé ex nihilo à plus de 1 km de tout bâti n'est pas compté avant qu'il apparaisse dans une référence.
- **1985 → 2015** : `F(y) = F(2016) × WSF-E(y) / WSF-E(2015)` : chaque carreau garde sa croissance relative de l'archive Landsat et rejoint sa valeur 2016 sans rupture.
- Carreaux habités hors des fenêtres Sentinel-2 (petits écarts) : valeur de référence pour toutes les années, signalés.

!!! warning "Rupture de série 2015 / 2016"
    WSF Evolution (Landsat, 30 m) ne voit pas l'habitat diffus et les petites constructions que la référence à 10 m détecte. L'écart entre 2015 et 2016 est un **changement de capteur**, pas une croissance : il est signalé sur les graphiques.

## 7. Bâtiments

Les empreintes Microsoft (dalles « quadkey » de niveau 9) sont lues ligne à ligne ; chaque polygone est réduit à son centroïde et à sa surface, compté dans son carreau, puis oublié. On en déduit le nombre de **bâtiments par hectare bâti** de la commune, qui convertit les hectares gagnés en ordre de grandeur de bâtiments. Les dates d'imagerie sont mixtes (2014 → 2024) et la couverture peut être incomplète : ces comptes ne forment pas une série datée.

## Limites

- Résolution : les cases traditionnelles et carbets isolés sous couvert arboré échappent largement aux capteurs à 10-20 m.
- Saison sèche courte certaines années (nuages) : années indéterminées signalées (*années observées* dans l'atlas).
- Les sols nus des chantiers sont comptés comme « bâti » (c'est souvent le signe d'une urbanisation en cours).
- La validation de référence se fait par **contrôle visuel** sur image très haute résolution (Pléiades Neo, SEAS Guyane) : objectif ≥ 80 % de concordance sur 50 carreaux tirés au sort.
