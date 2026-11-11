# Indicateurs statistiques

Les fiches communes stockent des **comptes bruts** (population, logements sans électricité, médecins…) et dérivent les taux au moment de l'affichage : une définition ne peut pas diverger d'un écran à l'autre. Chaque indicateur est calculé avec la même formule pour la **Guyane** (comparaison) et classé parmi les **22 communes** (rang 1 = valeur la plus haute, ou la plus basse quand une valeur basse est préférable).

| Thème | Indicateur | Formule | Source |
| --- | --- | --- | --- |
| Démographie | Population municipale légale | dernier millésime | INSEE, populations historiques |
| | Croissance annuelle moyenne sur 6 ans | `(P_N / P_N−6)^(1/6) − 1` | idem |
| | Densité | population / surface (IGN) | idem |
| | Naissances domiciliées, taux de natalité | naissances / population × 1 000 | INSEE, état civil |
| | Part des moins de 15 ans, des 65 ans ou plus | recensement | INSEE, population par âge |
| Éducation | Élèves des écoles publiques du 1er degré, évolution sur 5 rentrées, élèves par classe | somme par commune (rattachement par UAI) | Éducation nationale, effectifs et classes |
| | Scolarisation des 2-5, 6-10, 11-14, 15-17 ans | inscrits / population de l'âge | INSEE, scolarisation |
| | Écoles, collèges | BPE C107-C109, C201 | INSEE, BPE |
| Santé | Médecins généralistes, infirmiers, sages-femmes, dentistes, pharmacies | pour 10 000 habitants (BPE D265, D281, D278, D277, D307) | INSEE, BPE |
| | Centres et maisons de santé, PMI, urgences | BPE D108 + D113, D115, D106 | INSEE, BPE |
| Eau, énergie, logement | Résidences principales sans électricité | ELEC = non / total | INSEE, logements dans les DOM |
| | Sans point d'eau intérieur ou eau froide seulement | modalité INSEE « aucun point d'eau ou eau froide seulement » | idem |
| | Eaux usées à même le sol, tout-à-l'égout | évacuation des eaux usées | idem |
| | Habitations de fortune ou cases traditionnelles | type de logement | idem |
| | Sans baignoire / douche et WC | idem | idem |
| Emploi | Chômage 15-64 ans, 15-24 ans (au sens du recensement), activité, sans diplôme | recensement | INSEE, population active |
| Commerces | Commerces alimentaires pour 1 000 habitants ; hyper / supermarchés ; supérettes / épiceries ; boulangeries | BPE B104-B105, B201-B210 | INSEE, BPE |
| Services | France services, poste, France Travail, gendarmerie / police, accueil du jeune enfant, transports | BPE A128, A206-A208, A122, A104 + A140, D502, E1 | INSEE, BPE |

!!! info "Précautions de lecture"
    - « Sans point d'eau ou eau froide seulement » **n'est pas** « sans eau » : c'est la modalité exacte du recensement, qui regroupe l'absence de point d'eau intérieur et l'eau froide seule.
    - Le chômage du recensement (déclaratif) diffère du chômage au sens du BIT.
    - La BPE recense des équipements déclarés : leur présence ne dit rien de leur capacité ni de leur accessibilité.
    - **FiLoSoFi** (revenus, pauvreté) n'est pas diffusé pour les communes de Guyane : aucun indicateur de revenu n'est affiché.
    - Le jeu « effectifs des écoles » renseigne souvent le **code postal** à la place du code commune pour la Guyane : la plateforme rattache chaque école par son UAI (annuaire), puis par les codes postaux officiels.
