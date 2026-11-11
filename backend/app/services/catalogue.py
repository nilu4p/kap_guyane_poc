"""Catalogue of every data source: what it brings, its licence, how it is accessed.

Integrated sources are keyless open data. Keyed providers (``credentials``) are
fallbacks: listed as « clé requise » until their key is set in Administration ›
Paramètres, then « intégrée ». Restricted sources (very high resolution
imagery, cadastre-linked files…) are listed with the procedure to obtain them, so
the services know what could be plugged in next and under which conditions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings

SOURCES: List[Dict[str, Any]] = [
    # --- integrated -----------------------------------------------------------
    {"id": "geo.api.gouv.fr", "name": "API Découpage administratif (IGN / INSEE)", "category": "Territoire",
     "status": "intégrée", "access": "libre, sans clé", "licence": "Licence Ouverte 2.0",
     "usage": "Contours des 22 communes, population légale, surface, intercommunalité", "health": "geo.api.gouv.fr",
     "url": "https://geo.api.gouv.fr/decoupage-administratif"},
    {"id": "insee_melodi", "name": "INSEE — API Melodi", "category": "Statistiques",
     "status": "intégrée", "access": "libre, sans clé", "licence": "Licence Ouverte 2.0",
     "usage": "Populations légales 1968-2023, naissances et décès, âges, scolarisation, logement DOM (eau, électricité, "
              "assainissement), activité et chômage, base permanente des équipements (santé, commerces, services)",
     "health": "insee_melodi", "url": "https://portail-api.insee.fr/"},
    {"id": "education_nationale", "name": "Éducation nationale — data.education.gouv.fr", "category": "Statistiques",
     "status": "intégrée", "access": "libre, sans clé", "licence": "Licence Ouverte 2.0",
     "usage": "Annuaire géolocalisé des écoles, collèges, lycées ; effectifs et classes des écoles publiques depuis 2009",
     "health": "education_nationale", "url": "https://data.education.gouv.fr/"},
    {"id": "finess", "name": "FINESS — établissements sanitaires (ministère de la Santé)", "category": "Équipements",
     "status": "intégrée", "access": "libre, sans clé (miroir OpenDataSoft de l'extraction Etalab)", "licence": "Licence Ouverte 2.0",
     "usage": "Hôpitaux, centres et maisons de santé, pharmacies, PMI, laboratoires, dialyse — géolocalisés ; les doublons OSM à moins de 60 m sont écartés",
     "health": "finess", "url": "https://www.data.gouv.fr/fr/datasets/finess-extraction-du-fichier-des-etablissements/"},
    {"id": "ign_iris", "name": "IGN — Contours IRIS (Géoplateforme) · INSEE — population par IRIS", "category": "Statistiques",
     "status": "intégrée", "access": "libre, sans clé", "licence": "Licence Ouverte 2.0",
     "usage": "Calibrage de la population par quartier (densité et structure par âge) dans les communes découpées en IRIS",
     "health": "ign_iris", "url": "https://geoservices.ign.fr/contoursiris"},
    {"id": "cadastre_ign", "name": "IGN — API Carto, module cadastre", "category": "Contraintes",
     "status": "intégrée", "access": "libre, sans clé", "licence": "Licence Ouverte 2.0",
     "usage": "Vérification foncière agrégée des sites proposés (nombre et taille des parcelles du carreau, sans identifiant ni propriétaire)",
     "health": "cadastre_ign", "url": "https://apicarto.ign.fr/api/doc/cadastre"},
    {"id": "openstreetmap", "name": "OpenStreetMap (Overpass API)", "category": "Équipements",
     "status": "intégrée", "access": "libre, sans clé", "licence": "ODbL",
     "usage": "Santé, points d'eau, commerces alimentaires, transport, services, crèches ; réseau routier (desserte)",
     "health": "openstreetmap", "url": "https://www.openstreetmap.org/"},
    {"id": "dlr_wsf2019", "name": "DLR — World Settlement Footprint 2019 (10 m)", "category": "Satellite",
     "status": "intégrée", "access": "libre, lecture par plages HTTP", "licence": "CC BY 4.0",
     "usage": "Surface bâtie de référence 2019 (Sentinel-1 + Sentinel-2)", "health": "dlr_wsf2019",
     "url": "https://geoservice.dlr.de/web/maps/eoc:wsf2019"},
    {"id": "dlr_wsf_evolution", "name": "DLR — WSF Evolution 1985-2015 (30 m)", "category": "Satellite",
     "status": "intégrée", "access": "libre, lecture par plages HTTP", "licence": "CC BY 4.0",
     "usage": "Année d'urbanisation de chaque pixel (archive Landsat) : croissance historique des quartiers",
     "health": "dlr_wsf_evolution", "url": "https://geoservice.dlr.de/web/maps/eoc:wsfevolution"},
    {"id": "sentinel2", "name": "Copernicus Sentinel-2 L2A (Earth Search, AWS open data)", "category": "Satellite",
     "status": "intégrée", "access": "libre, sans clé", "licence": "Copernicus (libre)",
     "usage": "Composites de saison sèche annuels → indice de bâti calibré sur WSF 2019 ; imagerie couleur de l'atlas",
     "health": "sentinel2", "url": "https://registry.opendata.aws/sentinel-2-l2a-cogs/"},
    {"id": "microsoft_buildings", "name": "Microsoft Global ML Building Footprints", "category": "Satellite",
     "status": "intégrée", "access": "libre, sans clé", "licence": "ODbL",
     "usage": "Nombre de bâtiments par carreau (agrégé à la lecture, aucune emprise conservée)", "health": "microsoft_buildings",
     "url": "https://github.com/microsoft/GlobalMLBuildingFootprints"},
    {"id": "wdpa", "name": "WDPA — Aires protégées (UNEP-WCMC / UICN)", "category": "Contraintes",
     "status": "intégrée", "access": "libre, sans clé", "licence": "conditions WDPA (usage non commercial)",
     "usage": "Contrainte d'implantation : Parc amazonien, réserves naturelles…", "health": "wdpa",
     "url": "https://www.protectedplanet.net/"},
    # --- keyed fallbacks (Administration › Paramètres › Clés API des sources) -------
    {"id": "copernicus_cdse", "name": "Copernicus Data Space Ecosystem — Sentinel Hub (Sentinel-2 L2A)", "category": "Satellite",
     "status": "clé requise", "access": "compte CDSE gratuit, client OAuth (quota mensuel)", "licence": "Copernicus (libre)",
     "usage": "Secours de l'imagerie Sentinel-2 de l'atlas (catalogue et tuiles couleur) quand Earth Search est injoignable",
     "procedure": "Créer un client OAuth dans le tableau de bord Sentinel Hub du CDSE, puis le saisir dans Paramètres › Clés API des sources",
     "health": "copernicus_cdse", "keys": ["cdse_client_id", "cdse_client_secret"],
     "url": "https://dataspace.copernicus.eu/"},
    {"id": "protected_planet", "name": "Protected Planet API (WDPA, UNEP-WCMC)", "category": "Contraintes",
     "status": "clé requise", "access": "jeton gratuit sur demande", "licence": "conditions WDPA (usage non commercial)",
     "usage": "Secours des aires protégées quand le serveur cartographique UNEP-WCMC ne répond pas",
     "procedure": "Demander un jeton sur api.protectedplanet.net, puis le saisir dans Paramètres › Clés API des sources",
     "health": "protected_planet", "keys": ["protected_planet_token"],
     "url": "https://api.protectedplanet.net/documentation"},
    {"id": "eox_s2cloudless", "name": "EOX — Sentinel-2 cloudless (mosaïques annuelles)", "category": "Fonds de carte",
     "status": "intégrée", "access": "tuiles libres", "licence": "CC BY 4.0 (2016) / CC BY-NC-SA 4.0 (2018 et suivantes)",
     "usage": "Fond satellite sans nuages, une mosaïque par année (curseur temporel de l'atlas)", "health": None,
     "url": "https://s2maps.eu/"},
    # --- restricted / to plug ----------------------------------------------------
    {"id": "seas_dinamis", "name": "SEAS Guyane / DINAMIS — Pléiades, Pléiades Neo, SPOT 6-7", "category": "Satellite THR",
     "status": "accès restreint", "access": "ayants droit institutionnels (commune, CTG, université, IRD) via DINAMIS",
     "licence": "licence DINAMIS / Airbus : diffusion publique d'extraits soumise à conditions",
     "usage": "Vérité terrain à 30 cm - 1,5 m : contrôle visuel des carreaux (objectif ≥ 80 % de concordance sur 50 carreaux)",
     "procedure": "Demande d'accès DINAMIS par la collectivité ; branchement en WMS/WMTS via Sources personnalisées",
     "health": None, "url": "https://dinamis.data-terra.org/"},
    {"id": "geodes", "name": "CNES GEODES (Sentinel, Pléiades selon droits)", "category": "Satellite",
     "status": "à brancher", "access": "compte CNES", "licence": "selon produit",
     "usage": "Catalogue national des données spatiales ; alternative souveraine à Earth Search",
     "procedure": "Compte GEODES ; source personnalisée STAC", "health": None, "url": "https://geodes.cnes.fr/"},
    {"id": "open_buildings_temporal", "name": "Google Open Buildings 2.5D Temporal (2016-2023)", "category": "Satellite",
     "status": "à brancher", "access": "Google Earth Engine (compte)", "licence": "CC BY 4.0",
     "usage": "Série annuelle du « nombre fractionnaire de bâtiments » (couverture Guyane à vérifier)",
     "procedure": "Export Earth Engine en GeoTIFF puis source personnalisée ; à comparer à la série Sentinel-2", "health": None,
     "url": "https://sites.research.google/gr/open-buildings/temporal/"},
    {"id": "georisques", "name": "Géorisques — PPR, zonages de risques (BRGM / MTE)", "category": "Contraintes",
     "status": "à brancher", "access": "libre (API REST et WMS)", "licence": "Licence Ouverte 2.0",
     "usage": "Exclure ou signaler les sites en zone inondable (PPRI) et de mouvement de terrain",
     "procedure": "API georisques.gouv.fr (non joignable depuis l'environnement de développement) ; zonages en WMS via Sources personnalisées",
     "health": None, "url": "https://www.georisques.gouv.fr/doc-api"},
    {"id": "ign_bdtopo", "name": "IGN — BD TOPO, OCS GE, PCI (cadastre)", "category": "Territoire",
     "status": "à brancher", "access": "libre (Géoplateforme)", "licence": "Licence Ouverte 2.0",
     "usage": "Bâtiments, routes, équipements, occupation du sol ; parcelles pour la vérification foncière",
     "procedure": "Flux WMS/WFS de la Géoplateforme via Sources personnalisées", "health": None,
     "url": "https://geoservices.ign.fr/"},
    {"id": "majic", "name": "DGFiP — Fichiers fonciers MAJIC", "category": "Territoire",
     "status": "exclue", "access": "convention, données personnelles", "licence": "restreinte",
     "usage": "Volontairement exclue : risque d'usage fiscal ou individuel contraire à la charte", "health": None, "url": ""},
    {"id": "filosofi", "name": "INSEE — FiLoSoFi (revenus, pauvreté)", "category": "Statistiques",
     "status": "non diffusée", "access": "—", "licence": "—",
     "usage": "Non diffusé pour les communes de Guyane (absence de source fiscale exploitable) : aucun indicateur de revenu",
     "health": None, "url": ""},
    {"id": "hydroweb", "name": "Hydroweb / SWOT (CNES-Theia) — hauteurs des fleuves", "category": "Risques",
     "status": "à brancher", "access": "libre (compte Theia)", "licence": "libre",
     "usage": "Module « Fleuve Info » : sécheresse et isolement des communes du fleuve", "health": None,
     "url": "https://hydroweb.next.theia-land.fr/"},
]


def describe(settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    from app.sources import health

    cfg = settings or get_settings()
    states = health.snapshot()
    out = []
    for source in SOURCES:
        entry = dict(source)
        if entry.get("keys") and all(getattr(cfg, key, "") for key in entry["keys"]):
            entry["status"] = "intégrée"
            entry.pop("procedure", None)
        state = states.get(source.get("health") or "")
        entry["live"] = state
        out.append(entry)
    return out
