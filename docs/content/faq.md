# FAQ

**La plateforme remplace-t-elle le recensement ?**
Non. Elle mesure la croissance du **bâti** et en déduit, à occupation constante, une population *possible*. C'est un indicateur indépendant pour demander des vérifications ciblées (RIL), présenté comme tel.

**Peut-on voir une maison ?**
Non. Tout est agrégé à 200 m ; aucune emprise n'est conservée ; les exports appliquent une règle de secret.

**Pourquoi ma commune a-t-elle une qualité « faible » ?**
Les bourgs petits ou très dispersés, sous couvert arboré, ou entourés de sols nus en saison sèche (rizières, savanes, plages) sont mal vus à 20 m. La série Sentinel-2 n'est alors pas appliquée : la référence WSF 2019 reste. Un contrôle visuel sur image très haute résolution (Pléiades, SEAS Guyane) est la bonne étape suivante.

**Pourquoi un saut entre 2015 et 2016 ?**
Changement de capteur (Landsat 30 m → référence 10 m) : l'habitat diffus apparaît en 2016. Ce n'est pas une croissance.

**Le taux de desserte en eau paraît très bas.**
Les points d'eau viennent d'OpenStreetMap, souvent incomplet en Guyane. Ajoutez les bornes-fontaines connues dans l'écran Équipements.

**Les distances tiennent-elles compte du fleuve ?**
Elles sont à vol d'oiseau ; le facteur de détour donne un ordre de grandeur. En zone de fleuve ou de criques, augmentez-le (Administration → Paramètres).

**Peut-on l'utiliser sans Internet ?**
Oui pour la démonstration : l'instantané embarqué contient statistiques, équipements et analyses de 9 communes. Le fond de carte satellite, lui, vient d'Internet (préférez OpenStreetMap en cache, ou ajoutez un fond local en source personnalisée).

**Combien de temps prend une analyse ?**
Quelques minutes par commune (lecture des archives satellitaires par plages HTTP).
