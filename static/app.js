// ==================== State ====================
let currentTab = "jobs";
let keywordTags = [];
let allProspects = [];
let currentProspectFilter = "all";

// ==================== Init ====================
document.addEventListener("DOMContentLoaded", () => {
    loadProfile();
    loadStats();
    loadJobs();
    setupUpload();
    setupPlatformToggles();
    setInterval(loadStats, 5000);
    setInterval(() => {
        if (currentTab === "jobs") loadJobs();
        else if (currentTab === "applied") loadApplied();
        else if (currentTab === "logs") loadLogs();
        else if (currentTab === "prospect") loadProspects();
    }, 8000);
});

// ==================== Toast ====================
function toast(message, type = "info") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

// ==================== Utils ====================
function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// ==================== Upload ====================
function setupUpload() {
    const zone = document.getElementById("uploadZone");
    const input = document.getElementById("cvInput");
    input.addEventListener("change", (e) => { if (e.target.files.length > 0) uploadCV(e.target.files[0]); });
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.style.borderColor = "var(--accent)"; });
    zone.addEventListener("dragleave", () => { zone.style.borderColor = ""; });
    zone.addEventListener("drop", (e) => {
        e.preventDefault(); zone.style.borderColor = "";
        if (e.dataTransfer.files.length > 0) uploadCV(e.dataTransfer.files[0]);
    });
}

