// Setup wizard — configuration initiale de l'application.
// Chargé uniquement sur setup.html.
(function () {
  "use strict";

  const TOTAL_STEPS = 5;
  const BENEFICIARY_PRESETS = {
    public_collectivite:  "agent:Agent,elu:Élu(e)",
    public_administration: "fonctionnaire:Fonctionnaire,contractuel:Contractuel(le),prestataire:Prestataire",
    private_company:       "salarie:Salarié(e),prestataire:Prestataire",
    association:           "salarie:Salarié(e),benevole:Bénévole",
  };

  let currentStep = 1;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function $(id) { return document.getElementById(id); }

  function showAlert(msg, tone) {
    const el = $("setupAlert");
    el.textContent = msg;
    el.className = `alert alert-${tone || "danger"} mb-3`;
  }

  function hideAlert() {
    $("setupAlert").className = "alert d-none mb-3";
  }

  function parseBeneficiaryTypes(raw) {
    const result = [];
    (raw || "").split(",").forEach((part) => {
      const p = part.trim();
      const colon = p.indexOf(":");
      if (colon > 0) {
        result.push({ value: p.slice(0, colon).trim(), label: p.slice(colon + 1).trim() });
      }
    });
    return result;
  }

  function getCsrfToken() {
    return fetch("/api/csrf-token", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((d) => d.token || "")
      .catch(() => "");
  }

  // ── Stepper UI ────────────────────────────────────────────────────────────

  function updateStepper(step) {
    document.querySelectorAll("[data-step-indicator]").forEach((el) => {
      const n = parseInt(el.dataset.stepIndicator, 10);
      el.classList.remove("is-active", "is-done");
      if (n < step) el.classList.add("is-done");
      else if (n === step) el.classList.add("is-active");
    });
  }

  function showStep(n) {
    for (let i = 1; i <= TOTAL_STEPS; i++) {
      $(`setupStep${i}`)?.classList.toggle("d-none", i !== n);
    }
    updateStepper(n);

    const prevBtn = $("setupPrevBtn");
    const nextBtn = $("setupNextBtn");
    const submitBtn = $("setupSubmitBtn");

    prevBtn.style.visibility = n === 1 ? "hidden" : "visible";
    nextBtn.classList.toggle("d-none", n === TOTAL_STEPS);
    submitBtn.classList.toggle("d-none", n !== TOTAL_STEPS);

    if (n === 4) renderBeneficiaryPreview();
    if (n === 5) renderRecap();

    currentStep = n;
    hideAlert();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ── Preset chips ──────────────────────────────────────────────────────────

  function renderPresetChips(orgContext) {
    const container = $("beneficiaryPresets");
    if (!container) return;
    container.innerHTML = "";
    Object.entries(BENEFICIARY_PRESETS).forEach(([ctx, value]) => {
      const labels = parseBeneficiaryTypes(value).map((t) => t.label).join(" + ");
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "preset-chip" + (ctx === orgContext ? " border-brand" : "");
      chip.style.borderColor = ctx === orgContext ? "var(--brand)" : "";
      chip.style.background = ctx === orgContext ? "var(--brand-soft)" : "";
      chip.textContent = labels;
      chip.addEventListener("click", () => {
        $("setupBeneficiaryTypes").value = value;
        renderPresetChips(ctx);
        $("setupOrgContext").value = ctx;
      });
      container.appendChild(chip);
    });
  }

  // ── Preview & recap ───────────────────────────────────────────────────────

  function renderBeneficiaryPreview() {
    const raw = $("setupBeneficiaryTypes").value.trim()
      || BENEFICIARY_PRESETS[$("setupOrgContext").value]
      || BENEFICIARY_PRESETS.public_collectivite;
    const types = parseBeneficiaryTypes(raw);
    const container = $("setupBeneficiaryPreview");
    if (!container) return;
    if (!types.length) {
      container.innerHTML = '<p class="text-muted">Aucun type configuré.</p>';
      return;
    }
    container.innerHTML = '<div class="d-flex flex-wrap gap-2">' +
      types.map((t) =>
        `<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25 px-3 py-2" style="font-size:.9rem">${escHtml(t.label)}</span>`
      ).join("") +
      "</div>";
  }

  function renderRecap() {
    const orgContextLabels = {
      public_collectivite:  "Collectivité territoriale",
      public_administration: "Administration publique",
      private_company:       "Entreprise privée",
      association:           "Association",
    };
    const rows = [
      ["Type d'organisation", orgContextLabels[$("setupOrgContext").value] || "-"],
      ["Nom de l'organisation", $("setupOrgName").value.trim() || "(non renseigné)"],
      ["Email DPO", $("setupDpoEmail").value.trim() || "(non renseigné)"],
      ["Contact support", $("setupSupportName").value.trim() || "(non renseigné)"],
      ["Rôle support", $("setupSupportRole").value.trim() || "(non renseigné)"],
      ["Email support", $("setupSupportEmail").value.trim() || "(non renseigné)"],
      ["Types de bénéficiaires", $("setupBeneficiaryTypes").value.trim() || BENEFICIARY_PRESETS[$("setupOrgContext").value]],
    ];
    $("setupRecap").innerHTML = rows.map(([label, value]) => `
      <div class="setup-recap__row">
        <span class="setup-recap__label">${escHtml(label)}</span>
        <span class="setup-recap__value">${escHtml(value)}</span>
      </div>
    `).join("");
  }

  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── Validation par étape ──────────────────────────────────────────────────

  function validateStep(n) {
    if (n === 2 && !$("setupOrgName").value.trim()) {
      showAlert("Le nom de l'organisation est obligatoire.");
      $("setupOrgName").focus();
      return false;
    }
    return true;
  }

  // ── Soumission ────────────────────────────────────────────────────────────

  async function submitSetup() {
    const btn = $("setupSubmitBtn");
    btn.disabled = true;
    btn.textContent = "Enregistrement…";
    hideAlert();

    try {
      const csrf = await getCsrfToken();
      const body = {
        org_context:       $("setupOrgContext").value,
        beneficiary_types: $("setupBeneficiaryTypes").value.trim()
          || BENEFICIARY_PRESETS[$("setupOrgContext").value],
        org_name:          $("setupOrgName").value.trim(),
        dpo_email:         $("setupDpoEmail").value.trim(),
        support_name:      $("setupSupportName").value.trim(),
        support_role:      $("setupSupportRole").value.trim(),
        support_email:     $("setupSupportEmail").value.trim(),
      };

      const res = await fetch("/api/setup/complete", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Erreur ${res.status}`);
      }

      try {
        sessionStorage.setItem("adminFlashNotice", "Configuration initiale enregistrée avec succès.");
      } catch (_) {}
      window.location.href = "admin.html";
    } catch (err) {
      showAlert(`Impossible d'enregistrer la configuration : ${err.message}`);
      btn.disabled = false;
      btn.textContent = "Terminer la configuration";
    }
  }

  // ── Initialisation ────────────────────────────────────────────────────────

  function bindEvents() {
    $("setupOrgContext").addEventListener("change", () => {
      const newCtx = $("setupOrgContext").value;
      $("setupBeneficiaryTypes").value = BENEFICIARY_PRESETS[newCtx] || "";
      renderPresetChips(newCtx);
    });
    $("setupNextBtn").addEventListener("click", () => {
      if (!validateStep(currentStep)) return;
      if (currentStep < TOTAL_STEPS) showStep(currentStep + 1);
    });
    $("setupPrevBtn").addEventListener("click", () => {
      if (currentStep > 1) showStep(currentStep - 1);
    });
    $("setupSubmitBtn").addEventListener("click", submitSetup);
  }

  async function prefillFromApi() {
    try {
      const res = await fetch("/api/setup/status", { credentials: "same-origin" });
      if (!res.ok) return;
      const data = await res.json();
      if (data.setupCompleted) { window.location.href = "admin.html"; return; }
      if (data.orgContext) $("setupOrgContext").value = data.orgContext;
      if (data.beneficiaryTypes) $("setupBeneficiaryTypes").value = data.beneficiaryTypes;
      if (data.orgName) $("setupOrgName").value = data.orgName;
      if (data.dpoEmail) $("setupDpoEmail").value = data.dpoEmail;
      if (data.supportName) $("setupSupportName").value = data.supportName;
      if (data.supportRole) $("setupSupportRole").value = data.supportRole;
      if (data.supportEmail) $("setupSupportEmail").value = data.supportEmail;
      renderPresetChips($("setupOrgContext").value || "public_collectivite");
    } catch (_) {}
  }

  function init() {
    const ctx = $("setupOrgContext").value || "public_collectivite";
    if (!$("setupBeneficiaryTypes").value) {
      $("setupBeneficiaryTypes").value = BENEFICIARY_PRESETS[ctx] || BENEFICIARY_PRESETS.public_collectivite;
    }
    renderPresetChips(ctx);
    bindEvents();
    showStep(1);
    prefillFromApi(); // async, n'empêche pas la navigation
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
