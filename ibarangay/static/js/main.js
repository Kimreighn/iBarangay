// Background polling and notification sounds

function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.innerText = message;
    container.appendChild(t);
    setTimeout(() => {
        t.style.opacity = '0';
        setTimeout(() => t.remove(), 500);
    }, 5000);
}

window.toast = toast;

function canShowDesktopPopup() {
    if (!('Notification' in window)) return false;
    if (Notification.permission !== 'granted') return false;
    return document.hidden || !document.hasFocus();
}

function notifyUser(eventKey, title, message, toastType = 'info') {
    toast(message, toastType);
    if (canShowDesktopPopup() && typeof window.showDesktopNotification === 'function') {
        window.showDesktopNotification(eventKey, title, message, {
            loopSound: true,
            requireInteraction: true,
            timeoutMs: 60000,
            tag: `ibarangay-${eventKey}`
        });
    } else if (typeof window.playNotificationSound === 'function') {
        window.playNotificationSound(eventKey);
    }
}

function fetchJsonSafely(url) {
    return fetch(url)
        .then(res => res.ok ? res.json() : null)
        .catch(() => null);
}

function ensurePollState() {
    if (!window.NOTIFICATION_POLL_STATE || typeof window.NOTIFICATION_POLL_STATE !== 'object') {
        window.NOTIFICATION_POLL_STATE = {};
    }
    return window.NOTIFICATION_POLL_STATE;
}

function hasSeenNotificationKey(key) {
    const state = ensurePollState();
    return Object.prototype.hasOwnProperty.call(state, key);
}

function getSeenNotificationId(key) {
    const state = ensurePollState();
    return Number(state[key] || 0);
}

function setSeenNotificationId(key, value) {
    const state = ensurePollState();
    state[key] = Number(value || 0);
    if (typeof saveNotificationState === 'function') {
        saveNotificationState(state);
    }
}

async function pollEmergencyAlerts() {
    if (!['bio', 'official'].includes(window.USER_ROLE)) return;
    const data = await fetchJsonSafely('/api/emergency');
    if (!Array.isArray(data)) return;

    const latestId = data.reduce((maxId, item) => Math.max(maxId, Number(item.id) || 0), 0);
    const storageKey = 'last_emergency_seen_id';

    if (!hasSeenNotificationKey(storageKey)) {
        setSeenNotificationId(storageKey, latestId);
        return;
    }

    const previousId = getSeenNotificationId(storageKey);
    const fresh = data.filter(item => Number(item.id) > previousId);

    if (fresh.length > 0) {
        const incidentCount = fresh.filter(item => item.type === 'accident').length;
        const healthCount = fresh.filter(item => item.type === 'health').length;
        const parts = [];
        if (incidentCount) parts.push(`${incidentCount} incident${incidentCount === 1 ? '' : 's'}`);
        if (healthCount) parts.push(`${healthCount} health report${healthCount === 1 ? '' : 's'}`);
        notifyUser('emergency', 'iBarangay Emergency Alert', `New ${parts.join(' and ')} received. Check the report tab now.`, 'emergency');
    }

    if (latestId > previousId) {
        setSeenNotificationId(storageKey, latestId);
    }
}

async function pollAnnouncementAlerts() {
    if (!['resident', 'official'].includes(window.USER_ROLE)) return;
    const data = await fetchJsonSafely('/api/announcements');
    if (!Array.isArray(data)) return;

    const latestId = data.reduce((maxId, item) => Math.max(maxId, Number(item.id) || 0), 0);
    const storageKey = 'last_announcement_seen_id';

    if (!hasSeenNotificationKey(storageKey)) {
        setSeenNotificationId(storageKey, latestId);
        return;
    }

    const previousId = getSeenNotificationId(storageKey);
    const fresh = data.filter(item => Number(item.id) > previousId);

    if (fresh.length > 0) {
        notifyUser(
            'announcement',
            'iBarangay Announcement',
            `${fresh.length === 1 ? 'New barangay announcement received.' : `${fresh.length} new barangay announcements received.`}`
        );
    }

    if (latestId > previousId) {
        setSeenNotificationId(storageKey, latestId);
    }
}

