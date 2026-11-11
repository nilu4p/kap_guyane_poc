# Population par carreau

La population de chaque carreau est **estimée** par un modèle dasymétrique simple, affiché comme tel partout.

## Modèle

1. **Année de calibration** *B* : dernier millésime de population municipale légale INSEE de la commune (par exemple 2023, en vigueur au 1er janvier 2026), population `P_B`.
2. **Densité d'occupation** `d = P_B / (hectares bâtis de la commune en B)` — habitants par hectare bâti, calibrée sur la commune elle-même (pas une norme nationale).
3. **Habitants d'un carreau l'année y** = `d × hectares bâtis du carreau en y`.

Pour les années **postérieures** à *B*, c'est une **extrapolation à occupation constante** : le total communal dit combien d'habitants la croissance mesurée du bâti *pourrait* loger. C'est un indicateur indépendant et reproductible, utile pour demander des vérifications ciblées — **pas un contre-recensement**.

## Calibrage par quartier (IRIS)

Dans les communes que l'INSEE découpe en **IRIS** (Cayenne, Saint-Laurent, Kourou, Matoury…), la densité n'est pas une moyenne communale : chaque IRIS reçoit **sa population** (recensement, Melodi `DS_RP_POPULATION_PRINC_IRIS`) répartie sur **ses hectares bâtis** (contours IGN), avec **sa structure par âge** pour les enfants. À Saint-Laurent, la densité va ainsi d'environ 63 habitants par hectare bâti (centre-ville) à 116 (quartiers récents).

- Les deux découpages peuvent différer d'âge (l'IGN publie le découpage actuel, le recensement celui de son millésime) : seuls les IRIS présents dans les deux sont calés un à un ; le reste de la commune forme une **zone résiduelle** calée sur la population restante — le total communal est toujours conservé.
- Garde-fous : un IRIS de moins de 2 ha bâtis ou de densité invraisemblable (moins du cinquième ou plus de cinq fois la densité communale) rejoint la zone résiduelle ; si les chiffres sont incohérents avec la population communale, le modèle revient au calibrage communal.

## Hypothèse communale

Une commune peut saisir sa propre estimation (année, valeur, fourchette, source) — rôle *Responsable*. Elle est affichée **à côté** de la population légale, jamais à sa place. Dans l'atlas et l'aide à la décision, l'option « hypothèse communale » calibre la densité sur ce chiffre ; tous les résultats et documents mentionnent alors l'hypothèse utilisée.

## Enfants

Les parts d'âge du dernier recensement de la commune (INSEE, *Scolarisation*) sont appliquées à chaque carreau :

- 3-10 ans (maternelle + élémentaire) ≈ ¾ de la tranche 2-5 ans + la tranche 6-10 ans ;
- 11-14 ans (collège) ; 15-17 ans (lycée).

Hypothèse : la structure par âge est la même dans tous les quartiers de la commune (les quartiers récents sont souvent plus jeunes : l'estimation des enfants y est prudente).

## Limites

- Hors IRIS (communes de moins de 10 000 habitants), l'occupation par hectare bâti est une moyenne communale.
- Les écarts entre population légale et réalité (effet de centralité, populations non recensées) se retrouvent dans la calibration ; c'est précisément ce que l'indicateur de croissance du bâti aide à objectiver.
