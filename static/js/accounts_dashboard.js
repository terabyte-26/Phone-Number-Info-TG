/* ── Toast system ── */

const TOAST_ICONS = {
    success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
};

const TOAST_CLOSE_ICON = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

function showToast(message, type = "success", duration = 4000) {
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
        setTimeout(() => toast.remove(), 260);
    };

    toast.querySelector(".toast-close").addEventListener("click", dismiss);
    container.appendChild(toast);
    setTimeout(dismiss, duration);
}


/* ── Custom confirm dialog ── */

function showConfirm(title, message, onOk) {
    const dialog = document.getElementById("confirmDialog");
    const titleEl = document.getElementById("confirmTitle");
    const msgEl = document.getElementById("confirmMessage");
    const okBtn = document.getElementById("confirmOk");
    const cancelBtn = document.getElementById("confirmCancel");

    if (!dialog) {
        // Fallback to native confirm
        if (confirm(title + "\n" + message)) onOk();
        return;
    }

    titleEl.textContent = title;
    msgEl.textContent = message;
    dialog.classList.add("is-open");
    dialog.setAttribute("aria-hidden", "false");

    const cleanup = () => {
        dialog.classList.remove("is-open");
        dialog.setAttribute("aria-hidden", "true");
        okBtn.replaceWith(okBtn.cloneNode(true));
        cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    document.getElementById("confirmOk").addEventListener("click", () => {
        cleanup();
        onOk();
    });

    document.getElementById("confirmCancel").addEventListener("click", cleanup);

    dialog.addEventListener("click", (e) => {
        if (e.target === dialog) cleanup();
    });
}


/* ── Subscription helpers ── */

function parseInitialSubscriptions(rawValue) {
    if (!rawValue) return [];
    try {
        const parsed = JSON.parse(rawValue);
        if (Array.isArray(parsed)) {
            return parsed
                .filter((item) => item && typeof item === "object")
                .map((item) => ({ name: String(item.name || "").trim(), date: String(item.date || "").trim() }))
                .filter((item) => item.name && item.date);
        }
        if (parsed && typeof parsed === "object") {
            return Object.entries(parsed)
                .map(([name, date]) => ({ name: String(name || "").trim(), date: String(date || "").trim() }))
                .filter((item) => item.name && item.date);
        }
    } catch (_) {
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
        const name = (row.querySelector(".sub-name")?.value || "").trim().toLowerCase();
        const date = (row.querySelector(".sub-date")?.value || "").trim() || defaultDate;
        if (name && date) output.push({ name, date });
    });
    form.querySelector(".subscriptions-json").value = JSON.stringify(output);
}

function bindSubscriptionUI(form) {
    const today = new Date().toISOString().slice(0, 10);
    const defaultDate = today;
    const listEl = form.querySelector(".subscriptions-list");
    const hiddenInput = form.querySelector(".subscriptions-json");
    const addBtn = form.querySelector(".add-subscription-btn");

    const addRow = (sub = {}) => {
        listEl.querySelector(".sub-empty")?.remove();
        listEl.appendChild(createSubscriptionRow(sub));
    };

    const setSubscriptions = (subs) => {
        listEl.innerHTML = "";
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

    addBtn.addEventListener("click", () => addRow({ date: defaultDate }));

    listEl.addEventListener("click", (event) => {
        if (!(event.target instanceof HTMLElement)) return;
        if (!event.target.classList.contains("sub-remove")) return;
        event.target.closest(".sub-row")?.remove();
        renderEmptyState(listEl);
    });

    form.addEventListener("submit", () => serializeSubscriptions(form, defaultDate));

    return { setSubscriptions, defaultDate };
}


/* ── Modal ── */

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


/* ── Secret fields ── */

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


/* ── Account search ── */

let currentModeFilter = "all";

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
                const mode = row.dataset.mode || "";

                const matchesSearch = !query || name.includes(query) || phone.includes(query);
                const matchesFilter = currentModeFilter === "all" || mode === currentModeFilter;
                const visible = matchesSearch && matchesFilter;

                row.classList.toggle("is-hidden", !visible);
                if (visible) visibleCount += 1;
            });

            if (emptyMsg) emptyMsg.hidden = visibleCount > 0;
        });
    };

    input.addEventListener("input", runFilter);

    // "/" keyboard shortcut to focus search
    document.addEventListener("keydown", (e) => {
        if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "SELECT") {
            e.preventDefault();
            input.focus();
        }
    });

    // Filter chips
    const chips = document.querySelectorAll(".filter-chip");
    chips.forEach((chip) => {
        chip.addEventListener("click", () => {
            chips.forEach((c) => c.classList.remove("active"));
            chip.classList.add("active");
            currentModeFilter = chip.dataset.filter;
            runFilter();
        });
    });

    // Expose for external use
    window._runAccountFilter = runFilter;
}


