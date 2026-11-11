# Validation visuelle

Contrôle de la couche de bâti par une personne, carreau par carreau, pour mesurer sa fiabilité. C'est le critère de réussite du dossier : **au moins 80 % d'accord sur 50 carreaux**.

1. Choisir l'**année contrôlée** (2016 et après).
2. Indiquer l'**image utilisée** pour juger. L'idéal est une image Pléiades / Pléiades Neo de SEAS Guyane, branchée en source personnalisée ; la mosaïque Sentinel‑2 sans nuages d'EOX (≈ 10 m), affichée par défaut, suffit pour les cas francs.
3. Pour chaque carreau (carré blanc), répondre **Bâti**, **Non bâti** ou **Incertain**. Un carreau est « bâti » si au moins un cinquième de sa surface est couvert de constructions, de toitures ou de sols aménagés.

- **Échantillon** : 50 carreaux tirés au sort de façon reproductible (même commune et même année = mêmes carreaux pour tous). Une moitié est jugée bâtie par la plateforme, l'autre moitié non bâtie, prise à moins de 600 m du bâti, là où les confusions se produisent.
- **Contrôle à l'aveugle** : la réponse de la plateforme n'est envoyée au navigateur qu'après le vote.
- **Résultat** : taux d'accord (sans les « incertain »), faux bâtis, bâti manqué ; l'objectif est atteint à 80 % sur au moins 40 carreaux jugés.
- Chaque vote est inscrit au journal d'audit (`validation.record`). Le vote est réservé aux chargés d'études.
