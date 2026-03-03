const TOAST_ICONS = {
    success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
};

const TOAST_CLOSE_ICON = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

function showToast(message, type = "success", duration = 4500) {
    const container = document.getElementById("toast-container");
    if (!container || !message) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${TOAST_ICONS[type] || ""}</span>
        <span class="toast-msg">${message}</span>
        <button class="toast-close" type="button" aria-label="Dismiss">${TOAST_CLOSE_ICON}</button>
    `;

    const dismiss = () => {
        toast.classList.add("is-hiding");
        setTimeout(() => toast.remove(), 310);
    };

    toast.querySelector(".toast-close").addEventListener("click", dismiss);
    container.appendChild(toast);
    setTimeout(dismiss, duration);
}

function parseInitialSubscriptions(rawValue) {
    if (!rawValue) return [];

    try {
        const parsed = JSON.parse(rawValue);
        if (Array.isArray(parsed)) {
            return parsed
                .filter((item) => item && typeof item === "object")
                .map((item) => ({
                    name: String(item.name || "").trim(),
                    date: String(item.date || "").trim(),
                }))
                .filter((item) => item.name && item.date);
        }

        if (parsed && typeof parsed === "object") {
            return Object.entries(parsed)
                .map(([name, date]) => ({
                    name: String(name || "").trim(),
                    date: String(date || "").trim(),
                }))
                .filter((item) => item.name && item.date);
        }
    } catch (_error) {
        return [];
    }

    return [];
}

function createSubscriptionRow(sub = {}) {
    const row = document.createElement("div");
    row.className = "sub-row";

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "sub-name";
    nameInput.placeholder = "subscription name (e.g. sml)";
    nameInput.value = sub.name || "";

    const dateInput = document.createElement("input");
    dateInput.type = "date";
    dateInput.className = "sub-date";
    dateInput.value = sub.date || "";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn tertiary sub-remove";
    removeBtn.textContent = "x";

    row.appendChild(nameInput);
    row.appendChild(dateInput);
    row.appendChild(removeBtn);
    return row;
}

function renderEmptyState(listEl) {
    if (listEl.querySelector(".sub-row")) return;

    const empty = document.createElement("p");
    empty.className = "sub-empty";
    empty.textContent = "No subscriptions added.";
    listEl.appendChild(empty);
}

function serializeSubscriptions(form, defaultDate) {
    const rows = form.querySelectorAll(".sub-row");
    const output = [];

    rows.forEach((row) => {
        const nameInput = row.querySelector(".sub-name");
        const dateInput = row.querySelector(".sub-date");
        const name = (nameInput?.value || "").trim().toLowerCase();
        const date = (dateInput?.value || "").trim() || defaultDate;
        if (name && date) output.push({ name, date });
    });

    const hiddenInput = form.querySelector(".subscriptions-json");
    hiddenInput.value = JSON.stringify(output);
}

function bindSubscriptionUI(form) {
    const defaultDate = form.dataset.defaultDate || "2027-02-25";
    const listEl = form.querySelector(".subscriptions-list");
    const hiddenInput = form.querySelector(".subscriptions-json");
    const addBtn = form.querySelector(".add-subscription-btn");

    const clearRows = () => {
        listEl.innerHTML = "";
    };

    const addRow = (sub = {}) => {
        listEl.querySelector(".sub-empty")?.remove();
        listEl.appendChild(createSubscriptionRow(sub));
    };

    const setSubscriptions = (subs) => {
        clearRows();
        const items = Array.isArray(subs) ? subs : [];
        if (items.length) {
            items.forEach((sub) => addRow(sub));
        } else {
            renderEmptyState(listEl);
        }
    };

    const initialItems = parseInitialSubscriptions(hiddenInput.value);
    hiddenInput.value = "[]";
    setSubscriptions(initialItems);

    addBtn.addEventListener("click", () => {
        addRow({ date: defaultDate });
    });

    listEl.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (!target.classList.contains("sub-remove")) return;
        target.closest(".sub-row")?.remove();
        renderEmptyState(listEl);
    });

    form.addEventListener("submit", () => {
        serializeSubscriptions(form, defaultDate);
    });

    return { setSubscriptions, defaultDate };
}

function setupModal(modalEl, openFn, closeBtnId) {
    const closeBtn = document.getElementById(closeBtnId);
    if (!modalEl || !closeBtn) return { open: () => {}, close: () => {} };

    const close = () => {
        modalEl.classList.remove("is-open");
        modalEl.setAttribute("aria-hidden", "true");
    };

    const open = () => {
        modalEl.classList.add("is-open");
        modalEl.setAttribute("aria-hidden", "false");
        if (typeof openFn === "function") openFn();
    };

    closeBtn.addEventListener("click", close);
    modalEl.addEventListener("click", (event) => {
        if (event.target === modalEl) close();
    });

    return { open, close };
}

function setupSecretFields() {
    document.querySelectorAll(".secret-toggle").forEach((btn) => {
        btn.addEventListener("click", () => {
            const input = btn.closest(".secret-field").querySelector("input");
            const eyeIcon = btn.querySelector(".eye-icon");
            const eyeOffIcon = btn.querySelector(".eye-off-icon");
            const isHidden = input.type === "password";
            input.type = isHidden ? "text" : "password";
            eyeIcon.hidden = isHidden;
            eyeOffIcon.hidden = !isHidden;
        });
    });
}

function setupAccountSearch() {
    const input = document.getElementById("accountSearchInput");
    if (!input) return;

    const blocks = Array.from(document.querySelectorAll(".block"));

    const runFilter = () => {
        const query = (input.value || "").trim().toLowerCase();

        blocks.forEach((block) => {
            const rows = Array.from(block.querySelectorAll(".account-row"));
            const emptyMsg = block.querySelector(".search-empty");
            if (!rows.length) return;

            let visibleCount = 0;
            rows.forEach((row) => {
                const name = row.dataset.searchName || "";
                const phone = row.dataset.searchPhone || "";
                const matched = !query || name.includes(query) || phone.includes(query);
                row.classList.toggle("is-hidden", !matched);
                if (matched) visibleCount += 1;
            });

            if (emptyMsg) {
                emptyMsg.hidden = visibleCount > 0;
            }
        });
    };

    input.addEventListener("input", runFilter);
}

document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll(".account-form");
    const formControllers = new Map();
    forms.forEach((form) => {
        formControllers.set(form, bindSubscriptionUI(form));
    });

    const addModal = document.getElementById("addAccountModal");
    const openAddBtn = document.getElementById("openAddAccountModal");
    const addModalApi = setupModal(addModal, null, "closeAddAccountModal");
    if (openAddBtn) {
        openAddBtn.addEventListener("click", addModalApi.open);
    }

    const detailsModal = document.getElementById("accountDetailsModal");
    const detailsForm = document.getElementById("accountDetailsForm");
    const detailsTitle = document.getElementById("accountDetailsTitle");
    const detailsMode = document.getElementById("detailsMode");
    const detailsName = document.getElementById("detailsName");
    const detailsPhone = document.getElementById("detailsPhone");
    const detailsPassword = document.getElementById("detailsPassword");
    const detailsSession = document.getElementById("detailsSession");
    const detailsDeleteBtn = document.getElementById("detailsDeleteBtn");

    const detailsModalApi = setupModal(detailsModal, null, "closeAccountDetailsModal");
    const detailsController = detailsForm ? formControllers.get(detailsForm) : null;

    document.querySelectorAll(".view-account-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (!detailsForm || !detailsController) return;

            const title = btn.dataset.title || "Account Details";
            const editUrl = btn.dataset.editUrl || "";
            const deleteUrl = btn.dataset.deleteUrl || "";
            const subData = btn.dataset.subscriptions || "{}";

            detailsTitle.textContent = title;
            detailsForm.action = editUrl;

            // Pre-select the account's current mode
            if (detailsMode) detailsMode.value = btn.dataset.mode || "backup";

            detailsName.value = btn.dataset.name || "";
            detailsPhone.value = btn.dataset.phone || "";
            detailsPassword.value = btn.dataset.password || "";
            detailsSession.value = btn.dataset.session || "";
            detailsDeleteBtn.setAttribute("formaction", deleteUrl);

            detailsController.setSubscriptions(parseInitialSubscriptions(subData));
            detailsModalApi.open();
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (addModal?.classList.contains("is-open")) addModalApi.close();
        if (detailsModal?.classList.contains("is-open")) detailsModalApi.close();
    });

    setupSecretFields();
    setupAccountSearch();

    // Show server-rendered flash messages as toasts
    document.querySelectorAll(".flash-data").forEach((el) => {
        showToast(el.dataset.msg, el.dataset.type);
    });
});
