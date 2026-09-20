// Gestion de la base de données : export, diagnostic, import.

async function getCsrfToken() {
  try {
    const r = await fetch("/api/csrf-token", { credentials: "same-origin" });
    const d = await r.json();
    return d.token || "";
  } catch {
    return "";
  }
}

function showDbResult(containerId, level, title, body) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const icons = { ok: "✅", warning: "⚠️", error: "❌", info: "ℹ️" };
  const classes = { ok: "alert-success", warning: "alert-warning", error: "alert-danger", info: "alert-info" };
  el.className = `alert ${classes[level] || "alert-info"} mt-3`;
  el.innerHTML = `<strong>${icons[level] || ""} ${escapeHtml(title)}</strong>${body ? `<div class="mt-2">${body}</div>` : ""}`;
  el.classList.remove("d-none");
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function renderDiagnoseReport(report) {
  const levelLabels = { ok: "Fichier valide", warning: "Compatible avec avertissements", error: "Fichier invalide" };
  let html = "";
  if (report.stats && Object.keys(report.stats).length) {
    const parts = [];
    if (report.stats.dossiers !== undefined) parts.push(`${report.stats.dossiers} dossier(s)`);
    if (report.stats.org_name) parts.push(`Organisation : ${escapeHtml(report.stats.org_name)}`);
    if (parts.length) html += `<div class="mb-2">${parts.join(" · ")}</div>`;
  }
  if (report.warnings?.length) {
    html += `<ul class="mb-1 ps-3">${report.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`;
  }
  if (report.issues?.length) {
    html += `<ul class="mb-1 ps-3">${report.issues.map(i => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`;
  }
  showDbResult("dbDiagnoseResult", report.level, levelLabels[report.level] || report.level, html);
}

document.addEventListener("DOMContentLoaded", () => {
  // Diagnostic
  document.getElementById("dbDiagnoseBtn")?.addEventListener("click", async () => {
    const file = document.getElementById("dbDiagnoseFile")?.files?.[0];
    if (!file) {
      showDbResult("dbDiagnoseResult", "error", "Sélectionnez un fichier .db à analyser.", "");
      return;
    }
    const btn = document.getElementById("dbDiagnoseBtn");
    btn.disabled = true;
    btn.textContent = "Analyse…";
    try {
      const csrf = await getCsrfToken();
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/admin/db/diagnose", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf },
        body: fd,
      });
      const data = await r.json();
      if (!r.ok) {
        const msgs = { no_file: "Aucun fichier reçu.", file_too_large: "Fichier trop volumineux (max 200 Mo)." };
        showDbResult("dbDiagnoseResult", "error", msgs[data.error] || data.error, "");
        return;
      }
      renderDiagnoseReport(data);
    } catch {
      showDbResult("dbDiagnoseResult", "error", "Erreur de connexion au serveur.", "");
    } finally {
      btn.disabled = false;
      btn.textContent = "Analyser";
    }
  });

  // Import
  document.getElementById("dbImportBtn")?.addEventListener("click", async () => {
    const file = document.getElementById("dbImportFile")?.files?.[0];
    if (!file) {
      showDbResult("dbImportResult", "error", "Sélectionnez un fichier .db à importer.", "");
      return;
    }
    const confirmed = window.confirm(
      "Importer ce fichier remplacera TOUTES les données actuelles.\n\nUn backup automatique sera créé.\n\nConfirmer ?"
    );
    if (!confirmed) return;

    const btn = document.getElementById("dbImportBtn");
    btn.disabled = true;
    btn.textContent = "Import en cours…";
    try {
      const csrf = await getCsrfToken();
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/admin/db/import", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf },
        body: fd,
      });
      const data = await r.json();
      if (!r.ok) {
        if (data.error === "diagnose_failed") {
          renderDiagnoseReport({ ...data.report, _importContext: true });
          const el = document.getElementById("dbImportResult");
          if (el) {
            el.className = "alert alert-danger mt-3";
            el.innerHTML = `<strong>❌ Import annulé — fichier invalide</strong><div class="mt-2">${(data.report?.issues || []).map(i => `<li>${escapeHtml(i)}</li>`).join("")}</div>`;
            el.classList.remove("d-none");
          }
        } else {
          const msgs = { no_file: "Aucun fichier reçu.", file_too_large: "Fichier trop volumineux (max 200 Mo).", import_failed: "Échec du remplacement." };
          showDbResult("dbImportResult", "error", msgs[data.error] || data.error, data.detail ? escapeHtml(data.detail) : "");
        }
        return;
      }
      let body = `Backup créé : <code>${escapeHtml(data.backup)}</code>`;
      if (data.stats?.dossiers !== undefined) body += `<br>${data.stats.dossiers} dossier(s) importé(s).`;
      showDbResult("dbImportResult", "ok", "Import réussi — rechargez la page.", body);
      document.getElementById("dbImportFile").value = "";
    } catch {
      showDbResult("dbImportResult", "error", "Erreur de connexion au serveur.", "");
    } finally {
      btn.disabled = false;
      btn.textContent = "Importer et remplacer";
    }
  });
});


