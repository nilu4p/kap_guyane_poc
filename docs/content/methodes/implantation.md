# Aide à l'implantation

## Problème résolu

Choisir **k** sites pour de nouveaux équipements d'une famille de façon à desservir le plus possible de **demande aujourd'hui non desservie** (habitants, ou enfants de l'âge concerné) dans le rayon de la famille. C'est le problème de couverture maximale (MCLP).

## Algorithme

Couverture maximale **gloutonne**, explicable étape par étape :

1. Demande résiduelle de chaque carreau = sa demande s'il n'est pas desservi par un équipement existant, provisoire ou en projet ; pour les écoles, s'y ajoute la part **sans place** quand l'école la plus proche est saturée (voir [capacité des écoles](accessibilite.md#capacite-des-ecoles)).
2. Pour chaque **carreau candidat**, gain = somme de la demande résiduelle dans le rayon.
3. Le candidat au plus grand gain est retenu ; la demande qu'il couvre est marquée desservie ; les candidats à moins de l'espacement minimal (par défaut le rayon) sont écartés.
4. On recommence jusqu'à *k* sites (ou plus aucun gain).

L'algorithme glouton atteint au moins 63 % de l'optimum théorique et chaque choix se justifie simplement.

## Contraintes sur les candidats

| Contrainte | Donnée | Défaut |
| --- | --- | --- |
| dans la commune | contour IGN | toujours |
| près des habitants | au moins un carreau habité dans le rayon | toujours |
| hors plan d'eau | masque d'eau Sentinel-2 (SCL + MNDWI) | activée |
| place disponible | part bâtie du carreau | ≤ 60 % |
| desservi par une route | routes OpenStreetMap | ≤ 500 m |
| hors protection stricte | WDPA : réserves naturelles et biologiques, UICN I à IV | signalée ; exclue sur option |
| protection encadrée | WDPA : parc naturel régional, aire d'adhésion du Parc amazonien, site Ramsar, UICN V-VI | signalée seulement (territoires habités : les exclure exclurait les bourgs) |

## « Pourquoi ici »

Chaque site proposé affiche : la demande non desservie (ou sans place) qu'il couvrirait, la distance actuelle à l'équipement le plus proche, la croissance du bâti depuis 2019 dans sa zone de desserte, les habitants estimés dans le rayon, et les **vérifications** (ok / attention / non vérifié). Pour les écoles, le nombre de **classes** est estimé avec le nombre moyen d'élèves par classe des écoles publiques de la commune.

!!! warning "Ce que la plateforme ne sait pas"
    Le cadastre (API Carto IGN) donne un **résumé agrégé** du carreau proposé — nombre de parcelles, plus grande parcelle, parcelles de plus de 5 000 m² — sans identifiant ni propriétaire. La **propriété** (l'État détient l'essentiel du foncier guyanais), les **risques naturels** (PPRI, mouvements de terrain), les **réseaux** et l'accès réel ne sont pas connus : chaque site porte la mention « à vérifier (DGTM, EPFAG) ». La proposition est un point de départ pour les services, pas une décision.

## Scénarios

Les sites proposés peuvent être déplacés (glisser-déposer), complétés à la main, réévalués, puis enregistrés comme **scénario** (avant / après mémorisé). Un *Responsable* valide ou archive un scénario. **À la validation, l'évaluation est figée** (avant / après, sites, hypothèses, date de l'analyse) : le dossier d'implantation signé reprend exactement ces chiffres, même si les données changent ensuite ; un scénario non validé est recalculé sur les données du jour, et le document le dit.