/* ── Session generator ── */

function setupSessionGenerator() {
    document.querySelectorAll(".generate-session-btn").forEach((btn) => {
        const group        = btn.closest(".session-gen-group");
        const terminal     = group.querySelector(".session-terminal");
        const output       = terminal.querySelector(".terminal-output");
        const otpRow       = terminal.querySelector(".terminal-otp-row");
        const otpInput     = terminal.querySelector(".terminal-otp-input");
        const otpSubmit    = terminal.querySelector(".terminal-otp-submit");
        const cancelBtn    = terminal.querySelector(".terminal-cancel-btn");

        let evtSource = null;
        let jobId     = null;
        const origHTML = btn.innerHTML;

        const classifyLine = (msg) => {
            const lower = msg.toLowerCase();
            if (/error|failed|invalid|exception|timed out/i.test(msg)) return "err";
            if (/incorrect|expired|denied|could not/i.test(msg)) return "warn";
            if (/enter.*otp|enter.*code|otp below/i.test(msg)) return "prompt";
            if (/success|verified|exported|generated/i.test(msg)) return "ok";
            return "";
        };

        const appendLog = (msg, cls = "") => {
            const line = document.createElement("div");
            const resolved = cls || classifyLine(msg);
            line.className = "term-line" + (resolved ? " " + resolved : "");
            line.textContent = msg;
            output.appendChild(line);
            output.scrollTop = output.scrollHeight;
        };

        const stopStream = () => {
            if (evtSource) { evtSource.close(); evtSource = null; }
        };

        const resetBtn = () => {
            btn.disabled = false;
            btn.innerHTML = origHTML;
        };

        const closeTerminal = () => {
            terminal.hidden = true;
            otpRow.hidden   = true;
            otpInput.value  = "";
            output.innerHTML = "";
            jobId = null;
        };

        otpInput.addEventListener("input", () => {
            otpInput.value = otpInput.value.replace(/\D/g, "");
        });

        const handleOtpSubmit = () => {
            const otp = otpInput.value.trim();
            if (!otp || !jobId) return;
            fetch("/accounts/session/otp", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: new URLSearchParams({ job_id: jobId, otp }),
            }).catch(() => {});
            otpRow.hidden  = true;
            otpInput.value = "";
            appendLog("Code submitted, waiting...");
        };

        otpSubmit.addEventListener("click", handleOtpSubmit);
        otpInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                handleOtpSubmit();
            }
        });

        cancelBtn.addEventListener("click", () => {
            if (jobId) {
                fetch("/accounts/session/cancel", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({ job_id: jobId }),
                }).catch(() => {});
            }
            stopStream();
            resetBtn();
            closeTerminal();
        });

        btn.addEventListener("click", () => {
            const form          = btn.closest("form");
            const phoneInput    = form.querySelector("[name='phone']");
            const nameInput     = form.querySelector("[name='name']");
            const passwordInput = form.querySelector("[name='password']");
            const sessionInput  = group.querySelector("[name='session_string']");

            const phone    = (phoneInput?.value    || "").trim();
            const name     = (nameInput?.value     || "").trim();
            const password = (passwordInput?.value || "").trim();

            if (!phone) {
                showToast("Enter a phone number first", "error");
                phoneInput?.focus();
                return;
            }

            stopStream();
            output.innerHTML = "";
            otpRow.hidden    = true;
            otpInput.value   = "";
            terminal.hidden  = false;
            btn.disabled     = true;
            btn.textContent  = "Generating...";
            terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });

            fetch("/accounts/session/start", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: new URLSearchParams({ phone, name, password }),
            })
            .then((r) => r.json())
            .then((data) => {
                if (data.error) {
                    appendLog("Error: " + data.error, "err");
                    resetBtn();
                    return;
                }
                jobId = data.job_id;
                evtSource = new EventSource("/accounts/session/stream/" + encodeURIComponent(jobId));

                evtSource.onmessage = (e) => {
                    const payload = JSON.parse(e.data);

                    if (payload.type === "log") {
                        appendLog(payload.msg);
                    } else if (payload.type === "waiting_otp") {
                        appendLog("Enter the OTP code sent to your device:");
                        otpRow.hidden  = false;
                        otpInput.value = "";
                        otpInput.focus();
                    } else if (payload.type === "done") {
                        appendLog("Session generated successfully.", "ok");
                        sessionInput.value = payload.session;
                        showToast("Session string generated and filled", "success");
                        resetBtn();
                        stopStream();
                        // Update revoke button visibility
                        if (window._updateRevokeVisibility) window._updateRevokeVisibility();
                        setTimeout(closeTerminal, 3000);
                    } else if (payload.type === "error") {
                        appendLog(payload.msg || "Unknown error", "err");
                        resetBtn();
                        stopStream();
                    } else if (payload.type === "cancelled") {
                        resetBtn();
                        stopStream();
                        closeTerminal();
                    }
                };

                evtSource.onerror = () => {
                    if (evtSource) {
                        appendLog("Stream disconnected", "err");
                        resetBtn();
                        stopStream();
                    }
                };
            })
            .catch((err) => {
                appendLog("Failed to start: " + (err.message || err), "err");
                resetBtn();
            });
        });
    });
}


