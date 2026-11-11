# Accessibilité

Pour chaque carreau habité, la plateforme calcule la **distance à vol d'oiseau** à l'équipement le plus proche de chaque famille (formule de haversine), y compris les équipements des communes voisines (marge de 10 km). Multipliée par le **facteur de détour** (1,3 par défaut), elle donne le **trajet estimé**, que la desserte compare au rayon : avec 1,3, un rayon de 1 500 m correspond à environ 1 150 m à vol d'oiseau. Un facteur de 1 revient au vol d'oiseau pur.

## Rayons de desserte

Un habitant est **desservi** si le trajet estimé jusqu'à l'équipement le plus proche est inférieur au rayon de sa famille. Rayons par défaut (modifiables : Administration → Paramètres) :

| Famille | Rayon | Demande prise en compte |
| --- | --- | --- |
| École maternelle / élémentaire | 1 500 m | enfants de 3 à 10 ans |
| Collège | 5 000 m | jeunes de 11 à 14 ans |
| Lycée | 15 000 m | jeunes de 15 à 17 ans |
| Santé (médecin, centre de santé, pharmacie) | 5 000 m | habitants |
| Point d'eau potable | 500 m | habitants |
| Commerce alimentaire / marché | 1 000 m | habitants |
| Transport (arrêt, gare routière, dégrad) | 500 m | habitants |
| Services publics | 3 000 m | habitants |
| Petite enfance | 2 000 m | habitants |

## Indicateurs

- **Taux de desserte** = demande des carreaux desservis / demande totale.
- **Demande non desservie** = demande au-delà du rayon.
- **Distance moyenne** pondérée par la population.
- **Demande rattachée** à un équipement = demande des carreaux pour lesquels il est le plus proche.

## Capacité des écoles

Une école proche mais pleine ne dessert pas un enfant de plus. Pour les écoles, collèges et lycées :

- **places** = nombre de classes (Éducation nationale) × **effectif cible par classe** (paramètre `school_class_size`, 25 par défaut) — ou la capacité saisie « en places » dans l'écran Équipements ;
- si la demande à moins du rayon d'une école dépasse ses places, la part excédentaire de chaque carreau rattaché est comptée **sans place** ;
- **taux de desserte avec une place** = demande desservie et ayant une place / demande totale (affiché à côté du taux de proximité) ; le nombre d'écoles saturées est indiqué ;
- l'aide à l'implantation vise aussi cette demande sans place.

Établissements sans classes publiées (privé) : capacité inconnue, traitée comme illimitée.

## Positions approximatives

L'annuaire de l'Éducation nationale situe certains établissements au **centre du bourg ou du lieu-dit** (précision « Ville », « Lieu-dit ») : ils sont marqués « position approximative » et comptés à part ; les services corrigent leur position dans l'écran Équipements (correction conservée lors des synchronisations).

## Limites

- Les distances sont à vol d'oiseau : un fleuve, une crique ou l'absence de route peuvent allonger fortement le trajet réel (facteur de détour à augmenter en zone de fleuve).
- Les écoles viennent de l'annuaire de l'Éducation nationale ; la santé de **FINESS** (établissements officiels) complété par OpenStreetMap ; les autres familles d'**OpenStreetMap**, dont la complétude est inégale en Guyane : un taux de desserte bas peut traduire une carte incomplète. Les services complètent l'inventaire dans l'écran [Équipements](../ecrans/equipements.md).
- Pas de calcul d'itinéraire sur le réseau réel : le facteur de détour reste une approximation (fleuve, criques).
