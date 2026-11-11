# Atlas

Carte de la commune au **carreau de 200 m**.

## Couches

| Couche | Valeur du carreau |
| --- | --- |
| Part bâtie | part du carreau bâtie l'année choisie |
| Surface bâtie gagnée | hectares gagnés (ou perdus) entre l'année « depuis » et l'année choisie |
| Habitants estimés | population du carreau ([méthode](../methodes/population.md)) |
| Enfants de 3 à 10 ans | enfants estimés du carreau |
| Accessibilité | distance à l'équipement le plus proche de la famille choisie : vert ≤ ½ rayon, vert clair ≤ rayon, puis jaune, orange, rouge, rouge sombre au-delà de 4 rayons |
| Bâtiments | nombre d'empreintes Microsoft dont le centre est dans le carreau |
| Plan d'eau | part du carreau en eau (Sentinel-2) |

- **Curseur d'année** : le fond **Sentinel-2 sans nuages** (mosaïques annuelles EOX, dès 2016) suit l'année.
- **Hypothèse communale** : recalcule population, enfants et accessibilité sur l'estimation de la commune.
- **Équipements** : losanges colorés par famille ; pointillés = provisoire ou en projet.
- **Sentinel-2 récente** : la scène la plus claire des 90 derniers jours, à 10 m, servie par la plateforme.
- **Aires protégées** (WDPA).
- **Clic sur un carreau** : fiche du carreau — courbe de sa part bâtie, habitants et enfants estimés, bâtiments, équipement le plus proche de chaque famille (distance à vol d'oiseau et trajet estimé).
- **Qualité de l'analyse satellitaire** : note (bonne / moyenne / faible), concordance et F1 avec WSF 2019, années observées. Voir [Bâti par satellite](../methodes/bati-satellite.md).

Si l'analyse de la commune n'existe pas encore, un bouton la lance (Chargé d'études).