/* ── Main initialization ── */

document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll(".account-form");
    const formControllers = new Map();
    forms.forEach((form) => {
        formControllers.set(form, bindSubscriptionUI(form));
    });

    // Add modal
    const addModal = document.getElementById("addAccountModal");
    const openAddBtn = document.getElementById("openAddAccountModal");
    const emptyAddBtn = document.getElementById("emptyAddBtn");
    const addModalApi = setupModal(addModal, null, "closeAddAccountModal");
    if (openAddBtn) openAddBtn.addEventListener("click", addModalApi.open);
    if (emptyAddBtn) emptyAddBtn.addEventListener("click", addModalApi.open);

    // Details modal
    const detailsModal = document.getElementById("accountDetailsModal");
    const detailsForm = document.getElementById("accountDetailsForm");
    const detailsTitle = document.getElementById("accountDetailsTitle");
    const detailsMode = document.getElementById("detailsMode");
    const detailsName = document.getElementById("detailsName");
    const detailsPhone = document.getElementById("detailsPhone");
    const detailsPassword = document.getElementById("detailsPassword");
    const detailsSession = document.getElementById("detailsSession");
    const detailsDeleteBtn = document.getElementById("detailsDeleteBtn");
    const detailsRevokeBtn = detailsModal ? detailsModal.querySelector(".revoke-session-btn") : null;

    const detailsModalApi = setupModal(detailsModal, null, "closeAccountDetailsModal");
    const detailsController = detailsForm ? formControllers.get(detailsForm) : null;

    // Revoke button visibility
    const updateRevokeVisibility = () => {
        if (detailsRevokeBtn) {
            detailsRevokeBtn.hidden = !detailsSession.value.trim();
        }
    };

    window._updateRevokeVisibility = updateRevokeVisibility;

    if (detailsSession) {
        detailsSession.addEventListener("input", updateRevokeVisibility);
    }

    // Revoke session handler
    if (detailsRevokeBtn) {
        detailsRevokeBtn.addEventListener("click", () => {
            const phone = detailsPhone.value.trim();
            if (!phone) {
                showToast("No phone number", "error");
                return;
            }

            showConfirm(
                "Revoke Session",
                "This will terminate the Telegram session and remove the session string. This action cannot be undone.",
                () => {
                    const origText = detailsRevokeBtn.innerHTML;
                    detailsRevokeBtn.disabled = true;
                    detailsRevokeBtn.textContent = "Revoking...";

                    fetch("/accounts/session/revoke", {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: new URLSearchParams({ phone }),
                    })
                    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
                    .then(({ ok, data }) => {
                        if (ok) {
                            detailsSession.value = "";
                            updateRevokeVisibility();
                            showToast("Session revoked successfully", "success");
                        } else {
                            showToast(data.error || "Revoke failed", "error");
                        }
                    })
                    .catch((err) => {
                        showToast("Revoke failed: " + (err.message || err), "error");
                    })
                    .finally(() => {
                        detailsRevokeBtn.disabled = false;
                        detailsRevokeBtn.innerHTML = origText;
                    });
                }
            );
        });
    }

    // Delete button handler — use custom confirm
    if (detailsDeleteBtn) {
        detailsDeleteBtn.addEventListener("click", (e) => {
            e.preventDefault();
            const deleteUrl = detailsDeleteBtn.getAttribute("formaction");
            if (!deleteUrl) return;

            showConfirm(
                "Delete Account",
                "This will permanently remove this account and its session data. This cannot be undone.",
                () => {
                    const form = document.createElement("form");
                    form.method = "POST";
                    form.action = deleteUrl;
                    form.style.display = "none";
                    document.body.appendChild(form);
                    form.submit();
                }
            );
        });
    }

    // View account buttons
    document.querySelectorAll(".view-account-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (!detailsForm || !detailsController) return;

            const title = btn.dataset.title || "Account Details";
            const editUrl = btn.dataset.editUrl || "";
            const deleteUrl = btn.dataset.deleteUrl || "";
            const subData = btn.dataset.subscriptions || "{}";

            detailsTitle.textContent = title;
            detailsForm.action = editUrl;

            if (detailsMode) detailsMode.value = btn.dataset.mode || "backup";
            detailsName.value = btn.dataset.name || "";
            detailsPhone.value = btn.dataset.phone || "";
            detailsPassword.value = btn.dataset.password || "";
            detailsSession.value = btn.dataset.session || "";
            detailsDeleteBtn.setAttribute("formaction", deleteUrl);

            updateRevokeVisibility();
            detailsController.setSubscriptions(parseInitialSubscriptions(subData));
            detailsModalApi.open();
        });
    });

    // Escape to close modals
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        // Close confirm dialog first if open
        const confirm = document.getElementById("confirmDialog");
        if (confirm?.classList.contains("is-open")) {
            confirm.classList.remove("is-open");
            confirm.setAttribute("aria-hidden", "true");
            return;
        }
        if (addModal?.classList.contains("is-open")) addModalApi.close();
        if (detailsModal?.classList.contains("is-open")) detailsModalApi.close();
    });

    setupSecretFields();
    setupAccountSearch();
    setupSessionGenerator();

    // Flash messages as toasts
    document.querySelectorAll(".flash-data").forEach((el) => {
        showToast(el.dataset.msg, el.dataset.type);
    });

    // Stat bar fill animation
    document.querySelectorAll(".stat-bar-fill").forEach((bar, i) => {
        const targetWidth = bar.style.width || "0%";
        bar.style.width = "0%";
        setTimeout(() => {
            bar.style.transition = `width 1200ms cubic-bezier(0.22, 1, 0.36, 1)`;
            bar.style.width = targetWidth;
        }, 300 + i * 150);
    });

    // Stat counter animation — slot-machine / odometer style
    document.querySelectorAll(".stat-value[data-count]").forEach((el) => {
        const target = parseInt(el.dataset.count, 10);
        if (isNaN(target) || target <= 0) return;

        const digits = String(target).split("");
        el.textContent = "";

        // Get the computed height of one character cell
        const charH = parseFloat(getComputedStyle(el).fontSize) || 32;
        // Use line-height ratio to get actual slot height
        const slotH = Math.ceil(charH);

        digits.forEach((digit, i) => {
            const slot = document.createElement("span");
            slot.className = "digit-slot";
            slot.style.height = slotH + "px";

            const strip = document.createElement("span");
            strip.className = "digit-strip";

            // Digits 0 through 9
            for (let n = 0; n <= 9; n++) {
                const d = document.createElement("span");
                d.className = "digit-char";
                d.style.height = slotH + "px";
                d.textContent = n;
                strip.appendChild(d);
            }

            slot.appendChild(strip);
            el.appendChild(slot);

            const digitVal = parseInt(digit, 10);
            const delay = (digits.length - 1 - i) * 140;
            const duration = 1000 + i * 220;

            setTimeout(() => {
                strip.style.transition = `transform ${duration}ms cubic-bezier(0.22, 1, 0.36, 1)`;
                strip.style.transform = `translateY(-${digitVal * slotH}px)`;
            }, delay);
        });
    });
});
