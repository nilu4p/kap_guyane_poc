// Identity of this platform for the shared console core (shell, login, audit, accounts…).
// Every other file under components/, lib/, services/client.js and the shared views is
// byte-identical across the platforms of the family: only this
// file, the platform views and api.js differ. See frontend/SHARED.md.

export const PLATFORM = {
  id: "kap", // namespace of browser events and local storage keys
  name: "KAP Guyane",
  tagline: "GEOINT · aide à la décision territoriale",
  loginTitle: "Aide à la décision territoriale",
  loginNotice:
    "Accès réservé aux services habilités. Données agrégées à 200 m — outil de planification, pas de contrôle. Toutes les actions sont journalisées.",
  loadingLabel: "Connexion à la plateforme…",
  // Display time zone of every date ("UTC" = ISO "AAAA-MM-JJ HH:MM Z").
  timeZone: "America/Cayenne",
  apiTimeoutMs: 60000,
  // Geographic scope, as written in sentences ("emprise de …").
  territoryLabel: "la Guyane",
  // Prefixes of the actions recorded by the backend (audit.record calls).
  auditFamilies: [
    { id: "auth.", label: "Connexions" },
    { id: "user.", label: "Comptes" },
    { id: "analysis.", label: "Analyses" },
    { id: "data.", label: "Données ouvertes" },
    { id: "equipment.", label: "Équipements" },
    { id: "territory.", label: "Hypothèses" },
    { id: "decision.", label: "Implantation" },
    { id: "scenario.", label: "Scénarios" },
    { id: "report.", label: "Documents signés" },
    { id: "export.", label: "Exports" },
    { id: "validation.", label: "Validation" },
    { id: "custom_source.", label: "Sources perso." },
    { id: "system.", label: "Système" },
  ],
  // Mirrors the backend RBAC (app/api/deps.py): minimum role per capability.
  capabilities: [
    { group: "Territoire", label: "Consulter les fiches communes, l'atlas, la veille, les scénarios et le registre", min: "viewer" },
    { group: "Territoire", label: "Obtenir une proposition d'implantation et évaluer des sites", min: "viewer" },
    { group: "Territoire", label: "Saisir l'hypothèse de population de la commune", min: "supervisor" },
    { group: "Analyses", label: "Lancer une analyse satellitaire, synchroniser les données ouvertes", min: "analyst" },
    { group: "Analyses", label: "Ajouter / corriger des équipements (existants, provisoires, en projet)", min: "analyst" },
    { group: "Analyses", label: "Exporter la liste Recensement Éclaireur (CSV, tracé)", min: "analyst" },
    { group: "Décision", label: "Enregistrer, modifier, supprimer un scénario (non validé)", min: "analyst" },
    { group: "Décision", label: "Préparer un document de décision (aperçu)", min: "analyst" },
    { group: "Décision", label: "Valider / archiver un scénario ; émettre et signer un document", min: "supervisor" },
    { group: "Contrôle", label: "Consulter et vérifier le journal d'audit ; voir le serveur de notifications", min: "supervisor" },
    { group: "Administration", label: "Comptes et rôles, paramètres, clés API des sources, sources personnalisées, webhook, supervision", min: "admin" },
  ],
};
