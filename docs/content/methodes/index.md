# Méthodes et calculs

Chaque chiffre affiché par la plateforme est soit une **donnée publiée** (INSEE, Éducation nationale, OpenStreetMap…), soit le résultat d'un **calcul documenté ici**, avec ses hypothèses et ses limites. Les estimations sont toujours nommées comme telles dans l'interface et dans les documents signés.

```text
 Données publiées                    Calculs de la plateforme                         Décision
 ────────────────                    ───────────────────────                          ────────
 WSF Evolution 1985-2015 ─┐
 WSF 2019 (10 m) ─────────┼──► Bâti par carreau 1985 → aujourd'hui ──┐
 Sentinel-2 (saison sèche)┘    (fusion, calibration, qualité)        │
 Empreintes Microsoft ──────► Bâtiments par hectare bâti ────────────┤
 Population légale INSEE ───► Population par carreau (dasymétrie) ───┼──► Accessibilité ──► Implantation
 Âges du recensement ───────► Enfants par carreau ───────────────────┘        ▲               (couverture max.)
 Annuaire scolaire, OSM, saisies ─► Équipements ────────────────────────────┘               │
 OSM routes, WDPA, eau S2 ────────► Contraintes ─────────────────────────────────────────────┘
```

| Page | Contenu |
| --- | --- |
| [Grille de 200 m](grille.md) | le support commun de toutes les couches, et pourquoi 200 m |
| [Bâti par satellite](bati-satellite.md) | WSF, Sentinel-2, calibration, harmonisation, seuil de bruit, garde-fou qualité |
| [Population par carreau](population.md) | répartition de la population légale sur le bâti, enfants, hypothèse communale |
| [Accessibilité](accessibilite.md) | distance à l'équipement le plus proche, rayons, taux de desserte |
| [Aide à l'implantation](implantation.md) | couverture maximale gloutonne, contraintes, « pourquoi ici », classes |
| [Veille et Recensement Éclaireur](veille-recensement.md) | quartiers en croissance, liste RIL, règle de secret |
| [Indicateurs statistiques](indicateurs.md) | formules des 46 indicateurs des fiches communes |
