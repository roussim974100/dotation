function initBackToTop() {
  if (!document.body.classList.contains("app-shell")) {
    return;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "back-to-top";
  button.id = "backToTopBtn";
  button.textContent = "Haut";
  button.setAttribute("aria-label", "Revenir en haut de la page");
  document.body.appendChild(button);

  const toggleVisibility = () => {
    button.classList.toggle("is-visible", window.scrollY > 320);
  };

  button.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  const updateButtonPosition = () => {
    const baseOffset = window.innerWidth <= 767.98 ? 12 : 16;
    const actionBars = Array.from(document.querySelectorAll(".action-bar"));
    const extraOffset = actionBars.reduce((maxOffset, bar) => {
      const rect = bar.getBoundingClientRect();
      const overlap = Math.max(0, window.innerHeight - rect.top);
      return Math.max(maxOffset, overlap > 0 ? overlap + 12 : 0);
    }, 0);
    button.style.bottom = `${baseOffset + extraOffset}px`;
  };

  const handleViewportChange = () => {
    toggleVisibility();
    updateButtonPosition();
  };

  window.addEventListener("scroll", handleViewportChange, { passive: true });
  window.addEventListener("resize", updateButtonPosition);
  toggleVisibility();
  updateButtonPosition();
}

document.addEventListener("DOMContentLoaded", initBackToTop);
