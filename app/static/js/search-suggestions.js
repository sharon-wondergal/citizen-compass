// Fills the search box's suggestion list as someone types.
// Search still works fully without this file.

(function () {
    "use strict";

    const WAIT_AFTER_TYPING_MS = 250;
    const MINIMUM_LENGTH = 2;

    function connect(input) {
        const list = document.getElementById(input.getAttribute("list"));
        let timer = null;
        let currentRequest = null;

        function showSuggestions(names) {
            // Setting .value keeps each suggestion as plain text, never as HTML.
            list.replaceChildren(...names.map(function (name) {
                const option = document.createElement("option");
                option.value = name;
                return option;
            }));
        }

        function fetchSuggestions() {
            const text = input.value.trim();
            if (currentRequest) {
                currentRequest.abort();
            }
            if (text.length < MINIMUM_LENGTH) {
                showSuggestions([]);
                return;
            }

            currentRequest = new AbortController();
            const address = input.dataset.suggestUrl + "?q=" + encodeURIComponent(text);

            fetch(address, { signal: currentRequest.signal })
                .then(function (response) {
                    return response.ok ? response.json() : { suggestions: [] };
                })
                .then(function (data) {
                    showSuggestions(data.suggestions);
                })
                .catch(function () {
                    // Suggestions are optional, so a failed request is ignored.
                });
        }

        input.addEventListener("input", function () {
            clearTimeout(timer);
            timer = setTimeout(fetchSuggestions, WAIT_AFTER_TYPING_MS);
        });
    }

    document.querySelectorAll("input[data-suggest-url]").forEach(connect);
}());
