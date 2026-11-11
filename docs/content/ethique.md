# Charte d'usage

> « Pas une seule maison n'est désignée : c'est un outil de planification, pas de contrôle. »

## Principes appliqués par la plateforme

1. **Un outil de planification, pas de contrôle.** La plateforme éclaire l'implantation des équipements et des réseaux. Tout usage fiscal, de contrôle de l'urbanisme individuel ou d'expulsion est exclu.
2. **Agrégation obligatoire à 200 m.** Toutes les couches sont calculées, stockées et exportées par carreaux de 200 m. Aucune emprise de bâtiment n'est conservée : les empreintes sont comptées à la lecture puis oubliées.
3. **Aucune distinction légal / illégal.** Le bâti est mesuré sans qualification juridique. Le cadastre nominatif (MAJIC) n'est pas utilisé.
4. **Secret statistique, à l'écran comme dans les exports.** Un carreau de moins de 5 bâtiments n'est jamais listé individuellement ; à l'écran, son nombre de bâtiments s'affiche « < 5 », ses habitants ne sont pas affichés et sa part bâtie est arrondie — en zone peu dense, un carreau de 200 m peut ne contenir qu'une habitation.
5. **Estimations nommées comme telles.** Chaque chiffre modélisé affiche sa méthode, ses hypothèses, ses sources et sa qualité. Un indicateur de croissance du bâti n'est pas un contre-recensement.
6. **Traçabilité.** Chaque analyse, export et document émis est inscrit au journal d'audit chaîné ; les documents de décision sont signés et vérifiables.

## Contexte

- Le Défenseur des droits (décisions 2023-31 et 2025-102) a critiqué la mise en œuvre de l'article 197 de la loi ELAN (arrêtés de démolition de l'habitat informel en Guyane et à Mayotte). La plateforme ne doit jamais contribuer à de telles procédures.
- La DGFiP détecte par IA les constructions non déclarées (« Foncier innovant ») : KAP Guyane s'en distingue délibérément (agrégé, non fiscal, non individuel).
- Avant tout usage opérationnel croisant ces données avec des données personnelles, une **analyse d'impact (AIPD)** au sens du RGPD est requise.

## Ce qui est garanti techniquement

| Engagement | Mise en œuvre |
| --- | --- |
| 200 m minimum | grille unique ; API, base, exports et documents sans géométrie plus fine |
| Pas d'empreintes | agrégation à la lecture (`msbuildings`) ; seules les sommes par carreau sont écrites |
| Secret | seuil `privacy_min_buildings` (≥ 3, 5 par défaut) dans les exports **et dans toutes les couches servies par l'API** (`app/analyse/privacy.py`) |
| Cadastre | résumé agrégé des parcelles d'un carreau proposé, jamais d'identifiant ni de propriétaire |
| Exports tracés | `export.census`, `report.issue`, `report.export` au journal d'audit |
| Droits | export réservé aux chargés d'études ; signature réservée aux responsables |
