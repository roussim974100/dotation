// Alimente le portail d'administration avec ses indicateurs
// et affiche les messages flash issus des sous-pages admin.
const ADMIN_FLASH_NOTICE_KEY = "adminFlashNotice";

async function fetchAdminJson(url) {
  const response = await fetch(url, {
    credentials: "same-origin"
  });
  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return response.json();
}

function setMetric(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = String(value);
  }
}

function showAdminFlashNotice() {
  const notice = document.getElementById("adminFlashNotice");
  if (!notice) {
    return;
  }
  try {
    const message = sessionStorage.getItem(ADMIN_FLASH_NOTICE_KEY);
    if (!message) {
      return;
    }
    notice.textContent = message;
    notice.classList.remove("d-none");
    sessionStorage.removeItem(ADMIN_FLASH_NOTICE_KEY);
  } catch (error) {
    // Rien de bloquant.
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  showAdminFlashNotice();
  try {
    const [users, services, resources] = await Promise.all([
      fetchAdminJson("/api/admin/users"),
      fetchAdminJson("/api/admin/services"),
      fetchAdminJson("/api/admin/resources")
    ]);
    setMetric("adminUsersCount", users.length);
    setMetric("adminPendingCount", users.filter((user) => user.status === "pending").length);
    setMetric("adminServicesCount", services.filter((service) => service.is_active).length);
    setMetric("adminResourcesCount", resources.filter((resource) => resource.is_active).length);
  } catch (error) {
    console.error(error);
  }
});
