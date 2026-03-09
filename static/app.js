// ==================== State ====================
let currentTab = "jobs";

// ==================== Init ====================
document.addEventListener("DOMContentLoaded", () => {
    loadProfile();
    loadStats();
    loadJobs();
    setupUpload();
    setupPlatformToggles();

    // Auto-refresh stats every 5 seconds
    setInterval(loadStats, 5000);
    setInterval(() => {
        if (currentTab === "jobs") loadJobs();
        else if (currentTab === "applied") loadApplied();
        else if (currentTab === "logs") loadLogs();
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

// ==================== Upload ====================
function setupUpload() {
    const zone = document.getElementById("uploadZone");
    const input = document.getElementById("cvInput");

    input.addEventListener("change", (e) => {
        if (e.target.files.length > 0) uploadCV(e.target.files[0]);
    });

    zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.style.borderColor = "var(--accent)";
    });

    zone.addEventListener("dragleave", () => {
        zone.style.borderColor = "";
    });

    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.style.borderColor = "";
        if (e.dataTransfer.files.length > 0) uploadCV(e.dataTransfer.files[0]);
    });
}

async function uploadCV(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast("Seuls les fichiers PDF sont acceptes", "error");
        return;
    }

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
        } else {
            toast(data.error || "Erreur upload", "error");
        }
    } catch {
        toast("Erreur de connexion", "error");
    }
}

// ==================== Platform Toggles ====================
function setupPlatformToggles() {
    document.querySelectorAll(".platform-toggle").forEach((el) => {
        el.addEventListener("click", () => el.classList.toggle("active"));
    });
}

function getSelectedPlatforms() {
    return Array.from(document.querySelectorAll(".platform-toggle.active"))
        .map((el) => el.dataset.platform)
        .join(",");
}

// ==================== Profile ====================
async function loadProfile() {
    try {
        const res = await fetch("/api/profile");
        const data = await res.json();

        if (data.exists) {
            document.getElementById("keywords").value = data.keywords || "";
            document.getElementById("location").value = data.location || "France";
            document.getElementById("minScore").value = data.min_match_score || 0.5;
            document.getElementById("autoApply").checked = data.auto_apply || false;

            if (data.cv_filename) {
                document.getElementById("uploadZone").classList.add("has-file");
                document.getElementById("uploadIcon").innerHTML = "&#9989;";
                document.getElementById("uploadText").textContent = data.cv_filename;
            }

            // Set platform toggles
            if (data.platforms) {
                const active = data.platforms.split(",");
                document.querySelectorAll(".platform-toggle").forEach((el) => {
                    el.classList.toggle("active", active.includes(el.dataset.platform));
                });
            }
        }
    } catch {}
}

async function saveProfile() {
    const formData = new FormData();
    formData.append("keywords", document.getElementById("keywords").value);
    formData.append("location", document.getElementById("location").value);
    formData.append("min_match_score", document.getElementById("minScore").value);
    formData.append("auto_apply", document.getElementById("autoApply").checked);
    formData.append("platforms", getSelectedPlatforms());

    try {
        const res = await fetch("/api/profile/update", { method: "POST", body: formData });
        const data = await res.json();

        if (data.success) {
            toast("Profil sauvegarde!", "success");
        } else {
            toast(data.error || "Erreur", "error");
        }
    } catch {
        toast("Erreur de connexion", "error");
    }
}

// ==================== Stats ====================
async function loadStats() {
    try {
        const res = await fetch("/api/stats");
        const data = await res.json();

        document.getElementById("statTotal").textContent = data.total;
        document.getElementById("statApplied").textContent = data.applied;
        document.getElementById("statMatched").textContent = data.matched;
        document.getElementById("statErrors").textContent = data.errors;

        // Update button states
        const btnSearch = document.getElementById("btnSearch");
        if (data.scraping) {
            btnSearch.innerHTML = '<span class="spinner"></span> Recherche en cours...';
            btnSearch.disabled = true;
        } else {
            btnSearch.innerHTML = "Rechercher des offres";
            btnSearch.disabled = false;
        }

        const btnApply = document.getElementById("btnApplyAll");
        if (data.applying) {
            btnApply.innerHTML = '<span class="spinner"></span> Candidatures en cours...';
            btnApply.disabled = true;
        } else {
            btnApply.innerHTML = "Postuler a tout";
            btnApply.disabled = false;
        }
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
        } else {
            toast(data.error || "Erreur", "error");
        }
    } catch {
        toast("Erreur de connexion", "error");
    }
}

// ==================== Jobs ====================
async function loadJobs() {
    try {
        const res = await fetch("/api/jobs?status=matched");
        const jobs = await res.json();
        renderJobs(jobs, "jobsList", true);
    } catch {}
}

async function loadApplied() {
    try {
        const res = await fetch("/api/jobs?status=applied");
        const jobs = await res.json();
        renderJobs(jobs, "appliedList", false);
    } catch {}
}

function renderJobs(jobs, containerId, showApplyBtn) {
    const container = document.getElementById(containerId);

    if (!jobs.length) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">&#128270;</div>
                <p>Aucune offre pour le moment</p>
            </div>`;
        return;
    }

    container.innerHTML = jobs.map((job) => {
        const scoreClass = job.match_score >= 0.7 ? "score-high" : job.match_score >= 0.4 ? "score-mid" : "score-low";
        const scorePercent = Math.round((job.match_score || 0) * 100);

        return `
        <div class="job-card">
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
                ${showApplyBtn ? `<button class="btn btn-success btn-sm" onclick="applyOne(${job.id})">Postuler</button>` : ""}
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

        if (data.success) {
            toast("Candidature lancee!", "success");
        } else {
            toast(data.error || "Erreur", "error");
        }
    } catch {
        toast("Erreur de connexion", "error");
    }
}

async function applyAll() {
    try {
        const res = await fetch("/api/apply-all", { method: "POST" });
        const data = await res.json();

        if (data.success) {
            toast(data.message, "success");
        } else {
            toast(data.error || "Erreur", "error");
        }
    } catch {
        toast("Erreur de connexion", "error");
    }
}

async function deleteJob(jobId) {
    try {
        await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
        loadJobs();
    } catch {}
}

// ==================== Logs ====================
async function loadLogs() {
    try {
        const res = await fetch("/api/logs");
        const logs = await res.json();

        const container = document.getElementById("logsList");
        if (!logs.length) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="icon">&#128203;</div>
                    <p>Aucun log pour le moment</p>
                </div>`;
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
    document.querySelectorAll(".tab").forEach((el) => {
        el.classList.toggle("active", el.dataset.tab === tab);
    });
    document.getElementById("tabJobs").style.display = tab === "jobs" ? "" : "none";
    document.getElementById("tabApplied").style.display = tab === "applied" ? "" : "none";
    document.getElementById("tabLogs").style.display = tab === "logs" ? "" : "none";

    if (tab === "jobs") loadJobs();
    else if (tab === "applied") loadApplied();
    else if (tab === "logs") loadLogs();
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
