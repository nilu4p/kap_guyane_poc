# Grille de 200 m

Toutes les couches spatiales (bâti, population, enfants, accessibilité, croissance, bâtiments, eau) sont calculées sur **une seule grille** couvrant la Guyane.

## Définition

- Grille alignée sur les longitudes / latitudes, ancrée en 1,5° N / 55,5° O.
- Hauteur d'un carreau : `200 / 110 574` degré de latitude ; largeur : `200 / (111 320 × cos 4°)` degré de longitude.
- Entre 2° N et 6° N, la dimension est-ouest varie de moins de 0,3 % : chaque carreau fait 200 m × 200 m (4 ha) à mieux que 1 % partout en Guyane.
- Identifiant d'un carreau : `ligne_colonne` (ligne comptée vers le nord, colonne vers l'est). Il est **stable** d'une commune à l'autre et d'une année à l'autre, ce qui permet de suivre un même carreau dans le temps et de le transmettre à l'INSEE.

## Pourquoi 200 m

- C'est la maille du **carroyage INSEE** (Filosofi carroyé) : les résultats se comparent aux produits statistiques nationaux.
- C'est le **plancher éthique** de la charte : à 200 m, un carreau urbain regroupe des dizaines de bâtiments ; aucune construction individuelle ne peut être désignée.
- C'est l'échelle de la décision : une école dessert un rayon de 1,5 km, un point d'eau quelques centaines de mètres.

!!! warning "Aucune couche plus fine"
    Les pixels Sentinel-2 (20 m) et les empreintes de bâtiments ne vivent qu'en mémoire pendant le calcul. L'API, la base de données, les exports et les documents ne contiennent **que** des carreaux de 200 m.