async function pollAcknowledgedReports() {
    if (window.USER_ROLE !== 'resident') return;
    const data = await fetchJsonSafely('/api/history');
    if (!Array.isArray(data)) return;

    const matching = data.filter(item => String(item.action || '').toLowerCase().includes('report was acknowledged'));
    const latestId = matching.reduce((maxId, item) => Math.max(maxId, Number(item.id) || 0), 0);
    const storageKey = 'last_acknowledgment_seen_id';

    if (!hasSeenNotificationKey(storageKey)) {
        setSeenNotificationId(storageKey, latestId);
        return;
    }

    const previousId = getSeenNotificationId(storageKey);
    const fresh = matching.filter(item => Number(item.id) > previousId);

    if (fresh.length > 0) {
        notifyUser(
            'acknowledgment',
            'iBarangay Report Update',
            `${fresh.length === 1 ? 'Officials acknowledged one of your reports.' : `${fresh.length} of your reports were acknowledged.`}`
        );
    }

    if (latestId > previousId) {
        setSeenNotificationId(storageKey, latestId);
    }
}

async function pollNewBioPosts() {
    if (!['resident', 'official', 'bio'].includes(window.USER_ROLE)) return;
    const data = await fetchJsonSafely('/api/posts');
    if (!Array.isArray(data)) return;

    const latestId = data.reduce((maxId, item) => Math.max(maxId, Number(item.id) || 0), 0);
    const storageKey = 'last_post_seen_id';

    if (!hasSeenNotificationKey(storageKey)) {
        setSeenNotificationId(storageKey, latestId);
        return;
    }

    const previousId = getSeenNotificationId(storageKey);
    const fresh = data.filter(item =>
        Number(item.id) > previousId &&
        String(item.author_id || '') !== String(window.USER_ID || '')
    );

    if (fresh.length > 0) {
        const latestPost = fresh[0];
        notifyUser(
            'post',
            'iBarangay New BIO Post',
            `New BIO post from ${latestPost.author_name || 'the barangay feed'}.`
        );
    }

    if (latestId > previousId) {
        setSeenNotificationId(storageKey, latestId);
    }
}

function startNotificationPolling() {
    pollEmergencyAlerts();
    pollAnnouncementAlerts();
    pollAcknowledgedReports();
    pollNewBioPosts();

    if (['bio', 'official'].includes(window.USER_ROLE)) {
        setInterval(pollEmergencyAlerts, 15000);
    }

    if (['resident', 'official'].includes(window.USER_ROLE)) {
        setInterval(pollAnnouncementAlerts, 30000);
    }

    if (window.USER_ROLE === 'resident') {
        setInterval(pollAcknowledgedReports, 20000);
    }

    if (['resident', 'official', 'bio'].includes(window.USER_ROLE)) {
        setInterval(pollNewBioPosts, 25000);
    }
}

if (window.USER_ROLE) {
    startNotificationPolling();
}

function toggleMobileMenu() {
    const m = document.getElementById('navMenu');
    if (m) m.classList.toggle('show');
}

function formatAiLabel(value) {
    return String(value ?? 'Unknown')
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase());
}

function buildAiTypeCountChips(typeCounts) {
    const entries = Object.entries(typeCounts || {});
    if (!entries.length) {
        return '<div class="ai-empty-state">No report-type trends are available yet.</div>';
    }

    return `
        <div class="ai-chip-row">
            ${entries.map(([label, count]) => `
                <span class="ai-chip">${escapeHtml(formatAiLabel(label))}: ${escapeHtml(count)}</span>
            `).join('')}
        </div>
    `;
}

function buildAiRepeatedPuroks(repeatedPuroks) {
    if (!Array.isArray(repeatedPuroks) || repeatedPuroks.length === 0) {
        return '<div class="ai-empty-state">No recurring purok hotspot has crossed the alert threshold yet.</div>';
    }

    return `
        <div class="ai-list">
            ${repeatedPuroks.slice(0, 4).map(item => `
                <div class="ai-list-row">
                    <strong>Purok ${escapeHtml(item.purok)}</strong>
                    <span class="ai-list-meta">${escapeHtml(item.count)} recurring record(s)</span>
                </div>
            `).join('')}
        </div>
    `;
}

