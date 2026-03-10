/* ── API Keys Dashboard JS ── */
(function () {
    'use strict';

    // ── Toast ────────────────────────────────────────────────────────────────
    const toastContainer = document.getElementById('toast-container');

    function showToast(type, msg) {
        const icons = {
            success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        };
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML =
            `<span class="toast-icon">${icons[type] || ''}</span>` +
            `<span class="toast-msg">${msg}</span>` +
            `<button class="toast-close" aria-label="Close">&times;</button>`;
        toastContainer.appendChild(el);
        el.querySelector('.toast-close').onclick = () => dismiss(el);
        setTimeout(() => dismiss(el), 4000);
    }

    function dismiss(el) {
        if (el._gone) return;
        el._gone = true;
        el.classList.add('is-hiding');
        setTimeout(() => el.remove(), 260);
    }

    // Consume flash messages
    document.querySelectorAll('.flash-data').forEach(el => {
        showToast(el.dataset.type, el.dataset.msg);
        el.remove();
    });

    // ── Modal helpers ────────────────────────────────────────────────────────
    function openModal(id) {
        const m = document.getElementById(id);
        m.classList.add('is-open');
        m.setAttribute('aria-hidden', 'false');
    }

    function closeModal(id) {
        const m = document.getElementById(id);
        m.classList.remove('is-open');
        m.setAttribute('aria-hidden', 'true');
    }

    // Close modals on backdrop click
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.addEventListener('click', e => {
            if (e.target === backdrop) closeModal(backdrop.id);
        });
    });

    // Close buttons
    document.querySelectorAll('.modal-close-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const modal = btn.closest('.modal-backdrop');
            if (modal) closeModal(modal.id);
        });
    });

    // ── Add Key Modal ────────────────────────────────────────────────────────
    const addBtn = document.getElementById('openAddKeyModal');
    const emptyBtn = document.getElementById('emptyAddBtn');
    if (addBtn) addBtn.addEventListener('click', () => openModal('addKeyModal'));
    if (emptyBtn) emptyBtn.addEventListener('click', () => openModal('addKeyModal'));

    // ── Edit Key Modal ───────────────────────────────────────────────────────
    document.querySelectorAll('.edit-key-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const keyId = btn.dataset.keyId;
            document.getElementById('editProvider').value = btn.dataset.provider;
            document.getElementById('editLabel').value = btn.dataset.label;
            document.getElementById('editKey').value = btn.dataset.keyValue;
            document.getElementById('editKeyForm').action = `/api-keys/edit/${keyId}`;
            openModal('editKeyModal');
        });
    });

    // ── Delete Key ───────────────────────────────────────────────────────────
    const confirmDialog = document.getElementById('confirmDialog');
    const confirmForm = document.getElementById('confirmForm');
    const confirmCancel = document.getElementById('confirmCancel');

    document.querySelectorAll('.delete-key-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            confirmForm.action = btn.dataset.deleteUrl;
            confirmDialog.classList.add('is-open');
        });
    });

    if (confirmCancel) {
        confirmCancel.addEventListener('click', () => {
            confirmDialog.classList.remove('is-open');
        });
    }

    if (confirmDialog) {
        confirmDialog.addEventListener('click', e => {
            if (e.target === confirmDialog) confirmDialog.classList.remove('is-open');
        });
    }

    // ── Toggle Enable/Disable ────────────────────────────────────────────────
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const keyId = btn.dataset.keyId;
            try {
                const res = await fetch(`/api-keys/toggle/${keyId}`, { method: 'POST' });
                const data = await res.json();
                if (data.enabled) {
                    btn.classList.add('active');
                    btn.title = 'Disable';
                    btn.closest('.key-row').dataset.enabled = 'true';
                } else {
                    btn.classList.remove('active');
                    btn.title = 'Enable';
                    btn.closest('.key-row').dataset.enabled = 'false';
                }
            } catch (err) {
                showToast('error', 'Failed to toggle key.');
            }
        });
    });

    // ── Secret field toggle ──────────────────────────────────────────────────
    document.querySelectorAll('.secret-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const field = btn.closest('.secret-field').querySelector('input');
            const eyeOn = btn.querySelector('.eye-icon');
            const eyeOff = btn.querySelector('.eye-off-icon');
            if (field.type === 'password') {
                field.type = 'text';
                eyeOn.hidden = true;
                eyeOff.hidden = false;
            } else {
                field.type = 'password';
                eyeOn.hidden = false;
                eyeOff.hidden = true;
            }
        });
    });

    // ── Refresh Usage (SSE — one key at a time) ────────────────────────────────
    const refreshBtn = document.getElementById('refreshUsageBtn');

    function updateUsageCell(entry) {
        const cell = document.querySelector(`.usage-cell[data-key-id="${entry.id}"]`);
        if (!cell) return;

        const barFill = cell.querySelector('.usage-bar-fill');
        const statusEl = cell.querySelector('.usage-status');

        if (entry.provider === 'groq' && entry.limit_tokens) {
            const isLimited = entry.status === 'rate_limited';
            const isTPD = entry.limit_tokens >= 50000; // TPD = 100K, TPM = 12K

            // Determine what to show on the bar: daily TPD if available, else TPM
            const dailyUsed = entry.daily_tokens_used || 0;
            const dailyLimit = entry.daily_tokens_limit || 100000;
            const hasDailyData = !isLimited && entry.daily_tokens_used != null;

            // Bar always shows daily TPD usage (the metric that matters)
            const barUsed = isTPD ? (entry.limit_tokens - (entry.remaining_tokens || 0)) : dailyUsed;
            const barLimit = isTPD ? entry.limit_tokens : dailyLimit;
            const usedPct = Math.round((barUsed / barLimit) * 100);

            if (barFill) {
                barFill.style.width = usedPct + '%';
                barFill.className = 'usage-bar-fill ' + (usedPct > 90 ? 'danger' : usedPct > 70 ? 'warning' : 'groq');
            }
            if (statusEl) {
                let html = '';
                if (isLimited) {
                    // Key hit daily 429 — show TPD data
                    const remainK = Math.round((entry.remaining_tokens || 0) / 1000);
                    const limitK = Math.round(entry.limit_tokens / 1000);
                    html = `<span class="status-error">${remainK}K</span> / ${limitK}K TPD exhausted`;
                    if (entry.reset_tokens) {
                        html += ` <span class="status-reset">resets in ${entry.reset_tokens}</span>`;
                    }
                } else if (hasDailyData) {
                    // Active key with tracked daily usage
                    const dailyUsedK = Math.round(dailyUsed / 1000);
                    const dailyLimitK = Math.round(dailyLimit / 1000);
                    html = `<span class="status-ok">${dailyUsedK}K</span> / ${dailyLimitK}K TPD used today (${usedPct}%)`;
                } else {
                    // No daily data yet — show TPM from headers
                    const remainK = Math.round((entry.remaining_tokens || 0) / 1000);
                    const limitK = Math.round(entry.limit_tokens / 1000);
                    html = `<span class="status-ok">${remainK}K</span> / ${limitK}K TPM remaining`;
                }
                statusEl.innerHTML = html;
            }
        } else if (entry.status === 'active') {
            if (barFill) barFill.style.width = '10%';
            if (statusEl) statusEl.innerHTML = '<span class="status-ok">Active</span>';
        } else if (entry.status === 'rate_limited') {
            if (barFill) { barFill.style.width = '100%'; barFill.className = 'usage-bar-fill danger'; }
            if (statusEl) {
                let msg = '<span class="status-error">Rate limited</span>';
                if (entry.reset_tokens) msg += ` <span class="status-reset">resets in ${entry.reset_tokens}</span>`;
                statusEl.innerHTML = msg;
            }
        } else if (entry.status === 'invalid') {
            if (barFill) { barFill.style.width = '100%'; barFill.className = 'usage-bar-fill danger'; }
            if (statusEl) statusEl.innerHTML = '<span class="status-error">Invalid key</span>';
        } else {
            if (barFill) barFill.style.width = '0%';
            if (statusEl) statusEl.innerHTML = '<span class="status-error">Error</span>';
        }
    }

    function streamUsageCheck() {
        if (refreshBtn) {
            refreshBtn.classList.add('refresh-spinning');
            refreshBtn.disabled = true;
        }

        // Reset all status texts to loading
        document.querySelectorAll('.usage-status').forEach(el => {
            el.innerHTML = '<span class="status-loading">Checking...</span>';
        });
        document.querySelectorAll('.usage-bar-fill').forEach(el => {
            el.style.width = '0%';
        });

        const source = new EventSource('/api-keys/usage');

        source.onmessage = function (e) {
            const entry = JSON.parse(e.data);
            if (entry.done) {
                source.close();
                if (refreshBtn) {
                    refreshBtn.classList.remove('refresh-spinning');
                    refreshBtn.disabled = false;
                }
                return;
            }
            updateUsageCell(entry);
        };

        source.onerror = function () {
            source.close();
            if (refreshBtn) {
                refreshBtn.classList.remove('refresh-spinning');
                refreshBtn.disabled = false;
            }
            showToast('error', 'Usage check connection lost.');
        };
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', streamUsageCheck);
    }

    // Auto-check on page load
    if (document.querySelectorAll('.key-row').length > 0) {
        streamUsageCheck();
    }

    // ── Search & Filter ──────────────────────────────────────────────────────
    const searchInput = document.getElementById('keySearchInput');
    const rows = document.querySelectorAll('.key-row');
    const emptyMsg = document.querySelector('.search-empty');
    let activeFilter = 'all';

    function applyFilters() {
        const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
        let visible = 0;
        rows.forEach(row => {
            const label = row.dataset.searchLabel || '';
            const key = row.dataset.searchKey || '';
            const provider = row.dataset.provider || '';
            const enabled = row.dataset.enabled || 'true';

            let matchFilter = activeFilter === 'all' ||
                              activeFilter === provider ||
                              (activeFilter === 'enabled' && enabled === 'true');
            let matchSearch = !query || label.includes(query) || key.includes(query) || provider.includes(query);

            if (matchFilter && matchSearch) {
                row.classList.remove('is-hidden');
                visible++;
            } else {
                row.classList.add('is-hidden');
            }
        });
        if (emptyMsg) emptyMsg.hidden = visible > 0;
    }

    if (searchInput) searchInput.addEventListener('input', applyFilters);

    document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            activeFilter = chip.dataset.filter;
            applyFilters();
        });
    });

    // Keyboard shortcut: / to focus search
    document.addEventListener('keydown', e => {
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
            e.preventDefault();
            if (searchInput) searchInput.focus();
        }
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-backdrop.is-open').forEach(m => closeModal(m.id));
            if (confirmDialog) confirmDialog.classList.remove('is-open');
        }
    });

})();
