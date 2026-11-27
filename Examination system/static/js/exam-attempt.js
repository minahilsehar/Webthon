(() => {
    const root = document.querySelector("[data-attempt][data-autosave-url]");
    const form = document.getElementById("submit-attempt");
    if (!root || !form) return;

    const attemptId = root.dataset.attempt;
    const attemptKey = `${attemptId}:${root.dataset.attemptStarted}`;
    const workspaceKey = `imtihanify-workspace:${root.dataset.user}`;
    const scratchpadKey = `imtihanify-scratchpad:${attemptKey}`;
    const status = document.getElementById("attempt-status");
    const timer = document.getElementById("attempt-timer");
    const submitButton = document.getElementById("submit-button");
    const textSize = document.getElementById("workspace-text-size");
    const scratchpad = document.getElementById("attempt-scratchpad");
    const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
    const databaseRequest = indexedDB.open("examflow-outbox", 1);
    let database;
    let flushPromise = null;
    const pendingWrites = new Set();
    let deadlineReached = Number(timer.dataset.seconds) <= 0;
    let attemptClosed = false;
    let remaining = Number(timer.dataset.seconds);

    function readLocalValue(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            setStatus("Browser storage is unavailable. Workspace preferences may not be retained.");
            return null;
        }
    }

    function writeLocalValue(key, value, failureMessage) {
        try {
            window.localStorage.setItem(key, value);
            return true;
        } catch (error) {
            setStatus(failureMessage);
            return false;
        }
    }

    const savedTextSize = readLocalValue(workspaceKey);
    textSize.value = savedTextSize === "large" ? "large" : "standard";
    root.dataset.textSize = textSize.value;
    textSize.addEventListener("change", () => {
        root.dataset.textSize = textSize.value;
        writeLocalValue(
            workspaceKey,
            textSize.value,
            "This device could not save your workspace preference.",
        );
    });

    scratchpad.value = readLocalValue(scratchpadKey) || "";
    scratchpad.addEventListener("input", () => {
        writeLocalValue(
            scratchpadKey,
            scratchpad.value,
            "This device could not save your scratchpad notes. Copy them before leaving.",
        );
    });

    function updateQuestionNavigation(fieldset) {
        const questionId = fieldset.dataset.question;
        const link = document.querySelector(`[data-question-nav][data-question-id="${questionId}"]`);
        if (!link) return;

        const reviewButton = fieldset.querySelector("[data-review-toggle]");
        const markedForReview = reviewButton?.getAttribute("aria-pressed") === "true";
        const answered = fieldset.querySelectorAll("input[type=checkbox]:checked").length > 0;
        const state = markedForReview
            ? (answered ? "answered-review" : "review")
            : (answered ? "answered" : "unanswered");
        const stateText = markedForReview
            ? (answered ? "Answered · Review" : "Marked for review")
            : (answered ? "Answered" : "Not answered");

        link.dataset.state = state;
        link.querySelector("[data-question-status]").textContent = stateText;
        link.setAttribute(
            "aria-label",
            `Question ${link.dataset.questionNumber}: ${stateText}`,
        );
    }

    for (const fieldset of document.querySelectorAll("[data-question]")) {
        const reviewButton = fieldset.querySelector("[data-review-toggle]");
        const reviewKey = `${attemptKey}:review:${fieldset.dataset.question}`;
        if (readLocalValue(reviewKey) === "true") {
            reviewButton.setAttribute("aria-pressed", "true");
            reviewButton.textContent = "Remove review mark";
        }
        reviewButton.addEventListener("click", () => {
            const marked = reviewButton.getAttribute("aria-pressed") !== "true";
            reviewButton.setAttribute("aria-pressed", String(marked));
            reviewButton.textContent = marked ? "Remove review mark" : "Mark for review";
            writeLocalValue(
                reviewKey,
                String(marked),
                "This device could not save the review mark.",
            );
            updateQuestionNavigation(fieldset);
        });
        updateQuestionNavigation(fieldset);
        fieldset.addEventListener("change", () => updateQuestionNavigation(fieldset));
    }

    databaseRequest.onupgradeneeded = () => {
        databaseRequest.result.createObjectStore("answers", { keyPath: "key" });
    };
    databaseRequest.onsuccess = () => {
        database = databaseRequest.result;
        restoreQueuedAnswers()
            .then(() => flushOutbox())
            .then(() => sendHeartbeat())
            .catch((error) => setStatus(error.message));
    };
    databaseRequest.onerror = () => {
        setStatus("Offline answer storage is unavailable. Do not close this page.");
        submitButton.disabled = true;
    };

    function setStatus(message) {
        status.textContent = message;
    }

    function transaction(mode) {
        return database.transaction("answers", mode).objectStore("answers");
    }

    function allQueuedAnswers() {
        return new Promise((resolve, reject) => {
            const request = transaction("readonly").getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    function queueAnswer(fieldset, value) {
        return new Promise((resolve, reject) => {
            const store = transaction("readwrite");
            const key = `${attemptKey}:${fieldset.dataset.question}`;
            const request = store.get(key);
            request.onsuccess = () => {
                const sequence = Math.max(
                    Number(fieldset.dataset.sequence),
                    request.result ? request.result.sequence : 0,
                ) + 1;
                const record = {
                    key,
                    attemptKey,
                    questionId: Number(fieldset.dataset.question),
                    sequence,
                    value,
                    url: root.dataset.autosaveUrl,
                };
                store.put(record);
                store.transaction.oncomplete = () => resolve(record);
                store.transaction.onerror = () => reject(store.transaction.error);
            };
            request.onerror = () => reject(request.error);
        });
    }

    function removeAcknowledged(record, savedSequence) {
        return new Promise((resolve, reject) => {
            const store = transaction("readwrite");
            const request = store.get(record.key);
            request.onsuccess = () => {
                if (request.result && request.result.sequence <= savedSequence) {
                    store.delete(record.key);
                }
                store.transaction.oncomplete = resolve;
                store.transaction.onerror = () => reject(store.transaction.error);
            };
            request.onerror = () => reject(request.error);
        });
    }

    function updateQueuedSequence(record, sequence) {
        return new Promise((resolve, reject) => {
            const store = transaction("readwrite");
            store.put({ ...record, sequence });
            store.transaction.oncomplete = resolve;
            store.transaction.onerror = () => reject(store.transaction.error);
        });
    }

    async function restoreQueuedAnswers() {
        for (const record of await allQueuedAnswers()) {
            if (record.attemptKey !== attemptKey) continue;
            const fieldset = document.querySelector(`[data-question="${record.questionId}"]`);
            if (!fieldset || record.sequence <= Number(fieldset.dataset.sequence)) continue;
            for (const input of fieldset.querySelectorAll("input[type=checkbox]")) {
                input.checked = record.value.includes(input.value);
            }
            updateQuestionNavigation(fieldset);
        }
    }

    function flushOutbox() {
        if (!database) return Promise.reject(new Error("Offline answer storage is unavailable."));
        if (flushPromise) return flushPromise;
        flushPromise = (async () => {
            if (!navigator.onLine) throw new Error("You are offline. Answers are queued on this device.");
            await Promise.all([...pendingWrites]);
            while (true) {
                const records = (await allQueuedAnswers())
                    .filter((record) => record.attemptKey === attemptKey);
                if (!records.length) break;
                for (const record of records) {
                    let queued = record;
                    let saved = false;
                    for (let retry = 0; retry < 3; retry += 1) {
                        const response = await fetch(queued.url, {
                            method: "POST",
                            credentials: "same-origin",
                            headers: {
                                "Content-Type": "application/json",
                                "X-CSRFToken": csrfToken,
                            },
                            body: JSON.stringify({
                                question_id: queued.questionId,
                                sequence: queued.sequence,
                                value: queued.value,
                            }),
                        });
                        const result = await response.json();
                        if (response.status === 409 && Number.isInteger(result.sequence)) {
                            queued = { ...queued, sequence: result.sequence + 1 };
                            await updateQueuedSequence(queued, queued.sequence);
                            continue;
                        }
                        if (!response.ok) throw new Error(result.error || "Answer save failed.");
                        await removeAcknowledged(queued, result.sequence);
                        const fieldset = document.querySelector(`[data-question="${queued.questionId}"]`);
                        if (fieldset) fieldset.dataset.sequence = String(result.sequence);
                        saved = true;
                        break;
                    }
                    if (!saved) throw new Error("Answer changed in another session. Try saving again.");
                }
            }
            setStatus("All answers saved.");
        })().finally(() => {
            flushPromise = null;
        });
        return flushPromise;
    }

    async function saveFieldset(fieldset) {
        const selected = [...fieldset.querySelectorAll("input[type=checkbox]:checked")]
            .map((input) => input.value);
        const pending = queueAnswer(fieldset, selected);
        pendingWrites.add(pending);
        try {
            await pending;
        } catch (error) {
            setStatus(error.message);
            return;
        } finally {
            pendingWrites.delete(pending);
        }
        setStatus("Saving answers…");
        try {
            await flushOutbox();
        } catch (error) {
            setStatus(error.message);
        }
    }

    for (const fieldset of document.querySelectorAll("[data-question]")) {
        fieldset.addEventListener("change", () => saveFieldset(fieldset));
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        submitButton.disabled = true;
        for (const input of form.querySelectorAll("input[type=checkbox]")) input.disabled = true;
        try {
            await flushOutbox();
            form.submit();
        } catch (error) {
            setStatus(error.message);
            submitButton.disabled = false;
            if (!attemptClosed) {
                for (const input of form.querySelectorAll("input[type=checkbox]")) input.disabled = false;
            }
        }
    });

    async function sendHeartbeat() {
        await flushOutbox();
        const response = await fetch(root.dataset.heartbeatUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrfToken },
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Connection check failed.");
        remaining = result.remaining_seconds;
        if (result.status !== "in_progress") {
            attemptClosed = true;
            for (const input of form.querySelectorAll("input[type=checkbox]")) input.disabled = true;
            setStatus("The attempt has ended. Your saved answers were submitted.");
        }
    }

    window.addEventListener("online", () => {
        if (!attemptClosed) sendHeartbeat().catch((error) => setStatus(error.message));
        else flushOutbox().catch((error) => setStatus(error.message));
    });
    window.addEventListener("offline", () => {
        if (!attemptClosed) setStatus("Connection lost. New answer changes will be queued on this device.");
    });
    window.setInterval(() => {
        if (remaining > 0) remaining -= 1;
        timer.textContent = String(Math.max(0, remaining));
        if (remaining === 0 && !deadlineReached) {
            deadlineReached = true;
            sendHeartbeat().catch((error) => setStatus(error.message));
        }
    }, 1000);
    window.setInterval(() => {
        if (!attemptClosed) sendHeartbeat().catch((error) => setStatus(error.message));
    }, 30000);
})();
