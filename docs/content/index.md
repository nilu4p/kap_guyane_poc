# KAP Guyane — aide à la décision territoriale

**KAP Guyane** est une plateforme GEOINT multi-sources qui aide les communes de Guyane à décider **où implanter** les équipements du quotidien — écoles, santé, points d'eau, commerces alimentaires, arrêts de transport, services publics — à partir de ce que l'on sait réellement du territoire : les **statistiques officielles** (INSEE, Éducation nationale), les **équipements recensés** (annuaire scolaire, OpenStreetMap, saisies des services) et la **croissance du bâti mesurée par satellite** (DLR World Settlement Footprint, Copernicus Sentinel-2), le tout fusionné sur une **grille de 200 m**.

!!! quote "La question du lundi matin"
    « Où ma population a-t-elle grandi depuis le dernier recensement, et ces quartiers sont-ils couverts par une école, l'eau, une route ? Où implanter l'école provisoire de 2027 ? Quels carreaux signaler à l'INSEE avant la collecte de janvier ? »

## Ce que fait la plateforme

| Brique | Ce qu'elle apporte | Où |
| --- | --- | --- |
| **Statistiques des 22 communes** | 46 indicateurs dérivés (démographie, éducation, santé, eau et logement, emploi, commerces, services), comparés à la Guyane et classés | [Territoire](ecrans/territoire.md), [Fiche commune](ecrans/commune.md) |
| **Bâti par satellite** | Surface bâtie de chaque carreau de 200 m de 1985 à aujourd'hui (WSF Evolution, WSF 2019, série Sentinel-2 calibrée) | [Atlas](ecrans/atlas.md), [méthode](methodes/bati-satellite.md) |
| **Population par carreau** | Population légale INSEE répartie sur le bâti, prolongée au rythme de la croissance mesurée (estimation nommée comme telle) | [méthode](methodes/population.md) |
| **Accessibilité** | Distance de chaque habitant à l'équipement le plus proche, part de la demande desservie | [méthode](methodes/accessibilite.md) |
| **Aide à l'implantation** | Propose les sites qui desservent le plus d'habitants (ou d'enfants) non desservis, sous contraintes, avec le « pourquoi ici » | [Décision](ecrans/decision.md), [méthode](methodes/implantation.md) |
| **Veille** | Quartiers en croissance loin des équipements ; liste « Recensement Éclaireur » pour l'INSEE | [Veille](ecrans/veille.md) |
| **Documents signés** | Diagnostic, dossier d'implantation, liste RIL : figés, hachés, signés, vérifiables | [Rapports](ecrans/rapports.md) |

## Les principes

- **Agrégation obligatoire à 200 m** : aucune construction individuelle n'est jamais désignée, stockée ni exportée. Les empreintes de bâtiments sont comptées à la lecture puis oubliées.
- **Planification, pas contrôle** : aucune distinction légal / illégal, aucun croisement avec le cadastre nominatif, tout usage fiscal ou d'expulsion exclu. Voir la [charte d'usage](ethique.md).
- **Chaque chiffre dit d'où il vient** : source, millésime, méthode, hypothèses et qualité sont affichés à côté de chaque valeur. Une estimation n'est jamais présentée comme un recensement.
- **Sources ouvertes et souveraines** : INSEE, Éducation nationale, IGN, Copernicus, DLR, OpenStreetMap — toutes sans clé. Les images très haute résolution (Pléiades via SEAS Guyane / DINAMIS) se branchent quand la collectivité en a les droits.
- **Reproductible sur les 22 communes**, utilisable sans compétence SIG, et démontrable **hors ligne** (instantané embarqué).

## Par où commencer

1. [Prise en main](prise-en-main/index.md) : connexion, navigation, rôles.
2. [Démonstration en 5 minutes](prise-en-main/demonstration.md) : le scénario du Salon des maires.
3. [Méthodes et calculs](methodes/index.md) : comment chaque chiffre est obtenu, et ses limites.
