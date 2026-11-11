// Platform endpoints. The transport (session cookie, CSRF, error messages) and the endpoints
// shared by the platform family (auth, audit, accounts, administration, custom sources) live
// in client.js, re-exported here so that every view keeps importing from "services/api.js".
import { assetUrl, del, download, get, post, put } from "./client.js";

export * from "./client.js";

// --- Territory ----------------------------------------------------------------
export const fetchCommunes = (geometry = false) => get("/api/v1/communes", { params: { geometry } });
export const fetchTerritoryKpis = () => get("/api/v1/territoire/kpis");
export const fetchCommune = (code) => get(`/api/v1/communes/${code}`);
export const fetchContour = (code) => get(`/api/v1/communes/${code}/contour`);
export const saveHypothesis = (code, body) => put(`/api/v1/communes/${code}/hypothese`, body);
export const deleteHypothesis = (code) => del(`/api/v1/communes/${code}/hypothese`);
export const fetchDataStatus = () => get("/api/v1/donnees");
export const startSync = () => post("/api/v1/donnees/sync");

// --- Facilities ----------------------------------------------------------------
export const fetchCategories = () => get("/api/v1/equipements/categories");
export const fetchEquipments = (commune, category) =>
  get("/api/v1/equipements", { params: { commune, ...(category ? { category } : {}) } });
export const createEquipment = (body) => post("/api/v1/equipements", body);
export const updateEquipment = (id, body) => put(`/api/v1/equipements/${id}`, body);
export const deleteEquipment = (id) => del(`/api/v1/equipements/${id}`);

// --- Analyses & grid ----------------------------------------------------------------
export const startAnalysis = (commune, sentinel2 = true) => post("/api/v1/analyses", { kind: "commune", commune, sentinel2 });
export const fetchAnalyses = (commune) => get("/api/v1/analyses", { params: commune ? { commune } : {} });
export const fetchAnalysis = (id) => get(`/api/v1/analyses/${id}`);
export const fetchGridMeta = (code) => get(`/api/v1/grille/${code}/meta`);
export const fetchLayer = (code, params) => get(`/api/v1/grille/${code}/couche`, { params });
export const fetchCell = (code, cell) => get(`/api/v1/grille/${code}/carreau/${cell}`);
export const fetchWatch = (code, since = 2019) => get(`/api/v1/grille/${code}/veille`, { params: { since } });
export const fetchCensus = (code, since = 2019) => get(`/api/v1/grille/${code}/recensement`, { params: { since } });
export const downloadCensus = (code, since = 2019) =>
  download(`/api/v1/grille/${code}/recensement?since=${since}&format=csv`, `recensement-eclaireur-${code}-${since}.csv`);
export const fetchConstraints = (code) => get(`/api/v1/grille/${code}/contraintes`);

// --- Visual validation of the satellite layer ------------------------------------------
export const fetchValidation = (code, year) => get(`/api/v1/validation/${code}`, { params: year ? { year } : {} });
export const recordVerdict = (code, body) => post(`/api/v1/validation/${code}`, body);

// --- Decision -----------------------------------------------------------------------
export const recommendSites = (body) => post("/api/v1/decision/implantation", body, { timeout: 120000 });
export const evaluateSites = (body) => post("/api/v1/decision/evaluer", body, { timeout: 120000 });
export const fetchCoverage = (commune, hypothese = false) => get("/api/v1/decision/acces", { params: { commune, hypothese } });
export const fetchScenarios = (commune) => get("/api/v1/scenarios", { params: commune ? { commune } : {} });
export const createScenario = (body) => post("/api/v1/scenarios", body);
export const updateScenario = (id, body) => put(`/api/v1/scenarios/${id}`, body);
export const setScenarioStatus = (id, status) => post(`/api/v1/scenarios/${id}/statut`, { status });
export const deleteScenario = (id) => del(`/api/v1/scenarios/${id}`);

// --- Reports ---------------------------------------------------------------------------
export const fetchReports = (commune) => get("/api/v1/rapports", { params: commune ? { commune } : {} });
export const fetchReport = (id) => get(`/api/v1/rapports/${id}`);
export const draftReport = (body) => post("/api/v1/rapports/projet", body);
export const issueReport = (body) => post("/api/v1/rapports/emettre", body);
export const verifyReport = (id) => post(`/api/v1/rapports/${id}/verifier`);
export const downloadReport = (id, ref) => download(`/api/v1/rapports/${id}/export`, `${ref}.txt`);
export const downloadRootCertificate = () => download("/api/v1/rapports/certificat", "kap-guyane-racine.pem");

// --- Imagery ----------------------------------------------------------------------------
export const fetchImageryLayers = () => get("/api/v1/imagery/layers");
export const fetchSentinel2Scenes = (commune) => get("/api/v1/imagery/sentinel2/scenes", { params: { commune }, timeout: 60000 });
export const sentinel2TileUrl = (itemId) => assetUrl(`/api/v1/imagery/sentinel2/tiles/${itemId}/{z}/{x}/{y}.png`);

// --- Administration -----------------------------------------------------------------------
export const testService = (service) => post(`/api/v1/settings/keys/test/${service}`, {}, { timeout: 90000 });
export const fetchEthics = () => get("/api/v1/system/ethique");
