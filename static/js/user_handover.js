"use strict";

const sidebarToggle = document.getElementById("sidebarToggle");
sidebarToggle?.addEventListener("click", () => {
    const open = document.getElementById("sidebar").classList.toggle("open");
    sidebarToggle.setAttribute("aria-expanded", String(open));
});

document.querySelectorAll("[data-pdf-fit]").forEach(button => {
    button.addEventListener("click", () => {
        const frame = document.getElementById("handoverPdfFrame");
        if (!frame) return;
        const url = new URL(frame.src);
        url.hash = "view=" + button.dataset.pdfFit;
        frame.src = url.href;
    });
});
