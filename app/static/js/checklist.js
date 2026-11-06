// Ticking documents, progress, printing and sharing on a checklist page.
// Ticks are saved only in this browser. Nothing here is sent to the server.
// Without JavaScript, the page still shows every section and printing still
// works from the browser's own menu.

(function () {
    "use strict";

    const page = document.querySelector("[data-checklist]");
    if (!page) {
        return;
    }

    const storageKey = page.dataset.checklist;
    const boxes = Array.from(page.querySelectorAll("input[data-document-id]"));
    const progressPanel = page.querySelector("[data-progress]");
    const progressText = page.querySelector("[data-progress-text]");
    const progressBar = page.querySelector("[data-progress-bar]");
    const shareMessage = page.querySelector("[data-share-message]");

    // Browser storage can be blocked, for example in a private window.
    // The ticks then last only until the page closes.
    function loadTicks() {
        try {
            const saved = JSON.parse(localStorage.getItem(storageKey));
            return Array.isArray(saved) ? saved : [];
        } catch (error) {
            return [];
        }
    }

    function saveTicks() {
        const ticked = boxes
            .filter(function (box) { return box.checked; })
            .map(function (box) { return box.dataset.documentId; });
        try {
            localStorage.setItem(storageKey, JSON.stringify(ticked));
        } catch (error) {
            // Nothing more to do. The ticks still show on this page.
        }
    }

    function updateProgress() {
        const required = boxes.filter(function (box) {
            return box.hasAttribute("data-required");
        });
        const done = required.filter(function (box) { return box.checked; }).length;
        const percent = required.length ? Math.round((done / required.length) * 100) : 0;

        if (required.length === 0) {
            progressText.textContent = "No required documents are listed.";
        } else if (done === required.length) {
            progressText.textContent = "You've ticked all " + required.length + " required documents.";
        } else {
            progressText.textContent = done + " of " + required.length + " required documents ready";
        }
        progressBar.style.width = percent + "%";
    }

    if (progressPanel) {
        const saved = loadTicks();
        boxes.forEach(function (box) {
            box.checked = saved.includes(box.dataset.documentId);
            box.addEventListener("change", function () {
                saveTicks();
                updateProgress();
            });
        });

        progressPanel.querySelector("[data-reset-button]").addEventListener("click", function () {
            boxes.forEach(function (box) { box.checked = false; });
            saveTicks();
            updateProgress();
        });

        progressPanel.hidden = false;
        updateProgress();
    }

    // ---------- Print ----------

    const printButton = page.querySelector("[data-print-button]");
    printButton.hidden = false;
    printButton.addEventListener("click", function () {
        window.print();
    });

    // ---------- Share ----------

    function showAddress() {
        shareMessage.textContent = "Copy this link: " + window.location.href;
    }

    function copyAddress() {
        if (!navigator.clipboard) {
            showAddress();
            return;
        }
        navigator.clipboard.writeText(window.location.href).then(function () {
            shareMessage.textContent = "Link copied.";
        }, showAddress);
    }

    const shareButton = page.querySelector("[data-share-button]");
    shareButton.hidden = false;
    shareButton.addEventListener("click", function () {
        if (navigator.share) {
            navigator.share({ title: document.title, url: window.location.href })
                .catch(function () {
                    // The person closed the share menu, so nothing is needed.
                });
        } else {
            copyAddress();
        }
    });
}());
