# Rapports signés

| Document | Préfixe | Contenu |
| --- | --- | --- |
| Diagnostic de commune | `DIAG-` | indicateurs par thème avec Guyane et rang, hypothèse communale, croissance du bâti et qualité, quartiers en croissance, sources et limites |
| Dossier d'aide à l'implantation | `IMPL-` | scénario, effet sur la desserte (avant / après), sites, hypothèses, charte |
| Liste Recensement Éclaireur | `RIL-` | carreaux à signaler à l'INSEE, règle de secret, charte |

**Préparer** (Chargé d'études) affiche un projet modifiable (destinataires, appréciation, propositions) ; **Émettre et signer** (Responsable) fige le texte, le hache en SHA-256, le signe (ECDSA, PKI de l'instance), l'inscrit au registre et à l'audit, et le notifie sur **#decisions**.

**Vérification hors plateforme** : le lien *Télécharger le certificat racine de l'instance* fournit la racine de confiance (PEM) ; l'export d'un document contient son certificat, son empreinte et la marche à suivre (`openssl verify`, puis vérification ECDSA-SHA256 du texte). L'horodatage est celui de l'horloge du serveur (pas d'autorité RFC 3161).

Dans le registre : **Vérifier l'intégrité** (empreinte, signature, chaîne de certificats — toute modification du texte est détectée), **Exporter** (texte et bloc de scellement), **Imprimer / PDF**.
