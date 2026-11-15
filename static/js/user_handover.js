"use strict";

const sidebarToggle = document.getElementById("sidebarToggle");
sidebarToggle?.addEventListener("click", () => {
    const open = document.getElementById("sidebar").classList.toggle("open");
    sidebarToggle.setAttribute("aria-expanded", String(open));
});

const pdfFrame = document.getElementById("handoverPdfFrame");
const pdfStatus = document.getElementById("handoverPdfStatus");
const pdfRetry = document.getElementById("handoverPdfRetry");
const fitButtons = document.querySelectorAll("[data-pdf-fit]");
let pdfObjectUrl = null;
let pdfController = null;
let pageHidden = false;

async function loadHandoverPdf() {
    if (!pdfFrame || !pdfStatus) return;
    pdfController?.abort();
    const controller = new AbortController();
    pdfController = controller;
    const timeout = setTimeout(() => controller.abort(), 60000);
    pdfFrame.hidden = true;
    pdfStatus.hidden = false;
    pdfStatus.className = "alert alert-light border";
    pdfStatus.textContent = "جارٍ تحميل معاينة PDF…";
    if (pdfRetry) pdfRetry.hidden = true;
    fitButtons.forEach(button => { button.disabled = true; });
    try {
        // Fetch our authenticated document as data. Hosting may add frame-blocking
        // headers to PDF responses even when Django sets SAMEORIGIN. A local blob
        // displays the same PDF without weakening protection on other site pages.
        const endpoint = new URL(pdfFrame.dataset.pdfUrl, window.location.href);
        if (endpoint.origin !== window.location.origin) throw new Error("origin");
        const response = await fetch(endpoint.href, {
            credentials: "same-origin", cache: "no-store",
            headers: { Accept: "application/pdf" }, signal: controller.signal
        });
        if (!response.ok) {
            if (response.status === 403) throw new Error("permission");
            throw new Error("generation");
        }
        if (!(response.headers.get("Content-Type") || "").toLowerCase().startsWith("application/pdf")) {
            throw new Error(response.redirected ? "login" : "generation");
        }
        const blob = await response.blob();
        if (await blob.slice(0, 5).text() !== "%PDF-") throw new Error("generation");
        if (controller.signal.aborted || pageHidden) return;
        if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
        pdfObjectUrl = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        pdfFrame.src = pdfObjectUrl + "#view=FitH";
        pdfFrame.hidden = false;
        pdfStatus.hidden = true;
        fitButtons.forEach(button => { button.disabled = false; });
    } catch (error) {
        if (pdfController !== controller || pageHidden) return;
        const message = error.message === "login"
            ? "انتهت جلسة الدخول. حدّث الصفحة وسجّل الدخول لعرض المعاينة."
            : error.message === "permission"
                ? "لا يملك حسابك صلاحية عرض هذا التقرير."
                : error.name === "AbortError"
                    ? "استغرق تجهيز المعاينة وقتًا طويلًا. حاول إعادة تحميلها."
                    : "تعذر تحميل معاينة PDF. حاول مجددًا أو استخدم «فتح وطباعة PDF» لعرض التفاصيل.";
        pdfStatus.textContent = message;
        pdfStatus.className = "alert alert-danger";
        if (pdfRetry) pdfRetry.hidden = false;
    } finally {
        clearTimeout(timeout);
    }
}

pdfRetry?.addEventListener("click", loadHandoverPdf);
window.addEventListener("pagehide", () => {
    pageHidden = true;
    pdfController?.abort();
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    pdfObjectUrl = null;
});
window.addEventListener("pageshow", event => {
    pageHidden = false;
    if (event.persisted) loadHandoverPdf();
});

fitButtons.forEach(button => {
    button.addEventListener("click", () => {
        if (!pdfFrame || !pdfObjectUrl) return;
        const url = new URL(pdfObjectUrl);
        url.hash = "view=" + button.dataset.pdfFit;
        pdfFrame.src = url.href;
    });
});

loadHandoverPdf();
