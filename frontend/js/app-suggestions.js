// Suggestions autocomplete pour les champs dynamiques (marque, modèle, etc.).
// Utilise /api/catalog/suggestions/<resource_id> — valeurs triées par fréquence,
// avec cascade liée (changer marque filtre les modèles disponibles).
// Dépend de escapeAttribute défini dans app.js.

const _fieldSuggestCache = new Map();

async function _fetchCatalogSuggestions(resourceId) {
  if (_fieldSuggestCache.has(resourceId)) return _fieldSuggestCache.get(resourceId);
  try {
    const r = await fetch(`/api/catalog/suggestions/${encodeURIComponent(resourceId)}`, { credentials: "same-origin" });
    if (!r.ok) return null;
    const data = await r.json();
    _fieldSuggestCache.set(resourceId, data);
    return data;
  } catch {
    return null;
  }
}

function fillFieldDatalist(datalistId, values) {
  const dl = document.getElementById(datalistId);
  if (!dl) return;
  dl.innerHTML = (values || [])
    .map((v) => `<option value="${escapeAttribute(String(v))}"></option>`)
    .join("");
}

function _bindLinkedListeners(resourceId, suggestions) {
  document.querySelectorAll(`[data-suggest-field][data-resource-id="${CSS.escape(resourceId)}"]`).forEach((input) => {
    if (input.dataset.boundSuggest) return;
    input.addEventListener("input", () => {
      const val = input.value.trim();
      const linkedForVal = suggestions.linked?.[input.dataset.suggestField]?.[val];
      Object.keys(suggestions.values || {}).forEach((otherKey) => {
        if (otherKey === input.dataset.suggestField) return;
        fillFieldDatalist(
          `fsugg-${resourceId}-${otherKey}`,
          linkedForVal?.[otherKey] || suggestions.values[otherKey]
        );
      });
    });
    input.dataset.boundSuggest = "true";
  });
}

async function loadFieldSuggestions() {
  // Collecte les resource_id depuis les datalists fsugg-<resourceId>-<fieldKey>
  const datalists = document.querySelectorAll("datalist[id^='fsugg-']");
  if (!datalists.length) return;

  // Extrait les resource_id uniques (tout ce qui précède le dernier segment)
  const resourceIds = new Set();
  datalists.forEach((dl) => {
    const parts = dl.id.replace("fsugg-", "").split("-");
    if (parts.length >= 2) resourceIds.add(parts.slice(0, -1).join("-"));
  });

  await Promise.all([...resourceIds].map(async (resourceId) => {
    const suggestions = await _fetchCatalogSuggestions(resourceId);
    if (!suggestions?.values) return;
    Object.entries(suggestions.values).forEach(([fieldKey, values]) => {
      fillFieldDatalist(`fsugg-${resourceId}-${fieldKey}`, values);
    });
    _bindLinkedListeners(resourceId, suggestions);
  }));
}
