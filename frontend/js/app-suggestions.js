// Suggestions autocomplete pour les champs dynamiques (marque, modèle, zones, UNC…).
// Dépend de requestJson et escapeAttribute définis dans app.js.
// Chargé après app.js — toutes les fonctions appelées sont disponibles au runtime.

const _fieldSuggestCache = new Map();

async function loadFieldSuggestions() {
  // Collecte tous les datalists fsugg-* présents dans le DOM (générés par buildDynamicFieldInput)
  const datalists = document.querySelectorAll("datalist[id^='fsugg-']");
  if (!datalists.length) return;
  const keys = [...new Set([...datalists].map(dl => dl.id.replace("fsugg-", "")))];
  await Promise.all(keys.map(async (key) => {
    if (_fieldSuggestCache.has(key)) {
      fillFieldDatalist(key, _fieldSuggestCache.get(key));
      return;
    }
    try {
      const values = await requestJson(`/api/forms/field-suggestions?field=${encodeURIComponent(key)}`);
      _fieldSuggestCache.set(key, values);
      fillFieldDatalist(key, values);
    } catch {
      // silencieux — l'autocomplete est optionnel
    }
  }));
}

function fillFieldDatalist(key, values) {
  document.querySelectorAll(`datalist#fsugg-${key}`).forEach((dl) => {
    if (dl.dataset.filled === "1") return;
    dl.innerHTML = values.map(v => `<option value="${escapeAttribute(v)}">`).join("");
    dl.dataset.filled = "1";
  });
}