function buildAiHealthRiskRows(profiles) {
    if (!Array.isArray(profiles) || profiles.length === 0) {
        return '<div class="ai-empty-state">No resident is currently above the monitoring threshold.</div>';
    }

    return `
        <div class="ai-list">
            ${profiles.slice(0, 5).map(profile => {
                const title = profile.full_name
                    ? escapeHtml(profile.full_name)
                    : `Purok ${escapeHtml(profile.purok || 'Unknown')} household`;
                const facts = [];
                if (profile.risk_level) facts.push(`${escapeHtml(formatAiLabel(profile.risk_level))} risk`);
                if (profile.risk_score !== undefined && profile.risk_score !== null) facts.push(`score ${escapeHtml(profile.risk_score)}`);
                if (profile.age !== undefined && profile.age !== null) facts.push(`age ${escapeHtml(profile.age)}`);
                if (profile.incident_count !== undefined && profile.incident_count !== null) facts.push(`${escapeHtml(profile.incident_count)} incident(s)`);
                if (profile.health_incident_count !== undefined && profile.health_incident_count !== null) facts.push(`${escapeHtml(profile.health_incident_count)} health report(s)`);
                const factorChips = Array.isArray(profile.factors) && profile.factors.length
                    ? `
                        <div class="ai-chip-row">
                            ${profile.factors.map(factor => `<span class="ai-chip muted">${escapeHtml(factor)}</span>`).join('')}
                        </div>
                    `
                    : '';

                return `
                    <div class="ai-list-row stacked">
                        <div>
                            <strong>${title}</strong>
                            <div class="ai-list-meta">${facts.join(' &middot; ') || 'Monitored by the AI risk model.'}</div>
                        </div>
                        ${factorChips}
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function buildAiRecommendations(recommendations) {
    if (!Array.isArray(recommendations) || recommendations.length === 0) {
        return '<div class="ai-empty-state">No recommendation has been generated yet.</div>';
    }

    return `
        <ul class="ai-analysis-list">
            ${recommendations.map(item => `<li>${escapeHtml(item)}</li>`).join('')}
        </ul>
    `;
}

function buildAiMapRiskSignals(signals) {
    if (!Array.isArray(signals) || signals.length === 0) {
        return '<div class="ai-empty-state">No map-based watch zone has been detected yet.</div>';
    }

    return `
        <div class="ai-list">
            ${signals.slice(0, 4).map(signal => `
                <div class="ai-list-row stacked">
                    <div>
                        <strong>${escapeHtml(signal.risk_label || 'Watch zone')}</strong>
                        <div class="ai-list-meta">
                            Purok ${escapeHtml(signal.purok || 'Unknown')} · ${escapeHtml(signal.count || 0)} recurring report(s) · ${escapeHtml(formatAiLabel(signal.risk_level || 'moderate'))}
                        </div>
                    </div>
                    <div class="ai-list-meta">${escapeHtml(signal.summary || 'The AI flagged this map zone for monitoring.')}</div>
                    ${signal.validation_note ? `<div class="ai-list-meta">${escapeHtml(signal.validation_note)}</div>` : ''}
                </div>
            `).join('')}
        </div>
    `;
}

function buildAiPredictiveAlerts(alerts) {
    if (!Array.isArray(alerts) || alerts.length === 0) {
        return '<div class="ai-empty-state">No predictive alert is available yet.</div>';
    }

    return `
        <ul class="ai-analysis-list">
            ${alerts.map(item => `<li>${escapeHtml(item)}</li>`).join('')}
        </ul>
    `;
}

window.hideAiCommunityAnalysis = function() {
    const insightBox = document.getElementById('ai-insight-box');
    const detailsBox = document.getElementById('ai-analysis-details');

    if (insightBox) {
        insightBox.style.display = 'none';
        insightBox.innerText = '';
    }

    if (detailsBox) {
        detailsBox.style.display = 'none';
        detailsBox.innerHTML = '';
    }
};

window.renderAiCommunityAnalysis = function(data) {
    const insightBox = document.getElementById('ai-insight-box');
    const detailsBox = document.getElementById('ai-analysis-details');
    const patterns = data?.incident_patterns || {};
    const healthRisks = Array.isArray(data?.health_risks) ? data.health_risks : [];
    const mapRiskSignals = Array.isArray(data?.map_risk_signals) ? data.map_risk_signals : [];
    const predictiveAlerts = Array.isArray(data?.predictive_alerts) ? data.predictive_alerts : [];
    const riskOverview = data?.risk_overview || {};
    const recommendations = Array.isArray(data?.recommendations) ? data.recommendations : [];
    const metadata = data?.analysis_metadata || {};
    const hotspots = Array.isArray(data?.hotspots) ? data.hotspots : [];
    const barangayProfile = data?.barangay_profile || {};

    if (insightBox) {
        insightBox.innerText = data?.insight || 'AI analysis is available.';
        insightBox.style.display = 'block';
    }

    if (!detailsBox) {
        return;
    }

    const metrics = [
        { label: 'Records Reviewed', value: Number(patterns.total_records || 0) },
        { label: 'Hotspots', value: hotspots.length },
        { label: 'Map Watch Zones', value: mapRiskSignals.length },
        { label: 'Flagged Residents', value: Number(riskOverview.flagged_residents || 0) },
        { label: 'High / Critical', value: Number(riskOverview.high_or_critical || 0) },
    ];

    detailsBox.innerHTML = `
        <div class="ai-analysis-header">
            <div>
                <small class="ai-kicker">${escapeHtml(metadata.component || 'AI analysis')}</small>
                <h4>Incident Pattern and Health Risk Findings</h4>
                <p class="text-muted">Scope: ${escapeHtml(formatAiLabel(metadata.analysis_scope || 'all'))} · Barangay: ${escapeHtml(metadata.barangay_name || barangayProfile.barangay_name || 'Current scope')}</p>
                <p class="text-muted">Residents reviewed: ${escapeHtml(barangayProfile.resident_count || 0)} · Mapped households: ${escapeHtml(barangayProfile.mapped_households || 0)} · Analysis run: ${escapeHtml(metadata.analysis_variant || 1)}</p>
            </div>
        </div>
        <div class="ai-metric-grid">
            ${metrics.map(metric => `
                <div class="ai-metric-card">
                    <span class="ai-metric-label">${escapeHtml(metric.label)}</span>
                    <strong class="ai-metric-value">${escapeHtml(metric.value)}</strong>
                </div>
            `).join('')}
        </div>
        <div class="ai-analysis-grid">
            <article class="ai-analysis-card">
                <h5>Incident Patterns</h5>
                <p>${escapeHtml(data?.incident_summary || patterns.summary || 'No incident summary available.')}</p>
                <div class="ai-section-label">Report Type Mix</div>
                ${buildAiTypeCountChips(patterns.type_counts)}
                <div class="ai-section-label">Repeated Puroks</div>
                ${buildAiRepeatedPuroks(patterns.repeated_puroks)}
            </article>
            <article class="ai-analysis-card">
                <h5>Potential Health Risks</h5>
                <p>${escapeHtml(data?.health_summary || 'No health-risk summary available.')}</p>
                ${buildAiHealthRiskRows(healthRisks)}
            </article>
            <article class="ai-analysis-card">
                <h5>Map-Based Risks</h5>
                <p>${escapeHtml(data?.map_risk_summary || 'No map-based risk summary available.')}</p>
                ${buildAiMapRiskSignals(mapRiskSignals)}
            </article>
            <article class="ai-analysis-card">
                <h5>Predictive Alerts</h5>
                ${buildAiPredictiveAlerts(predictiveAlerts)}
            </article>
        </div>
        <article class="ai-analysis-card">
            <h5>Recommended Actions</h5>
            ${buildAiRecommendations(recommendations)}
            ${metadata.field_validation_note ? `<div class="ai-section-label">Field Note</div><div class="ai-empty-state">${escapeHtml(metadata.field_validation_note)}</div>` : ''}
        </article>
    `;
    detailsBox.style.display = 'block';
};

window.WELFARE_CACHE = [];
window.WELFARE_SUMMARY = null;
window.WELFARE_STATUS_OPTIONS = ['planned', 'approved', 'released', 'cancelled'];
window.WELFARE_USER_CAN_EDIT = ['bio', 'official', 'superadmin'].includes(window.USER_ROLE || '');
window.WELFARE_RESIDENT_OPTIONS = [];
window.WELFARE_SELECTED_RESIDENT_IDS = [];

function formatWelfareStatus(status) {
    return String(status || 'planned')
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase());
}

