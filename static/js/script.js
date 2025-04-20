document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("download-form");
    const submitBtn = document.getElementById("submit-button");
    const loadingOverlay = document.getElementById("loading-overlay");

    form.addEventListener("submit", () => {
        submitBtn.disabled = true;
        submitBtn.innerText = "Processing...";
        loadingOverlay.style.display = "flex";
    });

    // Close loading screen on page load (after redirect)
    if (loadingOverlay.style.display === "flex") {
        window.addEventListener("pageshow", () => {
            submitBtn.disabled = false;
            submitBtn.innerText = "Extract Audio";
            loadingOverlay.style.display = "none";
        });
    }

    // Theme toggle
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);
});

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
}