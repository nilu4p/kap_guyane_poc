# Équipements

Inventaire des équipements de la commune, par famille, sur carte et en tableau.

| Origine | Contenu | Modifiable |
| --- | --- | --- |
| `education_nationale` | écoles, collèges, lycées ouverts (annuaire) ; élèves inscrits et classes à la dernière rentrée (écoles publiques) | position, capacité, statut, note (corrections locales) |
| `finess` | établissements de santé officiels | idem |
| `openstreetmap` | santé (en complément), eau, commerces alimentaires, transport, services, crèches | idem |
| `saisie` | équipements ajoutés par les services : existants absents des données ouvertes, **provisoires** ou **en projet** | tout ; suppression possible |

- **Ajouter** : choisir la famille, le statut, puis **cliquer sur la carte** pour placer l'équipement.
- Les équipements provisoires et en projet sont pris en compte dans l'accessibilité et l'aide à l'implantation (un projet déjà décidé n'est pas proposé une seconde fois).
- Les équipements issus des données ouvertes ne se suppriment pas (ils reviendraient à la synchronisation) ; leur identité reste celle de la source. Leurs **corrections locales** (position, capacité, statut, note) sont conservées à part et réappliquées à chaque synchronisation ; le tableau indique « corrigé ».
- **Position approximative** : établissements que la source ne situe qu'au centre du bourg ou du lieu-dit. Cliquez dessus, puis sur la carte pour les replacer.
- Saisir une capacité **en « places »** pour une école remplace le calcul classes × effectif cible.
