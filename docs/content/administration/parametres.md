# Paramètres opérationnels

<p class="where">Administration → <strong>Paramètres</strong> — administrateurs. Page générée depuis le code (<code>docs/tools/gen_parametres.py</code>).</p>

Ces réglages modifient le comportement de la plateforme **sans redémarrage**. Chaque modification est enregistrée, appliquée immédiatement et tracée dans l'audit (`system.settings`). Les **rayons de desserte** traduisent la norme locale de la commune : chaque résultat (atlas, aide à la décision, documents signés) affiche le rayon utilisé.

!!! tip "Méthode"
    Changez **un seul paramètre à la fois** et relancez l'analyse concernée ; les documents déjà émis gardent les valeurs de leur émission.

## Clés API des sources

En tête de l'onglet, la section **Clés API des sources** regroupe les fournisseurs qui demandent une clé. Toutes les sources intégrées fonctionnent **sans clé** : une clé active un **fournisseur de secours**, utilisé seulement quand la source ouverte ne répond pas.

| Fournisseur | Variables | Rôle | Obtenir la clé |
| --- | --- | --- | --- |
| Copernicus Data Space Ecosystem (Sentinel Hub) | `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` | Catalogue et tuiles couleur Sentinel-2 de l'atlas quand Earth Search (AWS) est injoignable (quota mensuel gratuit) | compte CDSE, puis *User settings → OAuth clients* dans le tableau de bord Sentinel Hub |
| Protected Planet (WDPA) | `PROTECTED_PLANET_TOKEN` | Aires protégées (contrainte d'implantation) quand le serveur UNEP-WCMC ne répond pas | demande de jeton sur api.protectedplanet.net |

- **Enregistrer** chiffre la valeur dans le coffre (`keys/api_credentials.enc`, clé maître hors sauvegardes) et l'applique sans redémarrage ; elle remplace la valeur du fichier `.env`.
- La valeur n'est **jamais renvoyée** au navigateur : seuls l'origine (coffre ou `.env`) et les 4 derniers caractères sont affichés.
- **Tester** vérifie la clé en direct (jeton et recherche de scènes pour Copernicus, lecture des aires protégées de Guyane pour Protected Planet).
- **Supprimer** retire la valeur du coffre et rétablit celle du `.env`, s'il y en a une.
- Chaque modification est tracée dans l'audit (`system.keys`) et notifiée sur le canal #securite.

Pour une autre API à clé (WMS sous licence, API métier…), déclarez une [source personnalisée](sources-personnalisees.md) : son secret est chiffré de la même façon.

## Vue d'ensemble

| Paramètre | Valeur par défaut | Plage | Unité |
| --- | --- | --- | --- |
| [Synchronisation automatique des données ouvertes (jours)](#data-refresh-days) | 7 | 0 – 90 | jours |
| [Facteur de détour (vol d'oiseau → trajet réel)](#detour-factor) | 1.3 | 1.0 – 2.5 | × |
| [Écoles : effectif cible par classe (calcul des places)](#school-class-size) | 25 | 10 – 35 | élèves par classe |
| [Secret : nombre minimal de bâtiments estimés par carreau exporté](#privacy-min-buildings) | 5 | 3 – 50 | bâtiments |
| [Sentinel-2 : couverture nuageuse maximale d'une scène (%)](#s2-max-cloud) | 40 | 5.0 – 80.0 | % |
| [Sentinel-2 : scènes par saison sèche et par tuile](#s2-scenes-per-year) | 4 | 1 – 10 | scènes |
| [Surface maximale analysée par commune (km²)](#max-analysis-area-km2) | 900 | 50.0 – 5000.0 | km² |
| [Densité par défaut (habitants par hectare bâti)](#fallback-persons-per-built-ha) | 60 | 5.0 – 300.0 | hab./ha bâti |
| [Rayon de desserte — école maternelle / élémentaire (m)](#radius-ecole) | 1500 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — collège (m)](#radius-college) | 5000 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — santé (m)](#radius-sante) | 5000 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — point d'eau potable (m)](#radius-eau) | 500 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — commerce alimentaire (m)](#radius-alimentation) | 1000 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — transport (m)](#radius-transport) | 500 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — services publics (m)](#radius-services) | 3000 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — petite enfance (m)](#radius-petite-enfance) | 2000 | 100 – 30000 | mètres à vol d'oiseau |
| [Rayon de desserte — lycée (m)](#radius-lycee) | 15000 | 100 – 60000 | mètres à vol d'oiseau |

## Synchronisation automatique des données ouvertes (jours) {#data-refresh-days}

Nom technique : `data_refresh_days` · type entier · plage 0 – 90 jours · défaut **7**

Fréquence de la mise à jour automatique des statistiques INSEE, de l'annuaire de l'Éducation nationale et des équipements OpenStreetMap. 0 = uniquement à la demande.

!!! success "Recommandation"
    7 jours : l'INSEE et l'Éducation nationale publient au plus quelques fois par an, OSM change chaque jour.

## Facteur de détour (vol d'oiseau → trajet réel) {#detour-factor}

Nom technique : `detour_factor` · type décimal · plage 1.0 – 2.5 × · défaut **1.3**

Multiplie les distances à vol d'oiseau pour estimer le trajet réel. La desserte compare ce trajet estimé au rayon de chaque famille : avec 1,3, un rayon de 1 500 m correspond à environ 1 150 m à vol d'oiseau. 1 = vol d'oiseau pur.

- **▲ Augmenter** : Desserte plus exigeante (zones de fleuve, de criques, réseau de pistes lâche).
- **▼ Diminuer** : Desserte plus généreuse (centre urbain au maillage serré).

!!! success "Recommandation"
    1,3 en ville ; 1,6 à 2 en zone de criques, de fleuve ou de pistes.

## Écoles : effectif cible par classe (calcul des places) {#school-class-size}

Nom technique : `school_class_size` · type entier · plage 10 – 35 élèves par classe · défaut **25**

Places d'une école = nombre de classes (Éducation nationale) × cet effectif. La demande rattachée à une école au-delà de ses places est comptée « sans place » (école saturée) et l'aide à l'implantation en tient compte. Une capacité saisie en « places » dans l'écran Équipements remplace ce calcul.

- **▲ Augmenter** : Écoles réputées plus capables : moins de saturation calculée.
- **▼ Diminuer** : Saturation plus vite atteinte (classes dédoublées en éducation prioritaire : 12 en CP / CE1).

!!! success "Recommandation"
    25 en moyenne ; plus bas en réseau d'éducation prioritaire renforcée (REP+).

## Secret : nombre minimal de bâtiments estimés par carreau exporté {#privacy-min-buildings}

Nom technique : `privacy_min_buildings` · type entier · plage 3 – 50 bâtiments · défaut **5**

Un carreau dont la croissance représente moins de bâtiments estimés n'est pas listé dans les exports (Recensement Éclaireur) : il est cumulé dans une ligne « autres carreaux ».

!!! success "Recommandation"
    5 au minimum (règle de la charte) ; augmenter dans les petites communes.

## Sentinel-2 : couverture nuageuse maximale d'une scène (%) {#s2-max-cloud}

Nom technique : `s2_max_cloud` · type décimal · plage 5.0 – 80.0 % · défaut **40**

Plafond de nuages des scènes Sentinel-2 retenues pour les composites de saison sèche (les nuages restants sont masqués pixel par pixel).

!!! success "Recommandation"
    40 % : en Guyane, abaisser trop le seuil laisse certaines années sans scène.

## Sentinel-2 : scènes par saison sèche et par tuile {#s2-scenes-per-year}

Nom technique : `s2_scenes_per_year` · type entier · plage 1 – 10 scènes · défaut **4**

Nombre de scènes les plus claires combinées (médiane) pour chaque année. Plus de scènes = moins de bruit, analyse plus longue.

!!! success "Recommandation"
    4 à 6.

## Surface maximale analysée par commune (km²) {#max-analysis-area-km2}

Nom technique : `max_analysis_area_km2` · type décimal · plage 50.0 – 5000.0 km² · défaut **900**

Plafond de la surface lue dans les archives satellitaires pour une commune (zones habitées d'abord). Les petits écarts au-delà gardent la seule référence WSF 2019.

!!! success "Recommandation"
    900 km² couvrent les zones habitées de toutes les communes en une analyse de quelques minutes.

## Densité par défaut (habitants par hectare bâti) {#fallback-persons-per-built-ha}

Nom technique : `fallback_persons_per_built_ha` · type décimal · plage 5.0 – 300.0 hab./ha bâti · défaut **60**

Utilisée seulement quand la densité ne peut pas être calibrée sur la population légale de la commune.

!!! success "Recommandation"
    Laisser la calibration faire ; ne sert qu'en secours.

## Rayon de desserte — école maternelle / élémentaire (m) {#radius-ecole}

Nom technique : `radius_ecole` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **1500**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « école maternelle / élémentaire ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — collège (m) {#radius-college}

Nom technique : `radius_college` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **5000**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « collège ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — santé (m) {#radius-sante}

Nom technique : `radius_sante` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **5000**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « santé ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — point d'eau potable (m) {#radius-eau}

Nom technique : `radius_eau` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **500**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « point d'eau potable ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — commerce alimentaire (m) {#radius-alimentation}

Nom technique : `radius_alimentation` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **1000**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « commerce alimentaire ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — transport (m) {#radius-transport}

Nom technique : `radius_transport` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **500**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « transport ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — services publics (m) {#radius-services}

Nom technique : `radius_services` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **3000**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « services publics ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — petite enfance (m) {#radius-petite-enfance}

Nom technique : `radius_petite_enfance` · type entier · plage 100 – 30000 mètres à vol d'oiseau · défaut **2000**

Distance maximale à vol d'oiseau pour considérer un habitant desservi par un équipement « petite enfance ».

!!! success "Recommandation"
    Norme locale de la commune ; chaque résultat affiche le rayon utilisé.

## Rayon de desserte — lycée (m) {#radius-lycee}

Nom technique : `radius_lycee` · type entier · plage 100 – 60000 mètres à vol d'oiseau · défaut **15000**

Distance maximale pour un lycée.

!!! success "Recommandation"
    Les lycées sont rares hors du littoral : rayon large.
