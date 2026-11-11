# Notifications

La plateforme publie sur un webhook compatible Slack / Mattermost / Teams, par canal :

| Canal | Contenu |
| --- | --- |
| `#veille` | après une analyse : hectares gagnés, quartiers en croissance, hectares loin d'une école (au plus une fois par jour et par commune) |
| `#analyses` | analyse satellitaire terminée (surface bâtie, concordance, années observées) ou en échec |
| `#donnees` | synchronisation des données ouvertes (jeux en échec) ; source indisponible / rétablie |
| `#decisions` | scénario validé ; document signé émis |
| `#securite` | compte verrouillé, administrateur créé, clés modifiées, mode secours, réinitialisation, restauration, journal d'audit altéré |

- `{channel}` ou `__CHANNEL__` dans l'URL est remplacé par le canal (une URL par canal) ; sinon une URL unique et un champ `channel` (`kap-<canal>`).
- HTTPS vers des hôtes publics uniquement (anti-SSRF), sauf les hôtes de `WEBHOOK_ALLOWED_HOSTS` (le serveur de démonstration `notif-sink`, consultable sur **/notifs/** par les responsables et les administrateurs : le canal #securite y affiche comptes et adresses).
- Mode workers : livraison par la file `notify` avec nouvelles tentatives (30 s → 16 min).
- Bouton **Envoyer un test sur chaque canal** dans Administration → Notifications.
