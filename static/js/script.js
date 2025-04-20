document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("download-form");
    const submitBtn = document.getElementById("submit-button");
    const loadingOverlay = document.getElementById("loading-overlay");

    form.addEventListener("submit", () => {
        submitBtn.disabled = true;
        submitBtn.innerText = "Processing...";
        // loadingOverlay.style.display = "flex";
    });

    // Always run this after page load (after redirect)
    window.addEventListener("pageshow", () => {
        submitBtn.disabled = false;
        submitBtn.innerText = "Extract Audio";
        loadingOverlay.style.display = "none";
    });

    // Theme toggle init
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);
});