function welfareMoney(value) {
    return `PHP ${Number(value || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;
}

function welfareDate(value) {
    if (!value) return 'Not scheduled';
    if (typeof window.formatPhilippineDate === 'function') {
        return window.formatPhilippineDate(value);
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleDateString('en-PH', { timeZone: 'Asia/Manila' });
}

function welfareStatusBadge(status) {
    const palette = {
        planned: ['rgba(59, 130, 246, 0.14)', '#60a5fa'],
        approved: ['rgba(245, 158, 11, 0.14)', '#fbbf24'],
        released: ['rgba(34, 197, 94, 0.14)', '#4ade80'],
        cancelled: ['rgba(239, 68, 68, 0.14)', '#f87171']
    };
    const selected = palette[status] || ['rgba(148, 163, 184, 0.16)', '#cbd5f5'];
    return `<span style="padding:5px 10px; border-radius:999px; background:${selected[0]}; color:${selected[1]}; font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:0.04em;">${escapeHtml(formatWelfareStatus(status))}</span>`;
}

function setWelfareStatusOptions(statuses) {
    const select = document.getElementById('welfare-filter-status');
    if (!select) return;
    const nextStatuses = Array.isArray(statuses) && statuses.length ? statuses : window.WELFARE_STATUS_OPTIONS;
    const current = select.value || '';
    select.innerHTML = '<option value="">All statuses</option>' + nextStatuses.map(status => (
        `<option value="${escapeHtml(status)}">${escapeHtml(formatWelfareStatus(status))}</option>`
    )).join('');
    if (current && nextStatuses.includes(current)) {
        select.value = current;
    }
}

window.populateWelfareResidentOptions = async function(force = false) {
    const optionsBox = document.getElementById('welfare-resident-options');
    if (!optionsBox) return;

    let residents = Array.isArray(window.MEMBERS_CACHE)
        ? window.MEMBERS_CACHE.filter(member => member.role === 'resident')
        : [];

    if (force || residents.length === 0) {
        try {
            const res = await fetch('/api/members');
            residents = res.ok
                ? (await res.json()).filter(member => member.role === 'resident')
                : [];
        } catch (error) {
            residents = [];
        }
    }

    residents.sort((left, right) => String(left.full_name || '').localeCompare(String(right.full_name || '')));
    window.WELFARE_RESIDENT_OPTIONS = residents;
    window.WELFARE_SELECTED_RESIDENT_IDS = window.WELFARE_SELECTED_RESIDENT_IDS.filter(selectedId =>
        residents.some(member => Number(member.id) === Number(selectedId))
    );
    window.renderWelfareResidentPicker();
};

window.getSelectedWelfareResidents = function() {
    const selectedIds = Array.isArray(window.WELFARE_SELECTED_RESIDENT_IDS) ? window.WELFARE_SELECTED_RESIDENT_IDS : [];
    return selectedIds
        .map(selectedId => (window.WELFARE_RESIDENT_OPTIONS || []).find(member => Number(member.id) === Number(selectedId)))
        .filter(Boolean);
};

window.renderWelfareResidentPicker = function() {
    const optionsBox = document.getElementById('welfare-resident-options');
    if (!optionsBox) return;

    const previewBox = document.getElementById('welfare-resident-preview');
    const countBox = document.getElementById('welfare-selected-count');
    const query = (document.getElementById('welfare-resident-search')?.value || '').trim().toLowerCase();
    const residents = Array.isArray(window.WELFARE_RESIDENT_OPTIONS) ? window.WELFARE_RESIDENT_OPTIONS : [];
    const selectedIds = Array.isArray(window.WELFARE_SELECTED_RESIDENT_IDS) ? window.WELFARE_SELECTED_RESIDENT_IDS : [];
    const filteredResidents = residents.filter(member => {
        if (!query) return true;
        const haystack = [
            member.full_name,
            member.username,
            member.position,
            member.purok ? `purok ${member.purok}` : ''
        ].map(value => String(value || '').toLowerCase()).join(' ');
        return haystack.includes(query);
    });

    optionsBox.innerHTML = filteredResidents.length
        ? filteredResidents.map(member => `
            <label class="welfare-beneficiary-card" style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 12px; border:1px solid var(--card-border); border-radius:12px; background:rgba(255,255,255,0.03); cursor:pointer;">
                <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                    <input class="welfare-beneficiary-checkbox" type="checkbox" ${selectedIds.includes(Number(member.id)) ? 'checked' : ''} onchange="window.toggleWelfareResidentSelection(${Number(member.id)}, this.checked)">
                    <div style="min-width:0;">
                        <strong style="display:block; font-size:14px;">${escapeHtml(member.full_name || 'Resident')}</strong>
                        <small class="text-muted">${escapeHtml(member.purok ? `Purok ${member.purok}` : 'Purok not set')}</small>
                    </div>
                </div>
                <span class="search-chip limited">${escapeHtml(member.class_type || 'N/A')}</span>
            </label>
        `).join('')
        : '<div class="text-muted" style="font-size:13px; padding:10px 0;">No resident matches the current search.</div>';

    const selectedResidents = window.getSelectedWelfareResidents();
    if (previewBox) {
        previewBox.innerHTML = selectedResidents.length
            ? selectedResidents.map(member => `
                <span class="mention-tag">
                    ${escapeHtml(member.full_name || 'Resident')}
                    <span style="cursor:pointer;" onclick="window.removeWelfareResidentSelection(${Number(member.id)})">&times;</span>
                </span>
            `).join('')
            : '<span class="text-muted" style="font-size:13px;">No beneficiaries selected yet.</span>';
    }

    if (countBox) {
        countBox.innerText = `${selectedResidents.length} selected`;
    }
};

window.toggleWelfareResidentSelection = function(residentId, isSelected) {
    const nextId = Number(residentId);
    const current = Array.isArray(window.WELFARE_SELECTED_RESIDENT_IDS) ? [...window.WELFARE_SELECTED_RESIDENT_IDS] : [];
    const existing = current.includes(nextId);
    if (isSelected && !existing) current.push(nextId);
    if (!isSelected && existing) {
        window.WELFARE_SELECTED_RESIDENT_IDS = current.filter(id => id !== nextId);
    } else {
        window.WELFARE_SELECTED_RESIDENT_IDS = current;
    }
    window.renderWelfareResidentPicker();
};

window.removeWelfareResidentSelection = function(residentId) {
    const nextId = Number(residentId);
    window.WELFARE_SELECTED_RESIDENT_IDS = (window.WELFARE_SELECTED_RESIDENT_IDS || []).filter(id => Number(id) !== nextId);
    window.renderWelfareResidentPicker();
};

window.clearWelfareResidentSelection = function() {
    window.WELFARE_SELECTED_RESIDENT_IDS = [];
    const search = document.getElementById('welfare-resident-search');
    if (search) search.value = '';
    window.renderWelfareResidentPicker();
};

window.selectAllVisibleWelfareResidents = function() {
    const query = (document.getElementById('welfare-resident-search')?.value || '').trim().toLowerCase();
    const residents = Array.isArray(window.WELFARE_RESIDENT_OPTIONS) ? window.WELFARE_RESIDENT_OPTIONS : [];
    const visibleResidents = residents.filter(member => {
        if (!query) return true;
        const haystack = [
            member.full_name,
            member.username,
            member.position,
            member.purok ? `purok ${member.purok}` : ''
        ].map(value => String(value || '').toLowerCase()).join(' ');
        return haystack.includes(query);
    });
    window.WELFARE_SELECTED_RESIDENT_IDS = [...new Set([
        ...(window.WELFARE_SELECTED_RESIDENT_IDS || []).map(id => Number(id)),
        ...visibleResidents.map(member => Number(member.id))
    ])];
    window.renderWelfareResidentPicker();
};

window.setWelfareSelectedResidents = function(residentIds) {
    window.WELFARE_SELECTED_RESIDENT_IDS = Array.isArray(residentIds)
        ? [...new Set(residentIds.map(id => Number(id)).filter(id => !Number.isNaN(id)))]
        : [];
    window.renderWelfareResidentPicker();
};

window.renderWelfareSummary = function() {
    const box = document.getElementById('welfare-summary-box');
    if (!box) return;

    const summary = window.WELFARE_SUMMARY || {};
    const metrics = [
        { label: 'Beneficiaries', value: Number(summary.beneficiary_count || 0), accent: 'var(--primary)' },
        { label: 'Released Records', value: Number(summary.released_records || 0), accent: '#4ade80' },
        { label: 'Pending Records', value: Number(summary.pending_records || 0), accent: 'var(--warning)' },
        { label: 'Released Amount', value: welfareMoney(summary.released_total || 0), accent: 'var(--secondary)' }
    ];

    const typeRows = Array.isArray(summary.type_breakdown) ? summary.type_breakdown : [];
    const latestLabel = summary.latest_released_date ? welfareDate(summary.latest_released_date) : 'No released entry yet';

    box.innerHTML = `
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px;">
            ${metrics.map(metric => `
                <div style="padding:14px; border-radius:14px; background:rgba(255,255,255,0.04); border:1px solid var(--card-border);">
                    <small style="display:block; color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:0.05em;">${escapeHtml(metric.label)}</small>
                    <strong style="display:block; font-size:22px; margin-top:6px; color:${metric.accent};">${escapeHtml(metric.value)}</strong>
                </div>
            `).join('')}
        </div>
        <div style="margin-top:14px; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;">
            <small class="text-muted">Scheduled amount: ${escapeHtml(welfareMoney(summary.scheduled_total || 0))}</small>
            <small class="text-muted">Latest released date: ${escapeHtml(latestLabel)}</small>
        </div>
        <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
            ${typeRows.length
                ? typeRows.map(row => `<span class="search-chip">${escapeHtml(row.assistance_type)} • ${escapeHtml(welfareMoney(row.released_amount || 0))}</span>`).join('')
                : '<span class="text-muted" style="font-size:13px;">No assistance type breakdown yet.</span>'}
        </div>
    `;
};

window.renderWelfareRecords = function() {
    const box = document.getElementById('welfare-records-box');
    if (!box) return;

    const statusFilter = document.getElementById('welfare-filter-status')?.value || '';
    const localQuery = (document.getElementById('welfare-search')?.value || '').trim().toLowerCase();
    const globalQuery = (window.NAV_SEARCH_QUERY || '').trim().toLowerCase();

    let records = Array.isArray(window.WELFARE_CACHE) ? [...window.WELFARE_CACHE] : [];
    if (statusFilter) {
        records = records.filter(record => String(record.status || '') === statusFilter);
    }

    const activeQueries = [localQuery, globalQuery].filter(Boolean);
    if (activeQueries.length) {
        records = records.filter(record => {
            const haystack = [
                record.reference_code,
                record.resident_name,
                record.assistance_type,
                record.program_name,
                record.notes,
                record.source_funds
            ].map(value => String(value || '').toLowerCase()).join(' ');
            return activeQueries.every(query => haystack.includes(query));
        });
    }

    if (!records.length) {
        box.innerHTML = '<p class="text-muted">No welfare records match the current filters.</p>';
        return;
    }

    box.innerHTML = records.map(record => {
        const quantityLabel = Number(record.quantity || 0) > 0
            ? `${Number(record.quantity).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${record.unit || 'unit(s)'}`
            : 'Not specified';
        const chips = [
            record.program_name || null,
            record.purok ? `Purok ${record.purok}` : null,
            record.resident_class_type ? `Class ${record.resident_class_type}` : null,
            record.source_funds || null
        ].filter(Boolean);

        return `
            <div style="padding:16px; border-radius:16px; border:1px solid var(--card-border); background:rgba(255,255,255,0.03); margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
                    <div>
                        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                            <strong style="font-size:16px;">${escapeHtml(record.assistance_type || 'Assistance')}</strong>
                            ${welfareStatusBadge(record.status)}
                        </div>
                        <div style="margin-top:6px; font-size:14px;">
                            <strong>${escapeHtml(record.resident_name || 'Resident')}</strong>
                            <span style="color:var(--text-muted);"> • ${escapeHtml(record.reference_code || 'No reference')}</span>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <strong style="display:block; font-size:18px; color:var(--secondary);">${escapeHtml(welfareMoney(record.amount || 0))}</strong>
                        <small class="text-muted">Release date: ${escapeHtml(welfareDate(record.distributed_on))}</small>
                    </div>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
                    ${chips.map(chip => `<span class="search-chip">${escapeHtml(chip)}</span>`).join('')}
                    <span class="search-chip limited">Qty: ${escapeHtml(quantityLabel)}</span>
                    ${record.created_by_name ? `<span class="search-chip limited">Encoded by ${escapeHtml(record.created_by_name)}</span>` : ''}
                </div>
                ${record.notes ? `<p style="margin:12px 0 0; font-size:14px; line-height:1.6; white-space:pre-wrap; color:rgba(255,255,255,0.88);">${escapeHtml(record.notes)}</p>` : ''}
                ${window.WELFARE_USER_CAN_EDIT && record.can_edit ? `
                    <div style="display:flex; justify-content:flex-end; margin-top:12px;">
                        <button class="btn btn-secondary" style="padding:6px 12px;" onclick="window.editWelfareRecord(${record.id})">Edit Record</button>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
};

window.resetWelfareForm = function() {
    const fields = ['welfare-record-id', 'welfare-type', 'welfare-program', 'welfare-amount', 'welfare-quantity', 'welfare-unit', 'welfare-source', 'welfare-reference', 'welfare-notes'];
    fields.forEach(id => {
        const element = document.getElementById(id);
        if (element) element.value = '';
    });

    const residentSearch = document.getElementById('welfare-resident-search');
    if (residentSearch) residentSearch.value = '';
    window.WELFARE_SELECTED_RESIDENT_IDS = [];
    window.renderWelfareResidentPicker();

    const status = document.getElementById('welfare-status');
    if (status) status.value = 'planned';

    const welfareDateField = document.getElementById('welfare-date');
    if (welfareDateField) {
        welfareDateField.value = typeof window.getPhilippineTodayInputValue === 'function'
            ? window.getPhilippineTodayInputValue()
            : new Date().toISOString().split('T')[0];
    }
};

window.editWelfareRecord = function(recordId) {
    if (!window.WELFARE_USER_CAN_EDIT) return;
    const record = (window.WELFARE_CACHE || []).find(item => Number(item.id) === Number(recordId));
    if (!record) return;

    document.getElementById('welfare-record-id').value = record.id;
    window.setWelfareSelectedResidents([record.resident_id]);
    const residentSearch = document.getElementById('welfare-resident-search');
    if (residentSearch) residentSearch.value = '';
    document.getElementById('welfare-type').value = record.assistance_type || '';
    document.getElementById('welfare-program').value = record.program_name || '';
    document.getElementById('welfare-amount').value = record.amount ?? '';
    document.getElementById('welfare-quantity').value = record.quantity ?? '';
    document.getElementById('welfare-unit').value = record.unit || '';
    document.getElementById('welfare-status').value = record.status || 'planned';
    document.getElementById('welfare-date').value = record.distributed_on || '';
    document.getElementById('welfare-source').value = record.source_funds || '';
    document.getElementById('welfare-reference').value = record.reference_code || '';
    document.getElementById('welfare-notes').value = record.notes || '';

    document.getElementById('welfare-type')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

window.saveWelfareDistribution = async function() {
    if (!window.WELFARE_USER_CAN_EDIT) return;

    const residentIds = (window.WELFARE_SELECTED_RESIDENT_IDS || []).map(id => Number(id)).filter(id => !Number.isNaN(id));
    const assistanceType = (document.getElementById('welfare-type')?.value || '').trim();

    if (!residentIds.length || !assistanceType) {
        alert('Select at least one beneficiary and enter the assistance type first.');
        return;
    }

    const recordId = document.getElementById('welfare-record-id')?.value || '';
    if (recordId && residentIds.length !== 1) {
        alert('Editing a welfare record requires exactly one beneficiary to stay selected.');
        return;
    }

    const payload = {
        assistance_type: assistanceType,
        program_name: (document.getElementById('welfare-program')?.value || '').trim(),
        amount: document.getElementById('welfare-amount')?.value || 0,
        quantity: document.getElementById('welfare-quantity')?.value || 0,
        unit: (document.getElementById('welfare-unit')?.value || '').trim(),
        status: document.getElementById('welfare-status')?.value || 'planned',
        distributed_on: document.getElementById('welfare-date')?.value || '',
        source_funds: (document.getElementById('welfare-source')?.value || '').trim(),
        reference_code: (document.getElementById('welfare-reference')?.value || '').trim(),
        notes: (document.getElementById('welfare-notes')?.value || '').trim()
    };

    if (recordId) {
        payload.resident_id = residentIds[0];
    } else {
        payload.resident_ids = residentIds;
        if (residentIds.length === 1) payload.resident_id = residentIds[0];
    }

    const url = recordId ? `/api/welfare/distributions/${recordId}` : '/api/welfare/distributions';
    const method = recordId ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            alert(data.error || 'Unable to save the welfare record right now.');
            return;
        }

        const createdCount = Number(data.created_count || 0);
        if (recordId) {
            alert('Welfare record updated.');
        } else if (createdCount > 1) {
            alert(`Welfare records created for ${createdCount} beneficiaries.`);
        } else {
            alert('Welfare record created.');
        }
        window.resetWelfareForm();
        await window.loadWelfareModule(true);
    } catch (error) {
        alert('Unable to save the welfare record right now.');
    }
};

window.loadWelfareModule = async function(force = false) {
    const summaryBox = document.getElementById('welfare-summary-box');
    const recordsBox = document.getElementById('welfare-records-box');
    if (!summaryBox && !recordsBox) return;

    try {
        const res = await fetch('/api/welfare/distributions');
        const data = await res.json();
        if (!res.ok || !data.success) {
            const message = data.error || 'Unable to load welfare records right now.';
            if (summaryBox) summaryBox.innerHTML = `<p class="text-muted">${escapeHtml(message)}</p>`;
            if (recordsBox) recordsBox.innerHTML = '';
            return;
        }

        window.WELFARE_CACHE = Array.isArray(data.records) ? data.records : [];
        window.WELFARE_SUMMARY = data.summary || {};
        window.WELFARE_STATUS_OPTIONS = Array.isArray(data.available_statuses) && data.available_statuses.length
            ? data.available_statuses
            : window.WELFARE_STATUS_OPTIONS;

        setWelfareStatusOptions(window.WELFARE_STATUS_OPTIONS);
        window.renderWelfareSummary();
        if (window.WELFARE_USER_CAN_EDIT) {
            await window.populateWelfareResidentOptions(force);
        }
        window.renderWelfareRecords();
        if (window.WELFARE_USER_CAN_EDIT && !document.getElementById('welfare-record-id')?.value) {
            window.resetWelfareForm();
        }
    } catch (error) {
        if (summaryBox) summaryBox.innerHTML = '<p class="text-muted">Unable to load welfare records right now.</p>';
        if (recordsBox) recordsBox.innerHTML = '';
    }
};