// Santé des champs : valeurs de dossiers dont le nom de champ n'existe plus dans le catalogue.
document.addEventListener("DOMContentLoaded", () => {
  const scanBtn = document.getElementById("fieldHealthScanBtn");
  const repairBtn = document.getElementById("fieldHealthRepairBtn");
  if (!scanBtn || !repairBtn) return;

  async function scan() {
    scanBtn.disabled = true;
    try {
      const response = await fetch("/api/admin/field-health", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Analyse impossible.");
      const report = await response.json();
      const rows = (report.orphans || []).map((o) => `<tr><td>${escapeHtml(o.resource)}</td><td><code>${escapeHtml(o.field)}</code></td><td>${o.target ? `<code>${escapeHtml(o.target)}</code>` : "<span class=\"text-muted\">aucun champ identifié</span>"}</td><td class="text-end">${Number(o.dossiers) || 0}</td></tr>`).join("");
      if (!rows) {
        showDbResult("fieldHealthResult", "ok", "Aucune valeur orpheline : tous les dossiers correspondent aux champs actuels.", "");
      } else {
        showDbResult("fieldHealthResult", report.repairable ? "warning" : "info",
          `${report.orphans.length} nom(s) de champ à examiner (${report.repairable} rattachable(s), ${report.unmatched} sans correspondance sûre).`,
          `<div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>Ressource</th><th>Ancien nom</th><th>Champ actuel</th><th class="text-end">Dossiers</th></tr></thead><tbody>${rows}</tbody></table></div><p class="small text-muted mt-2 mb-0">Les valeurs sans correspondance sûre ne sont pas modifiées : elles restent visibles dans « Autres informations enregistrées » du formulaire.</p>`);
      }
      repairBtn.classList.toggle("d-none", !report.repairable);
    } catch (error) {
      showDbResult("fieldHealthResult", "error", error.message || "Analyse impossible.", "");
    } finally {
      scanBtn.disabled = false;
    }
  }

  document.getElementById("dbHealthBtn")?.addEventListener("click", async () => {
    try {
      const response = await fetch("/api/admin/health", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Contrôle impossible.");
      const report = await response.json();
      if (report.status === "ok") {
        showDbResult("fieldHealthResult", "ok", "Base en bon état.", `Intégrité : ${escapeHtml(report.integrity)} · migrations appliquées jusqu'à la version ${escapeHtml(String(report.schemaVersion ?? "—"))}.`);
      } else {
        showDbResult("fieldHealthResult", "warning", "Points à examiner", `<ul class="mb-0">${(report.problems || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>`);
      }
    } catch (error) {
      showDbResult("fieldHealthResult", "error", error.message || "Contrôle impossible.", "");
    }
  });

  scanBtn.addEventListener("click", scan);
  repairBtn.addEventListener("click", async () => {
    repairBtn.disabled = true;
    try {
      const csrf = await getCsrfToken();
      const response = await fetch("/api/admin/field-health/repair", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf } });
      if (!response.ok) throw new Error("Rattachement impossible.");
      const report = await response.json();
      await scan();
      showDbResult("fieldHealthResult", "ok", `${report.repairedFields} valeur(s) rattachée(s) dans ${report.repairedForms} dossier(s) ; copie à plat recalculée pour ${report.resyncedForms || 0} dossier(s). Copie de sécurité faite avant.`, "");
    } catch (error) {
      showDbResult("fieldHealthResult", "error", error.message || "Rattachement impossible.", "");
    } finally {
      repairBtn.disabled = false;
    }
  });
});
