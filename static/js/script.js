// Ensure UI resets on every load
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("download-form");
    const submitBtn = document.getElementById("submit-button");
    const loadingOverlay = document.getElementById("loading-overlay");

    // Reset button and overlay state
    submitBtn.disabled = false;
    submitBtn.innerText = "Extract Audio";
    loadingOverlay.style.display = "none";

    // Show overlay on submit
    form.addEventListener("submit", () => {
        submitBtn.disabled = true;
        submitBtn.innerText = "Processing...";
        loadingOverlay.style.display = "flex";
    });
});