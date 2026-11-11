# Sources personnalisées

Administration → **Sources personnalisées** : branchez sans programmation n'importe quelle source publique ou institutionnelle :

- **API JSON / GeoJSON / CSV** (points, lignes ou polygones) : URL à variables (`{bbox}`, `{west}`…`{north}` = emprise de la Guyane, `{date}`, `{start}`, `{end}`, `{secret}`…), paramètres, en-têtes, corps POST, authentification (en-tête, paramètre, Bearer, Basic), pagination, lecture des champs détectée automatiquement ;
- **tuiles XYZ / WMTS** et **OGC WMS** : par exemple les flux de la Géoplateforme IGN, ou les images Pléiades de SEAS Guyane une fois les droits DINAMIS obtenus.

Chaque source se **teste en direct** étape par étape (requête, réponse, champs, aperçu) avant d'être enregistrée.

## Sécurité

- Les définitions et leur secret sont **chiffrés** (`keys/custom_sources.enc`, clé maître) ; le secret n'est jamais renvoyé au navigateur ni envoyé à un autre hôte.
- Toutes les requêtes passent par le serveur : http(s) uniquement, pas d'identifiants dans l'URL, **adresses publiques seulement** (hôtes internes à déclarer dans `CUSTOM_SOURCE_ALLOWED_HOSTS`), chaque redirection revérifiée, taille et durée bornées.
