# Veille et Recensement Éclaireur

## Quartiers en croissance

- Carreaux dont la surface bâtie a augmenté d'au moins **0,4 ha** (10 % du carreau) depuis l'année choisie (2019 par défaut).
- Regroupés en **foyers** (carreaux contigus) de plus de 1 ha gagné.
- Pour chaque foyer : hectares gagnés, **bâtiments estimés** (hectares × bâtiments par hectare bâti de la commune), **habitants estimés** (hectares × densité calibrée), distance à l'école, au point d'eau et à l'équipement de santé le plus proches, et un **repère** (l'école la plus proche) pour le situer sans désigner d'adresse.
- Un foyer « loin d'une école » est à plus du rayon de desserte scolaire.
- Après chaque analyse, le canal **#veille** reçoit un résumé (au plus une fois par jour et par commune).

## Recensement Éclaireur (appui au RIL)

Dans les communes de 10 000 habitants ou plus, l'INSEE recense chaque année un échantillon de logements tiré du **répertoire d'immeubles localisés (RIL)**. Un quartier nouveau absent du RIL est sous-représenté. La liste « Recensement Éclaireur » donne, avant la collecte de janvier, les **carreaux de 200 m** où le bâti a augmenté, pour que l'INSEE et le coordonnateur communal y vérifient le RIL.

Contenu de l'export (CSV, `;`) : identifiant du carreau, latitude et longitude du **centre** du carreau, hectares gagnés, bâtiments estimés, part bâtie actuelle — et l'avertissement de la charte en tête de fichier.

!!! success "Règle de secret"
    Un carreau dont la croissance représente moins de **5 bâtiments estimés** (paramètre `privacy_min_buildings`) n'est **pas listé** individuellement : il est cumulé dans une ligne « autres carreaux ». Un carreau ne doit jamais permettre de viser un ménage.

La même règle s'applique **à l'écran** (atlas, fiche carreau) : dans un carreau de moins de 5 bâtiments, le nombre de bâtiments s'affiche « < 5 », les habitants et enfants ne sont pas affichés, la part bâtie est arrondie à 5 %, et les gains de bâti plus petits que la surface de 5 bâtiments ne sont pas montrés. Les calculs (accessibilité, implantation) utilisent les valeurs exactes.

L'export est réservé aux chargés d'études et **inscrit au journal d'audit** ; la version signée est émise par un responsable (registre des [rapports](../ecrans/rapports.md)).

## Usage

Présenter la liste comme un **appui à la collecte**, co-construit avec l'INSEE Antilles-Guyane — jamais comme une « contre-statistique ».
