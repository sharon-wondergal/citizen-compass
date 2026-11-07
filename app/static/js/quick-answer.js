// Shows the answer on the homepage without leaving the page.
// Without this file, the form opens the normal search page instead.
// Answers are added with textContent, so stored text can never run as code.

(function () {
    "use strict";

    const form = document.getElementById("ask-form");
    const input = document.getElementById("home-search");
    const answerArea = document.getElementById("quick-answer");
    if (!form || !answerArea) {
        return;
    }

    const STATUS_ICONS = {
        verified: "bi-patch-check-fill",
        pending: "bi-hourglass-split",
        outdated: "bi-exclamation-triangle-fill",
        unavailable: "bi-question-circle-fill"
    };

    function element(tag, className, text) {
        const item = document.createElement(tag);
        if (className) {
            item.className = className;
        }
        if (text) {
            item.textContent = text;
        }
        return item;
    }

    function icon(name) {
        const item = element("i", "bi " + name);
        item.setAttribute("aria-hidden", "true");
        return item;
    }

    function badge(className, iconName, label) {
        const item = element("span", "status-badge " + className);
        item.append(icon(iconName), " " + label);
        return item;
    }

    function factCard(iconName, label, value) {
        const card = element("div", "answer-fact");
        const heading = element("span", "answer-fact-label");
        heading.append(icon(iconName), " " + label);
        card.append(heading, element("div", "answer-fact-value", value));
        return card;
    }

    function showAnswer(answer) {
        const card = element("article", "answer-card");

        const header = element("div", "answer-header");
        header.append(element("h2", "", answer.name), element("span", "answer-agency", answer.agency));

        const badges = element("p", "answer-badges");
        badges.append(badge("status-" + answer.status, STATUS_ICONS[answer.status], answer.status_label));
        if (answer.is_demo) {
            badges.append(" ", badge("status-demo", "bi-cone-striped", "Demonstration only"));
        }

        const facts = element("div", "answer-grid");
        facts.append(
            factCard("bi-folder2-open", "Documents needed", answer.documents),
            factCard("bi-cash-stack", "Fee", answer.fee),
            factCard("bi-geo-alt-fill", "Nearest office", answer.office),
            factCard("bi-hourglass-split", "How long it takes", answer.time)
        );

        const footer = element("div", "answer-footer");
        const checklist = element("a", "btn btn-cc-primary", "Open the full checklist");
        checklist.href = answer.checklist_url;
        footer.append(checklist);
        if (answer.website) {
            const website = element("a", "btn btn-outline-secondary", "Agency website");
            website.href = answer.website;
            website.target = "_blank";
            website.rel = "noopener noreferrer";
            footer.append(website);
        }
        const note = element("span", "answer-note");
        note.append(icon("bi-check-circle"), " Always confirm with the official source");
        footer.append(note);

        card.append(header, badges, facts, footer);
        answerArea.replaceChildren(card);
    }

    function showNotFound(answer) {
        const box = element("div", "answer-missing");
        box.append(icon("bi-exclamation-circle"));

        const text = element("div");
        text.append(element("p", "answer-missing-title", "No service matched “" + answer.query + "”."));
        if (answer.suggestion) {
            const retry = element("button", "btn btn-link p-0", "Did you mean " + answer.suggestion + "?");
            retry.type = "button";
            retry.addEventListener("click", function () {
                input.value = answer.suggestion;
                ask(answer.suggestion);
            });
            text.append(retry);
        } else {
            text.append(element(
                "p", "mb-0",
                "Check the spelling or try fewer words. This service may not be in our directory yet."
            ));
        }
        box.append(text);
        answerArea.replaceChildren(box);
    }

    function ask(question) {
        const address = answerArea.dataset.answerUrl + "?q=" + encodeURIComponent(question);
        fetch(address)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("No answer");
                }
                return response.json();
            })
            .then(function (answer) {
                if (answer.found) {
                    showAnswer(answer);
                } else {
                    showNotFound(answer);
                }
            })
            .catch(function () {
                // If the answer can't load, use the normal search page.
                form.submit();
            });
    }

    form.addEventListener("submit", function (event) {
        const question = input.value.trim();
        if (question) {
            event.preventDefault();
            ask(question);
        }
    });

    document.querySelectorAll("[data-quick-query]").forEach(function (tag) {
        tag.addEventListener("click", function (event) {
            event.preventDefault();
            input.value = tag.dataset.quickQuery;
            ask(tag.dataset.quickQuery);
        });
    });
}());