async function uploadCV(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) { toast("Seuls les fichiers PDF sont acceptes", "error"); return; }
    const formData = new FormData();
    formData.append("file", file);
    try {
        const res = await fetch("/api/upload-cv", { method: "POST", body: formData });
        const data = await res.json();
        if (data.success) {
            document.getElementById("uploadZone").classList.add("has-file");
            document.getElementById("uploadIcon").innerHTML = "&#9989;";
            document.getElementById("uploadText").textContent = file.name;
            toast("CV uploade avec succes!", "success");
        } else { toast(data.error || "Erreur upload", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
}

async function uploadYaml(input, yamlType) {
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("yaml_type", yamlType);
    try {
        const res = await fetch("/api/upload-yaml", { method: "POST", body: formData });
        const data = await res.json();
        if (data.success) {
            document.getElementById(yamlType === "resume" ? "resumeYamlStatus" : "configYamlStatus").textContent = "✅ " + file.name;
            toast(`${yamlType === "resume" ? "Profil" : "Config"} YAML chargé !`, "success");
        } else { toast(data.error || "Erreur YAML", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
}

// ==================== Platform Toggles ====================
function setupPlatformToggles() {
    document.querySelectorAll(".platform-toggle").forEach((el) => {
        el.addEventListener("click", () => el.classList.toggle("active"));
    });
}

function getSelectedPlatforms() {
    return Array.from(document.querySelectorAll(".platform-toggle.active"))
        .map((el) => el.dataset.platform).join(",");
}

// ==================== Keyword Tags ====================
function renderKeywordTags() {
    const container = document.getElementById("keywordTagsContainer");
    if (!container) return;
    container.innerHTML = keywordTags.map((kw, i) =>
        `<span style="background:#2563eb;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;display:inline-flex;align-items:center;gap:4px;white-space:nowrap">
            ${escapeHtml(kw)}
            <span onclick="removeKeyword(${i})" style="cursor:pointer;opacity:0.8;font-size:14px;line-height:1">&times;</span>
        </span>`
    ).join("");
    document.getElementById("keywords").value = keywordTags.join(",");
}

function addKeyword() {
    const input = document.getElementById("keywordInput");
    if (!input) return;
    const val = input.value.trim().replace(/,$/, "");
    if (!val) return;
    val.split(",").forEach(k => {
        const kw = k.trim();
        if (kw && !keywordTags.includes(kw)) keywordTags.push(kw);
    });
    input.value = "";
    renderKeywordTags();
}

function removeKeyword(index) {
    keywordTags.splice(index, 1);
    renderKeywordTags();
}

function handleKeywordKey(event) {
    if (event.key === "Enter" || event.key === ",") {
        event.preventDefault();
        addKeyword();
    }
}

// ==================== Profile ====================
async function loadProfile() {
    try {
        const res = await fetch("/api/profile");
        const data = await res.json();
        if (data.exists) {
            const kws = data.keywords || "";
            keywordTags = kws.split(",").map(k => k.trim()).filter(k => k);
            renderKeywordTags();
            document.getElementById("keywords").value = kws;
            document.getElementById("location").value = data.location || "France";
            document.getElementById("minScore").value = data.min_match_score || 0.5;
            document.getElementById("autoApply").checked = data.auto_apply || false;
            document.getElementById("firstName").value = data.first_name || "";
            document.getElementById("lastName").value = data.last_name || "";
            document.getElementById("emailAddr").value = data.email || "";
            document.getElementById("phone").value = data.phone || "";
            document.getElementById("city").value = data.city || "";
            document.getElementById("linkedinEmail").value = data.linkedin_email || "";
            document.getElementById("smtpUser").value = data.smtp_user || "";
            if (data.cv_filename) {
                document.getElementById("uploadZone").classList.add("has-file");
                document.getElementById("uploadIcon").innerHTML = "&#9989;";
                document.getElementById("uploadText").textContent = data.cv_filename;
            }
            if (data.platforms) {
                const active = data.platforms.split(",");
                document.querySelectorAll(".platform-toggle").forEach((el) => {
                    el.classList.toggle("active", active.includes(el.dataset.platform));
                });
            }
        }
    } catch {}
    try {
        const r = await fetch("/api/linkedin/status");
        const d = await r.json();
        const el = document.getElementById("linkedinStatus");
        if (el) el.textContent = d.logged_in ? "✅ Connecté à LinkedIn" : "❌ Non connecté";
    } catch {}
}

async function saveProfile() {
    // Flush any un-added text in keywordInput
    const inputEl = document.getElementById("keywordInput");
    if (inputEl && inputEl.value.trim()) addKeyword();

    const formData = new FormData();
    formData.append("keywords", document.getElementById("keywords").value);
    formData.append("location", document.getElementById("location").value);
    formData.append("min_match_score", document.getElementById("minScore").value);
    formData.append("auto_apply", document.getElementById("autoApply").checked);
    formData.append("platforms", getSelectedPlatforms());
    formData.append("first_name", document.getElementById("firstName").value);
    formData.append("last_name", document.getElementById("lastName").value);
    formData.append("email", document.getElementById("emailAddr").value);
    formData.append("phone", document.getElementById("phone").value);
    formData.append("city", document.getElementById("city").value);
    formData.append("linkedin_email", document.getElementById("linkedinEmail").value);
    const pw = document.getElementById("linkedinPassword").value;
    if (pw) formData.append("linkedin_password", pw);
    formData.append("smtp_user", document.getElementById("smtpUser").value);
    const smtpPw = document.getElementById("smtpPassword").value;
    if (smtpPw) formData.append("smtp_password", smtpPw);

    try {
        const res = await fetch("/api/profile/update", { method: "POST", body: formData });
        const data = await res.json();
        if (data.success) toast("Profil sauvegarde!", "success");
        else toast(data.error || "Erreur", "error");
    } catch { toast("Erreur de connexion", "error"); }
}

async function linkedinLogin() {
    toast("Ouverture du navigateur LinkedIn...", "info");
    try {
        const res = await fetch("/api/linkedin/login", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            toast(data.message, "success");
            document.getElementById("linkedinStatus").textContent = "✅ Connecté à LinkedIn";
        } else { toast(data.message || data.error || "Erreur connexion LinkedIn", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
}

async function resetErrors() {
    try {
        const res = await fetch("/api/reset-errors", { method: "POST" });
        const data = await res.json();
        toast(`${data.reset} offres remises en attente`, "success");
        loadJobs(); loadStats();
    } catch { toast("Erreur", "error"); }
}

async function resetState() {
    try {
        await fetch("/api/reset-state", { method: "POST" });
        toast("Etat reinitialise", "success");
        loadStats();
    } catch { toast("Erreur", "error"); }
}

// ==================== Stats ====================
async function loadStats() {
    try {
        const [statsRes, prospectRes] = await Promise.all([
            fetch("/api/stats"),
            fetch("/api/prospect/stats"),
        ]);
        const data = await statsRes.json();
        const pData = await prospectRes.json();

        document.getElementById("statTotal").textContent = data.total;
        document.getElementById("statApplied").textContent = data.applied;
        document.getElementById("statMatched").textContent = data.matched;
        document.getElementById("statErrors").textContent = data.errors;
        document.getElementById("statProspects").textContent = pData.total || 0;

        const btnSearch = document.getElementById("btnSearch");
        if (data.scraping) {
            btnSearch.innerHTML = '<span class="spinner"></span> Recherche en cours...';
            btnSearch.disabled = true;
        } else { btnSearch.innerHTML = "Rechercher des offres"; btnSearch.disabled = false; }

        const btnApply = document.getElementById("btnApplyAll");
        if (data.applying) {
            btnApply.innerHTML = '<span class="spinner"></span> Candidatures en cours...';
            btnApply.disabled = true;
        } else { btnApply.innerHTML = "Postuler a tout"; btnApply.disabled = false; }

        // Update prospect stats
        document.getElementById("pStatTotal").textContent = pData.total || 0;
        document.getElementById("pStatSent").textContent = pData.sent || 0;
        document.getElementById("pStatReplied").textContent = pData.replied || 0;
        document.getElementById("pStatInterview").textContent = pData.interview || 0;
    } catch {}
}

// ==================== Search ====================
async function startSearch() {
    try {
        const res = await fetch("/api/search", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            toast("Recherche lancee!", "success");
            document.getElementById("btnSearch").innerHTML = '<span class="spinner"></span> Recherche en cours...';
            document.getElementById("btnSearch").disabled = true;
        } else { toast(data.error || "Erreur", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
}

// ==================== Jobs ====================
async function loadJobs() {
    try {
        const [matched, errors] = await Promise.all([
            fetch("/api/jobs?status=matched").then(r => r.json()),
            fetch("/api/jobs?status=error").then(r => r.json()),
        ]);
        renderJobs([...matched, ...errors], "jobsList", true);
    } catch {}
}

async function loadApplied() {
    try {
        const res = await fetch("/api/jobs?status=applied");
        renderJobs(await res.json(), "appliedList", false);
    } catch {}
}

function renderJobs(jobs, containerId, showApplyBtn) {
    const container = document.getElementById(containerId);
    if (!jobs.length) {
        container.innerHTML = `<div class="empty-state"><div class="icon">&#128270;</div><p>Aucune offre pour le moment</p></div>`;
        return;
    }
    container.innerHTML = jobs.map((job) => {
        const scoreClass = job.match_score >= 0.7 ? "score-high" : job.match_score >= 0.4 ? "score-mid" : "score-low";
        const scorePercent = Math.round((job.match_score || 0) * 100);
        const isError = job.status === "error";
        return `
        <div class="job-card${isError ? ' job-card-error' : ''}">
            <div class="job-info">
                <h4><a href="${job.url}" target="_blank">${escapeHtml(job.title)}</a></h4>
                <div class="job-meta">
                    <span class="platform-badge platform-${job.platform}">${job.platform}</span>
                    <span>${escapeHtml(job.company)}</span>
                    <span>${escapeHtml(job.location)}</span>
                    ${job.salary ? `<span>${escapeHtml(job.salary)}</span>` : ""}
                </div>
            </div>
            <div class="job-actions">
                <span class="score-badge ${scoreClass}">${scorePercent}%</span>
                <span class="status-badge status-${job.status}">${job.status}</span>
                ${showApplyBtn && !isError ? `<button class="btn btn-success btn-sm" onclick="applyOne(${job.id})">Postuler</button>` : ""}
                ${isError && job.url ? `<a href="${job.url}" target="_blank" class="btn btn-sm" style="background:#2a4a2a;color:#aaa;border:1px solid #555;padding:4px 8px;border-radius:4px;font-size:11px;text-decoration:none">Manuel</a>` : ""}
                ${isError ? `<button class="btn btn-sm" style="background:#333;color:#888;border:1px solid #444;padding:4px 8px;border-radius:4px;font-size:11px;cursor:pointer" onclick="retryOne(${job.id})">Retry</button>` : ""}
                <button class="btn btn-danger btn-sm" onclick="deleteJob(${job.id})">X</button>
            </div>
        </div>`;
    }).join("");
}

// ==================== Apply ====================
async function applyOne(jobId) {
    try {
        const res = await fetch(`/api/apply/${jobId}`, { method: "POST" });
        const data = await res.json();
        if (data.success) toast("Candidature lancee!", "success");
        else toast(data.error || "Erreur", "error");
    } catch { toast("Erreur de connexion", "error"); }
}

async function applyAll() {
    try {
        const res = await fetch("/api/apply-all", { method: "POST" });
        const data = await res.json();
        if (data.success) toast(data.message, "success");
        else toast(data.error || "Erreur", "error");
    } catch { toast("Erreur de connexion", "error"); }
}

async function deleteJob(jobId) {
    try { await fetch(`/api/jobs/${jobId}`, { method: "DELETE" }); loadJobs(); } catch {}
}

async function retryOne(jobId) {
    try { await fetch(`/api/retry/${jobId}`, { method: "POST" }); loadJobs(); loadStats(); } catch {}
}

// ==================== PROSPECTION ====================
async function loadProspects() {
    try {
        const url = currentProspectFilter === "all" ? "/api/prospect/contacts" : `/api/prospect/contacts?status=${currentProspectFilter}`;
        const res = await fetch(url);
        allProspects = await res.json();
        renderProspects(allProspects);
    } catch {}
}

function filterProspects(filter) {
    currentProspectFilter = filter;
    document.querySelectorAll(".prospect-filter").forEach(b => b.classList.toggle("active", b.dataset.filter === filter));
    loadProspects();
}

function renderProspects(contacts) {
    const container = document.getElementById("prospectList");
    if (!contacts.length) {
        container.innerHTML = `<div class="empty-state"><div class="icon">&#128100;</div><p>Aucun contact prospect. Entrez des entreprises et cliquez "Trouver contacts".</p></div>`;
        return;
    }

    const statusLabels = { new: "Nouveau", sent: "Envoyé", replied: "Réponse", no_response: "Sans réponse", rejected: "Refusé", interview: "Entretien", error: "Erreur" };
    const statusColors = { new: "#555", sent: "#2563eb", replied: "#16a34a", no_response: "#d97706", rejected: "#dc2626", interview: "#a855f7", error: "#dc2626" };

    container.innerHTML = contacts.map(c => `
        <div class="prospect-card">
            <div class="prospect-info">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                    <strong style="font-size:14px">${escapeHtml(c.name || "Contact inconnu")}</strong>
                    ${c.role ? `<span style="font-size:11px;opacity:0.7">${escapeHtml(c.role)}</span>` : ""}
                    <span style="font-size:11px;background:#1a2a3a;padding:2px 6px;border-radius:10px;color:#60a5fa">${escapeHtml(c.company)}</span>
                </div>
                <div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap;align-items:center">
                    ${c.email ? `<span style="font-size:11px;opacity:0.7">📧 ${escapeHtml(c.email)}</span>` : ""}
                    ${c.linkedin_url ? `<a href="${escapeHtml(c.linkedin_url)}" target="_blank" style="font-size:11px;color:#0077b5;text-decoration:none">🔗 LinkedIn</a>` : ""}
                    ${c.sent_at ? `<span style="font-size:10px;opacity:0.5">Envoyé ${formatDate(c.sent_at)}</span>` : ""}
                    ${c.replied_at ? `<span style="font-size:10px;color:#4ade80">Réponse ${formatDate(c.replied_at)}</span>` : ""}
                </div>
                ${c.notes ? `<div style="font-size:11px;opacity:0.5;margin-top:3px">${escapeHtml(c.notes)}</div>` : ""}
            </div>
            <div class="prospect-actions">
                <span style="font-size:11px;background:${statusColors[c.status]||'#555'};color:#fff;padding:2px 8px;border-radius:10px">${statusLabels[c.status]||c.status}</span>
                <button class="btn btn-success btn-sm" onclick="openSendModal(${c.id}, '${escapeHtml(c.name)}', '${escapeHtml(c.company)}')" title="Envoyer candidature">Envoyer</button>
                <div class="prospect-status-btns">
                    <select onchange="updateProspectStatus(${c.id}, this.value)" style="background:#222;color:#aaa;border:1px solid #333;border-radius:4px;padding:2px 4px;font-size:11px;cursor:pointer">
                        <option value="">Statut</option>
                        <option value="new">Nouveau</option>
                        <option value="sent">Envoyé</option>
                        <option value="replied">Réponse reçue</option>
                        <option value="interview">Entretien</option>
                        <option value="no_response">Sans réponse</option>
                        <option value="rejected">Refusé</option>
                    </select>
                </div>
                <button class="btn btn-danger btn-sm" onclick="deleteProspect(${c.id})">X</button>
            </div>
        </div>
    `).join("");
}

async function findContacts() {
    const companies = document.getElementById("prospectCompanies").value.trim();
    if (!companies) { toast("Entrez au moins une entreprise", "error"); return; }
    const btn = document.getElementById("btnFindContacts");
    btn.innerHTML = '<span class="spinner"></span> Recherche...';
    btn.disabled = true;
    try {
        const fd = new FormData();
        fd.append("companies", companies);
        const res = await fetch("/api/prospect/find", { method: "POST", body: fd });
        const data = await res.json();
        if (data.success) {
            toast(data.message, "success");
            setTimeout(() => loadProspects(), 3000);
        } else { toast(data.error || "Erreur", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
    finally { btn.innerHTML = "Trouver contacts LinkedIn"; btn.disabled = false; }
}

function showAddContactModal() {
    document.getElementById("addContactModal").style.display = "flex";
}

function closeAddContactModal() {
    document.getElementById("addContactModal").style.display = "none";
    ["addCompany","addDomain","addName","addRole","addEmail","addLinkedin","addNotes"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = "";
    });
}

async function submitAddContact() {
    const company = document.getElementById("addCompany").value.trim();
    if (!company) { toast("L'entreprise est obligatoire", "error"); return; }
    const fd = new FormData();
    fd.append("company", company);
    fd.append("company_domain", document.getElementById("addDomain").value);
    fd.append("name", document.getElementById("addName").value);
    fd.append("role", document.getElementById("addRole").value);
    fd.append("email", document.getElementById("addEmail").value);
    fd.append("linkedin_url", document.getElementById("addLinkedin").value);
    fd.append("notes", document.getElementById("addNotes").value);
    try {
        const res = await fetch("/api/prospect/add", { method: "POST", body: fd });
        const data = await res.json();
        if (data.success) { toast("Contact ajouté!", "success"); closeAddContactModal(); loadProspects(); loadStats(); }
        else { toast(data.error || "Erreur", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
}

function openSendModal(contactId, name, company) {
    document.getElementById("sendContactId").value = contactId;
    document.getElementById("sendModalContact").textContent = `${name} — ${company}`;
    document.getElementById("sendSubject").value = "";
    document.getElementById("sendBody").value = "";
    document.getElementById("sendProspectModal").style.display = "flex";
}

function closeSendModal() {
    document.getElementById("sendProspectModal").style.display = "none";
}

function selectChannel(channel) {
    document.getElementById("sendChannel").value = channel;
    document.querySelectorAll(".channel-btn").forEach(b => b.classList.toggle("active", b.dataset.channel === channel));
}

async function generateMessage() {
    const contactId = document.getElementById("sendContactId").value;
    if (!contactId) return;
    const btn = event.currentTarget;
    btn.innerHTML = '<span class="spinner"></span> Génération...';
    btn.disabled = true;
    try {
        const res = await fetch(`/api/prospect/generate/${contactId}`, { method: "POST" });
        const data = await res.json();
        if (data.success) {
            const channel = document.getElementById("sendChannel").value;
            document.getElementById("sendSubject").value = data.subject || "";
            document.getElementById("sendBody").value = channel === "linkedin" ? data.linkedin_dm || data.body : data.body || "";
            toast("Message généré!", "success");
        } else { toast(data.error || "Erreur génération", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
    finally { btn.innerHTML = "✨ Générer avec IA"; btn.disabled = false; }
}

async function submitSendProspect() {
    const contactId = document.getElementById("sendContactId").value;
    const channel = document.getElementById("sendChannel").value;
    const subject = document.getElementById("sendSubject").value;
    const body = document.getElementById("sendBody").value;
    if (!body.trim()) { toast("Rédigez un message", "error"); return; }
    const fd = new FormData();
    fd.append("channel", channel);
    fd.append("subject", subject);
    fd.append("body", body);
    try {
        const res = await fetch(`/api/prospect/send/${contactId}`, { method: "POST", body: fd });
        const data = await res.json();
        if (data.success) {
            toast("Envoi en cours!", "success");
            closeSendModal();
            setTimeout(() => { loadProspects(); loadStats(); }, 2000);
        } else { toast(data.error || "Erreur", "error"); }
    } catch { toast("Erreur de connexion", "error"); }
}

async function updateProspectStatus(contactId, status) {
    if (!status) return;
    const fd = new FormData();
    fd.append("status", status);
    try {
        await fetch(`/api/prospect/status/${contactId}`, { method: "POST", body: fd });
        loadProspects(); loadStats();
    } catch {}
}

async function deleteProspect(contactId) {
    try {
        await fetch(`/api/prospect/contacts/${contactId}`, { method: "DELETE" });
        loadProspects(); loadStats();
    } catch {}
}

// ==================== Logs ====================
async function loadLogs() {
    try {
        const res = await fetch("/api/logs");
        const logs = await res.json();
        const container = document.getElementById("logsList");
        if (!logs.length) {
            container.innerHTML = `<div class="empty-state"><div class="icon">&#128203;</div><p>Aucun log pour le moment</p></div>`;
            return;
        }
        container.innerHTML = logs.map((log) => `
            <div class="log-entry">
                <div>
                    <span class="platform-badge platform-${log.platform}">${log.platform}</span>
                    <span class="status-badge status-${log.status}">${log.status}</span>
                    <span class="log-msg">${escapeHtml(log.message || "")}</span>
                </div>
                <span class="log-time">${formatDate(log.created_at)}</span>
            </div>
        `).join("");
    } catch {}
}

// ==================== Tabs ====================
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === tab));
    ["jobs","prospect","applied","logs"].forEach(t => {
        const el = document.getElementById(`tab${t.charAt(0).toUpperCase() + t.slice(1)}`);
        if (el) el.style.display = t === tab ? "" : "none";
    });
    if (tab === "jobs") loadJobs();
    else if (tab === "applied") loadApplied();
    else if (tab === "logs") loadLogs();
    else if (tab === "prospect") loadProspects();
}
