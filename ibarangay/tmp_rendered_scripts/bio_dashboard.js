
        (function() {
            try {
                const savedTheme = localStorage.getItem('ibarangay_theme_preference');
                document.documentElement.dataset.theme = savedTheme === 'light' ? 'light' : 'dark';
            } catch (error) {
                document.documentElement.dataset.theme = 'dark';
            }
        })();
    


    function togglePasswordVisibility(inputId, trigger) {
        const input = document.getElementById(inputId);
        if (!input || !trigger) return;

        const willShow = input.type === 'password';
        input.type = willShow ? 'text' : 'password';
        trigger.setAttribute('aria-label', willShow ? 'Password visible' : 'Password hidden');
        trigger.setAttribute('aria-pressed', willShow ? 'true' : 'false');

        const icon = trigger.querySelector('i');
        if (icon) {
            icon.className = willShow ? 'fa-regular fa-eye' : 'fa-regular fa-eye-slash';
        }
    }

    const bioTabState = {
        homeLoaded: false,
        membersLoaded: false,
        welfareLoaded: false,
        officialsLoaded: false,
        reportLoaded: false,
        historyLoaded: false,
        mapLoaded: false
    };
    let selectedAnnouncementTargets = [];
    let selectedAnnouncementPuroks = [];
    let availableAnnouncementPuroks = [];

    async function registerMember() {
        let picUrl = '';
        const picInput = document.getElementById('r-pic');
        if(picInput.files.length > 0) {
            const formData = new FormData();
            formData.append('file', picInput.files[0]);
            const upRes = await fetch('/api/upload_image', {method: 'POST', body: formData});
            const upData = await upRes.json();
            if(upData.success) picUrl = upData.url;
        }

        const body = {
            full_name: document.getElementById('r-name').value,
            username: document.getElementById('r-user').value,
            password: document.getElementById('r-pass').value,
            role: document.getElementById('r-role').value,
            position: document.getElementById('r-pos').value,
            birthdate: document.getElementById('r-bdate').value,
            birthplace: document.getElementById('r-bplace').value,
            purok: document.getElementById('r-purok').value,
            employment_status: document.getElementById('r-emp').value,
            mother_name: document.getElementById('r-mother').value,
            father_name: document.getElementById('r-father').value,
            family_size: document.getElementById('r-fsize').value,
            monthly_income: document.getElementById('r-income').value,
            lat: document.getElementById('r-lat').value,
            lng: document.getElementById('r-lng').value,
            pic_url: picUrl
        };
        const res = await fetch('/api/bio/member', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        const d = await res.json();
        if (d.success) {
            alert("Entry Created! Directory System Reset.");
            window.MENTION_CANDIDATES = null;
            loadMembers();
            ['r-name','r-user','r-pass','r-pos','r-bdate','r-bplace','r-purok','r-emp','r-mother','r-father','r-fsize','r-income','r-lat','r-lng','r-pic'].forEach(id => {
                const el = document.getElementById(id);
                if(el) { if (el.tagName === 'SELECT') el.selectedIndex = 0; else el.value = ''; }
            });
            document.getElementById('r-role').selectedIndex = 0;
            document.getElementById('r-pos').style.display = 'none';
            if(addPinMarker && addPinMap) addPinMap.removeLayer(addPinMarker);
        } else alert("Error: " + d.error);
    }

    async function broadcast() {
        const msg = document.getElementById('ann-msg').value;
        const editId = document.getElementById('ann-edit-id').value;
        const method = editId ? 'PUT' : 'POST';
        const url = editId ? `/api/announcements/${editId}` : '/api/announcements';
        const targetUsers = selectedAnnouncementTargets.map(target => ({ id: target.id, name: target.name }));
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: msg,
                target_puroks: targetUsers.length ? [] : selectedAnnouncementPuroks,
                target_users: targetUsers
            })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || 'Unable to save broadcast.');
            return;
        }
        alert(editId ? 'Broadcast updated!' : 'Broadcast sent!');
        resetAnnouncementForm();
        loadBioAnnouncements();
    }

    async function searchAnnouncementTargets(query) {
        const list = document.getElementById('ann-target-list');
        if(!query) { list.innerHTML = ''; list.style.display = 'none'; return; }
        const all = await loadMentionCandidates();
        const filtered = all.filter(u => u.full_name.toLowerCase().includes(query.toLowerCase())).slice(0, 6);
        list.style.display = filtered.length ? 'block' : 'none';
        list.innerHTML = filtered.map(u => `
            <div class="mention-item" onclick='addAnnouncementTarget(${JSON.stringify(u.id ?? null)}, ${JSON.stringify(u.full_name)})'>
                <img src="${u.pic_url || '/static/default-avatar.svg'}" style="width:30px; height:30px; border-radius:50%;">
                <span>${u.full_name}</span>
            </div>
        `).join('');
    }

    function addAnnouncementTarget(id, name) {
        if(mentionExists(selectedAnnouncementTargets, id, name)) return;
        selectedAnnouncementTargets.push({id, name});
        selectedAnnouncementPuroks = [];
        renderAnnouncementPuroks();
        renderAnnouncementTargets();
        document.getElementById('ann-target-input').value = '';
        document.getElementById('ann-target-list').innerHTML = '';
        document.getElementById('ann-target-list').style.display = 'none';
    }

    function removeAnnouncementTarget(index) {
        selectedAnnouncementTargets.splice(index, 1);
        renderAnnouncementTargets();
    }

    function renderAnnouncementTargets() {
        const container = document.getElementById('ann-target-preview-container');
        if (!container) return;
        container.innerHTML = selectedAnnouncementTargets.map((target, index) => `
            <div class="mention-tag">@${target.name} <span style="cursor:pointer" onclick="removeAnnouncementTarget(${index})">&times;</span></div>
        `).join('');
    }

    function resetAnnouncementForm() {
        document.getElementById('ann-edit-id').value = '';
        document.getElementById('ann-msg').value = '';
        document.getElementById('ann-target-input').value = '';
        document.getElementById('ann-target-list').innerHTML = '';
        document.getElementById('ann-target-list').style.display = 'none';
        document.getElementById('ann-submit-btn').innerText = 'Send Broadcast';
        selectedAnnouncementTargets = [];
        selectedAnnouncementPuroks = [];
        loadAnnouncementPurokOptions();
        renderAnnouncementPuroks();
        renderAnnouncementTargets();
    }

    async function loadAnnouncementPurokOptions(force = false) {
        if (!force && availableAnnouncementPuroks.length) return availableAnnouncementPuroks;
        const res = await fetch('/api/members');
        const members = await res.json();
        availableAnnouncementPuroks = [...new Set(
            members
                .map(member => parseInt(member.purok))
                .filter(value => Number.isInteger(value) && value > 0)
        )].sort((a, b) => a - b);
        if (!availableAnnouncementPuroks.length) availableAnnouncementPuroks = [1, 2, 3, 4, 5, 6, 7];
        renderAnnouncementPuroks();
        return availableAnnouncementPuroks;
    }

    function renderAnnouncementPuroks() {
        const box = document.getElementById('ann-purok-options');
        const allToggle = document.getElementById('ann-purok-all');
        if (!box || !allToggle) return;
        allToggle.checked = selectedAnnouncementTargets.length === 0 && selectedAnnouncementPuroks.length === 0;
        const disabled = selectedAnnouncementTargets.length > 0;
        box.innerHTML = availableAnnouncementPuroks.map(purok => `
            <label class="mention-tag announcement-purok-chip" style="cursor:${disabled ? 'not-allowed' : 'pointer'}; opacity:${disabled ? '0.45' : '1'};">
                <input type="checkbox" value="${purok}" ${selectedAnnouncementPuroks.includes(purok) ? 'checked' : ''} ${disabled ? 'disabled' : ''} onchange="toggleAnnouncementPurok(${purok}, this.checked)">
                Purok ${purok}
            </label>
        `).join('');
    }

    function toggleAllAnnouncementPuroks(checked) {
        if (selectedAnnouncementTargets.length) return;
        selectedAnnouncementPuroks = checked ? [] : selectedAnnouncementPuroks;
        renderAnnouncementPuroks();
    }

    function toggleAnnouncementPurok(purok, checked) {
        if (selectedAnnouncementTargets.length) return;
        if (checked && !selectedAnnouncementPuroks.includes(purok)) selectedAnnouncementPuroks.push(purok);
        if (!checked) selectedAnnouncementPuroks = selectedAnnouncementPuroks.filter(item => item !== purok);
        selectedAnnouncementPuroks.sort((a, b) => a - b);
        renderAnnouncementPuroks();
    }

    async function loadBioAnnouncements() {
        const res = await fetch('/api/announcements');
        const data = await res.json();
        const box = document.getElementById('bio-announcements-list');
        if (!box) return;
        box.innerHTML = data.map(announcement => {
            const targetNames = Array.isArray(announcement.target_names) && announcement.target_names.length
                ? announcement.target_names.map(name => `@${escapeHtml(name)}`).join(', ')
                : 'All members';
            const puroks = Array.isArray(announcement.target_puroks) && announcement.target_puroks.length
                ? announcement.target_puroks.map(purok => `Purok ${escapeHtml(purok)}`).join(', ')
                : (announcement.purok ? `Purok ${escapeHtml(announcement.purok)}` : 'All puroks');
            return `<div style="border:1px solid var(--card-border); border-radius:12px; padding:12px; margin-bottom:10px; background:rgba(255,255,255,0.03);">
                <p style="margin:0 0 8px; white-space:pre-wrap;">${escapeHtml(announcement.message)}</p>
                <small class="text-muted">${formatPhilippineDateTime(announcement.date)} | ${puroks} | ${targetNames}</small>
                <div style="display:flex; gap:8px; margin-top:10px;">
                    <button class="btn btn-secondary btn-compact announcement-action-btn" style="padding:5px 10px; font-size:12px;" onclick='editAnnouncement(${JSON.stringify(announcement)})'>Edit</button>
                    <button class="btn btn-danger btn-compact announcement-action-btn" style="padding:5px 10px; font-size:12px;" onclick="deleteAnnouncement(${announcement.id})">Delete</button>
                </div>
            </div>`;
        }).join('') || '<p class="text-muted">No broadcasts yet.</p>';
    }

    function editAnnouncement(announcement) {
        document.getElementById('ann-edit-id').value = announcement.id;
        document.getElementById('ann-msg').value = announcement.message || '';
        selectedAnnouncementTargets = (announcement.target_users || []).map(target => ({ id: target.id, name: target.name }));
        selectedAnnouncementPuroks = selectedAnnouncementTargets.length ? [] : (announcement.target_puroks || (announcement.purok ? [announcement.purok] : [])).map(value => parseInt(value)).filter(value => Number.isInteger(value));
        document.getElementById('ann-submit-btn').innerText = 'Update Broadcast';
        renderAnnouncementPuroks();
        renderAnnouncementTargets();
        document.getElementById('ann-msg').scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    async function deleteAnnouncement(id) {
        if (!confirm('Delete this broadcast announcement?')) return;
        const res = await fetch(`/api/announcements/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || 'Unable to delete broadcast.');
            return;
        }
        loadBioAnnouncements();
    }

    async function postEvent() {
        const body = {
            title: document.getElementById('ev-title').value,
            date: document.getElementById('ev-date').value,
            type: document.getElementById('ev-type').value,
            description: document.getElementById('ev-desc').value
        };
        await fetch('/api/events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        alert('Event/Achievement published.');
        document.getElementById('ev-title').value = '';
    }

    async function uploadFinance() {
        const body = {
            month: parseInt(document.getElementById('f-month').value),
            year: parseInt(document.getElementById('f-year').value),
            total_funds: parseFloat(document.getElementById('f-total').value),
            relief_distribution: parseFloat(document.getElementById('f-relief').value),
            project_expenses: parseFloat(document.getElementById('f-project').value)
        };
        const res = await fetch('/api/finance', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const d = await res.json();
        document.getElementById('f-summary').innerText = d.summary;
    }

    async function calcRelief() {
        const budget = document.getElementById('r-budget').value;
        const res = await fetch('/api/relief/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ budget }) });
        const d = await res.json();
        let h = '<ul style="padding-left:20px; text-align:left;">';
        d.allocations.forEach(a => { h += `<li>Fam ID #${a.family_id}: ₱${a.allocated_amount}</li>`; });
        h += '</ul>';
        document.getElementById('r-results').innerHTML = h;
    }

    async function analyzeFeedback() {
        const res = await fetch('/api/ratings/analysis');
        const data = await res.json();
        document.getElementById('feedback-results').innerText = data.analysis;
    }

    async function loadBioRatingSchedule() {
        const schedule = window.loadRatingScheduleStatus
            ? await window.loadRatingScheduleStatus(true)
            : await (await fetch('/api/ratings/schedule')).json();

        const status = document.getElementById('rating-schedule-status');
        if (!status) return schedule;

        status.innerHTML = schedule.is_configured
            ? `<strong style="color:${schedule.is_open ? 'var(--success)' : 'var(--warning)'};">${schedule.is_open ? 'Ratings Open' : 'Ratings Closed'}</strong><br><span class="text-muted">${schedule.schedule_text}</span>`
            : `<strong style="color:var(--warning);">No schedule set</strong><br><span class="text-muted">${schedule.message}</span>`;

        if (schedule.is_configured) {
            const windows = schedule.windows || [];
            setRatingWindowInputs(1, windows[0]);
            setRatingWindowInputs(2, windows[1]);
        }

        return schedule;
    }

    function ratingDateInputValue(month, day) {
        if (!month || !day) return '';
        const year = typeof window.getPhilippineCurrentYear === 'function'
            ? window.getPhilippineCurrentYear()
            : new Date().getFullYear();
        return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    }

    function setRatingWindowInputs(windowNumber, windowData) {
        document.getElementById(`rating-window${windowNumber}-start`).value = windowData ? ratingDateInputValue(windowData.start_month, windowData.start_day) : '';
        document.getElementById(`rating-window${windowNumber}-end`).value = windowData ? ratingDateInputValue(windowData.end_month, windowData.end_day) : '';
    }

    async function saveRatingSchedule() {
        const windows = [];
        for (const windowNumber of [1, 2]) {
            const startDate = document.getElementById(`rating-window${windowNumber}-start`).value;
            const endDate = document.getElementById(`rating-window${windowNumber}-end`).value;
            if (startDate || endDate) {
                if (!startDate || !endDate) {
                    alert(`Complete both start and end dates for rating window ${windowNumber}.`);
                    return;
                }
                windows.push({ start_date: startDate, end_date: endDate });
            }
        }

        if (!windows.length) {
            alert('Add at least one rating window.');
            return;
        }

        const body = { windows };

        const res = await fetch('/api/ratings/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.error || 'Unable to save rating schedule.');
            return;
        }

        window.RATING_SCHEDULE_CACHE = data.schedule;
        await loadBioRatingSchedule();
        renderOfficialsList(document.getElementById('off-search')?.value || '');
        alert('Rating schedule updated.');
    }

    // --- Social Features ---
    let selectedFiles = []; // Store real File objects
    let selectedMediaPreviews = []; // Store preview URLs
    let selectedMentions = [];
    let selectedLocation = null;
    let editPostFiles = [];
    let editPostMedia = [];
    let editPostMentions = [];
    let editPostLocation = null;
    window.POSTS_CACHE = [];
    window.MENTION_CANDIDATES = null;
    const LOCATION_PICKER_STATE = {
        create: { currentSuggestion: null, searchToken: 0, geoToken: 0, debounce: null },
        edit: { currentSuggestion: null, searchToken: 0, geoToken: 0, debounce: null }
    };

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function getLocationPickerElements(mode = 'create') {
        if (mode === 'edit') {
            return {
                box: document.getElementById('ep-location-search-box'),
                input: document.getElementById('ep-location-input'),
                list: document.getElementById('ep-location-list')
            };
        }
        return {
            box: document.getElementById('location-search-box'),
            input: document.getElementById('location-input'),
            list: document.getElementById('location-list')
        };
    }

    function normalizeLocationChoice(location, source = 'search') {
        if (!location) return null;
        const displayName = String(location.display_name || location.label || '').trim();
        const rawParts = displayName.split(',').map(part => part.trim()).filter(Boolean);
        const uniqueParts = [];
        rawParts.forEach(part => {
            if (!uniqueParts.some(existing => existing.toLowerCase() === part.toLowerCase())) {
                uniqueParts.push(part);
            }
        });
        const label = String(location.label || uniqueParts.slice(0, 3).join(', ') || displayName || 'Pinned location').trim();
        if (!label) return null;
        return {
            label,
            display_name: displayName || label,
            source: location.source || source
        };
    }

    function dedupeLocationChoices(choices) {
        const seen = new Set();
        return choices
            .map(choice => normalizeLocationChoice(choice, choice && choice.source ? choice.source : 'search'))
            .filter(choice => {
                if (!choice) return false;
                const key = choice.label.toLowerCase();
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
    }

    function getSelectedLocationValue(mode = 'create') {
        return mode === 'edit' ? editPostLocation : selectedLocation;
    }

    function setSelectedLocationValue(mode, value) {
        if (mode === 'edit') {
            editPostLocation = value;
            renderEditLocationPreview();
        } else {
            selectedLocation = value;
            renderLocationPreview();
        }
    }

    function resetLocationSearchBox(mode = 'create', clearSuggestion = false) {
        const state = LOCATION_PICKER_STATE[mode];
        if (state.debounce) {
            clearTimeout(state.debounce);
            state.debounce = null;
        }
        if (clearSuggestion) {
            state.currentSuggestion = null;
        }
        const { box, input, list } = getLocationPickerElements(mode);
        if (box) box.style.display = 'none';
        if (input) input.value = '';
        if (list) list.innerHTML = '';
    }

    function renderLocationSearchResults(mode = 'create', choices = [], statusMessage = '') {
        const { list } = getLocationPickerElements(mode);
        if (!list) return;

        const normalizedChoices = dedupeLocationChoices(choices);
        const statusHtml = statusMessage ? `<div class="location-search-empty">${escapeHtml(statusMessage)}</div>` : '';

        if (!normalizedChoices.length) {
            list.innerHTML = statusHtml || '<div class="location-search-empty">Search another location or use your current place.</div>';
            return;
        }

        list.innerHTML = statusHtml + normalizedChoices.map(choice => {
            const encodedLabel = encodeURIComponent(choice.label);
            const badge = choice.source === 'current' ? 'Current' : (choice.source === 'selected' ? 'Selected' : 'Search');
            const subtitle = choice.source === 'current'
                ? (choice.display_name || 'Current location detected from this device.')
                : (choice.display_name || 'Tap to use this location.');

            return `
                <button type="button" class="mention-item location-result-item" onclick="selectPostLocation('${mode}', decodeURIComponent('${encodedLabel}'))">
                    <div class="location-search-copy">
                        <strong>${escapeHtml(choice.label)}</strong>
                        <small>${escapeHtml(subtitle)}</small>
                    </div>
                    <span class="location-search-badge ${choice.source}">${badge}</span>
                </button>
            `;
        }).join('');
    }

    async function fetchCurrentLocationChoice() {
        if (!navigator.geolocation) {
            return null;
        }

        return new Promise(resolve => {
            navigator.geolocation.getCurrentPosition(async (pos) => {
                try {
                    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&accept-language=en&lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`);
                    if (!res.ok) throw new Error('Location lookup failed');
                    const data = await res.json();
                    resolve(normalizeLocationChoice({
                        display_name: data.display_name,
                        label: undefined,
                        source: 'current'
                    }, 'current'));
                } catch (e) {
                    console.error('Geo error', e);
                    resolve(null);
                }
            }, () => resolve(null), { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
        });
    }

    async function loadCurrentLocationSuggestion(mode = 'create') {
        const state = LOCATION_PICKER_STATE[mode];
        const requestToken = ++state.geoToken;
        const selected = getSelectedLocationValue(mode);

        renderLocationSearchResults(
            mode,
            selected ? [{ label: selected, display_name: selected, source: 'selected' }] : [],
            'Checking your current location...'
        );

        const currentChoice = await fetchCurrentLocationChoice();
        if (requestToken !== state.geoToken) return;

        state.currentSuggestion = currentChoice;
        const baseChoices = [];
        if (selected) baseChoices.push({ label: selected, display_name: selected, source: 'selected' });
        if (currentChoice) baseChoices.push(currentChoice);

        renderLocationSearchResults(
            mode,
            baseChoices,
            currentChoice
                ? 'Your current place is suggested below. You can also search another location.'
                : 'Current location is unavailable right now. You can still search another place.'
        );
    }

    async function performLocationSearch(query, mode = 'create') {
        const state = LOCATION_PICKER_STATE[mode];
        const trimmedQuery = String(query || '').trim();
        const selected = getSelectedLocationValue(mode);
        const currentChoice = state.currentSuggestion;
        const baseChoices = [];

        if (selected) baseChoices.push({ label: selected, display_name: selected, source: 'selected' });
        if (currentChoice) baseChoices.push(currentChoice);

        if (!trimmedQuery) {
            renderLocationSearchResults(
                mode,
                baseChoices,
                currentChoice
                    ? 'Your current place is suggested below. Search another location if needed.'
                    : 'Type a location name to search another place.'
            );
            return;
        }

        const searchToken = ++state.searchToken;
        renderLocationSearchResults(mode, baseChoices, `Searching for "${trimmedQuery}"...`);

        try {
            const res = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&addressdetails=1&accept-language=en&q=${encodeURIComponent(trimmedQuery)}`);
            if (!res.ok) throw new Error('Location search failed');
            const data = await res.json();
            if (searchToken !== state.searchToken) return;

            const searchChoices = Array.isArray(data)
                ? data.map(item => normalizeLocationChoice({ display_name: item.display_name, label: undefined, source: 'search' }, 'search'))
                : [];

            const combinedChoices = [...baseChoices, ...searchChoices];
            renderLocationSearchResults(
                mode,
                combinedChoices,
                combinedChoices.length ? '' : `No locations found for "${trimmedQuery}".`
            );
        } catch (e) {
            console.error('Location search error', e);
            if (searchToken !== state.searchToken) return;
            renderLocationSearchResults(mode, baseChoices, 'Unable to search locations right now. You can still use your current place.');
        }
    }

    function searchPostLocations(query, mode = 'create') {
        const state = LOCATION_PICKER_STATE[mode];
        if (state.debounce) clearTimeout(state.debounce);
        state.debounce = setTimeout(() => performLocationSearch(query, mode), 250);
    }

    function selectPostLocation(mode, locationLabel) {
        if (!locationLabel) return;
        setSelectedLocationValue(mode, locationLabel);
        const { box, input } = getLocationPickerElements(mode);
        if (input) input.value = locationLabel;
        if (box) box.style.display = 'none';
    }

    async function openLocationPicker(mode = 'create') {
        const { box, input } = getLocationPickerElements(mode);
        if (!box || !input) return;

        const mentionBox = document.getElementById(mode === 'edit' ? 'ep-mention-search-box' : 'mention-search-box');
        if (mentionBox) mentionBox.style.display = 'none';

        const shouldOpen = box.style.display === 'none';
        box.style.display = shouldOpen ? 'block' : 'none';
        if (!shouldOpen) return;

        input.focus();
        if (input.value.trim()) {
            searchPostLocations(input.value, mode);
        } else {
            await loadCurrentLocationSuggestion(mode);
        }
    }

    async function refreshCurrentLocationSuggestion(mode = 'create') {
        const { box } = getLocationPickerElements(mode);
        if (box) box.style.display = 'block';
        await loadCurrentLocationSuggestion(mode);
    }

    function mentionExists(list, id, name) {
        const normalizedName = String(name || '').trim().toLowerCase();
        return list.some(item => (
            id !== null && id !== undefined && id !== '' && item.id === id
        ) || String(item.name || '').trim().toLowerCase() === normalizedName);
    }

    async function loadMentionCandidates(force = false) {
        if (!force && Array.isArray(window.MENTION_CANDIDATES) && window.MENTION_CANDIDATES.length) {
            return window.MENTION_CANDIDATES;
        }

        const [resM, resO] = await Promise.all([
            fetch('/api/members'),
            fetch('/api/officials')
        ]);
        const residents = await resM.json();
        const officials = await resO.json();
        const seen = new Set();

        window.MENTION_CANDIDATES = [...residents, ...officials].filter(user => {
            if (!user || !user.full_name) return false;
            const key = user.id ?? user.full_name.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        return window.MENTION_CANDIDATES;
    }

    function renderLocationPreview() {
        const preview = document.getElementById('location-preview');
        if (!preview) return;

        if (!selectedLocation) {
            preview.innerHTML = '';
            preview.style.display = 'none';
            return;
        }

        preview.innerHTML = `<i class="fa-solid fa-location-dot"></i> at ${selectedLocation} <span style="cursor:pointer; margin-left:5px;" onclick="removeSelectedLocation()">&times;</span>`;
        preview.style.display = 'flex';
    }

    function renderEditLocationPreview() {
        const preview = document.getElementById('ep-location-preview');
        if (!preview) return;

        if (!editPostLocation) {
            preview.innerHTML = '';
            preview.style.display = 'none';
            return;
        }

        preview.innerHTML = `<i class="fa-solid fa-location-dot"></i> at ${editPostLocation} <span style="cursor:pointer; margin-left:5px;" onclick="removeEditLocation()">&times;</span>`;
        preview.style.display = 'flex';
    }

    function removeSelectedLocation() {
        selectedLocation = null;
        renderLocationPreview();
    }

    function removeEditLocation() {
        editPostLocation = null;
        renderEditLocationPreview();
    }

    function removeSelectedMention(index) {
        selectedMentions.splice(index, 1);
        renderMentions();
    }

    function removeEditMention(index) {
        editPostMentions.splice(index, 1);
        renderEditMentions();
    }

    async function handleMediaSelection(event) {
        const files = Array.from(event.target.files);
        for (const file of files) {
            selectedFiles.push(file);
            const reader = new FileReader();
            const previewUrl = await new Promise(res => {
                reader.onload = (e) => res(e.target.result);
                reader.readAsDataURL(file);
            });
            selectedMediaPreviews.push({ type: file.type.startsWith('video') ? 'video' : 'image', url: previewUrl });
        }
        renderMediaPreviews();
    }

    async function handleEditMediaSelection(event) {
        const files = Array.from(event.target.files);
        for (const file of files) {
            const reader = new FileReader();
            const previewUrl = await new Promise(res => {
                reader.onload = (e) => res(e.target.result);
                reader.readAsDataURL(file);
            });
            const tempId = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`;
            file.tempId = tempId;
            editPostFiles.push(file);
            editPostMedia.push({ type: file.type.startsWith('video') ? 'video' : 'image', url: previewUrl, source: 'new', tempId: tempId });
        }
        event.target.value = '';
        renderEditMediaPreviews();
    }

    function renderMediaPreviews() {
        const container = document.getElementById('media-preview-container');
        container.innerHTML = selectedMediaPreviews.map((m, i) => `
            <div class="preview-item" style="position:relative;">
                ${m.type === 'video' ? `<video src="${m.url}" style="width:100%; height:100%; object-fit:cover;"></video>` : `<img src="${m.url}" style="width:100%; height:100%; object-fit:cover;">`}
                <div class="preview-remove" onclick="selectedFiles.splice(${i}, 1); selectedMediaPreviews.splice(${i}, 1); renderMediaPreviews();">&times;</div>
            </div>
        `).join('');
    }

    function renderEditMediaPreviews() {
        const container = document.getElementById('ep-media-preview-container');
        container.innerHTML = editPostMedia.map((m, i) => `
            <div class="preview-item" style="position:relative;">
                ${m.type === 'video' ? `<video src="${m.url}" style="width:100%; height:100%; object-fit:cover;"></video>` : `<img src="${m.url}" style="width:100%; height:100%; object-fit:cover;">`}
                <div class="preview-remove" onclick="removeEditMedia(${i})">&times;</div>
            </div>
        `).join('');
    }

    function removeEditMedia(index) {
        const media = editPostMedia[index];
        if (media && media.source === 'new') {
            editPostFiles = editPostFiles.filter(file => file.tempId !== media.tempId);
        }
        editPostMedia.splice(index, 1);
        renderEditMediaPreviews();
    }

    function toggleMentionSearch() {
        const box = document.getElementById('mention-search-box');
        document.getElementById('location-search-box').style.display = 'none';
        box.style.display = box.style.display === 'none' ? 'block' : 'none';
        if(box.style.display === 'block') document.getElementById('mention-input').focus();
    }

    function toggleEditMentionSearch() {
        const box = document.getElementById('ep-mention-search-box');
        document.getElementById('ep-location-search-box').style.display = 'none';
        box.style.display = box.style.display === 'none' ? 'block' : 'none';
        if(box.style.display === 'block') document.getElementById('ep-mention-input').focus();
    }

    async function searchMentions(query) {
        if(!query) { document.getElementById('mention-list').innerHTML = ''; return; }
        const all = await loadMentionCandidates();
        const filtered = all.filter(u => u.full_name.toLowerCase().includes(query.toLowerCase())).slice(0, 5);
        document.getElementById('mention-list').innerHTML = filtered.map(u => `
            <div class="mention-item" onclick='addMention(${JSON.stringify(u.id ?? null)}, ${JSON.stringify(u.full_name)})'>
                <img src="${u.pic_url || '/static/default-avatar.svg'}" style="width:30px; height:30px; border-radius:50%;">
                <span>${u.full_name}</span>
            </div>
        `).join('');
    }

    async function searchEditMentions(query) {
        if(!query) { document.getElementById('ep-mention-list').innerHTML = ''; return; }
        const all = await loadMentionCandidates();
        const filtered = all.filter(u => u.full_name.toLowerCase().includes(query.toLowerCase())).slice(0, 5);
        document.getElementById('ep-mention-list').innerHTML = filtered.map(u => `
            <div class="mention-item" onclick='addEditMention(${JSON.stringify(u.id ?? null)}, ${JSON.stringify(u.full_name)})'>
                <img src="${u.pic_url || '/static/default-avatar.svg'}" style="width:30px; height:30px; border-radius:50%;">
                <span>${u.full_name}</span>
            </div>
        `).join('');
    }

    function addMention(id, name) {
        if(mentionExists(selectedMentions, id, name)) return;
        selectedMentions.push({id, name});
        renderMentions();
        toggleMentionSearch();
    }

    function addEditMention(id, name) {
        if(mentionExists(editPostMentions, id, name)) return;
        editPostMentions.push({id, name});
        renderEditMentions();
        toggleEditMentionSearch();
    }

    function renderMentions() {
        const container = document.getElementById('mention-preview-container');
        container.innerHTML = selectedMentions.map((m, i) => `
            <div class="mention-tag">@${m.name} <span style="cursor:pointer" onclick="removeSelectedMention(${i})">&times;</span></div>
        `).join('');
    }

    function renderEditMentions() {
        const container = document.getElementById('ep-mention-preview-container');
        container.innerHTML = editPostMentions.map((m, i) => `
            <div class="mention-tag">@${m.name} <span style="cursor:pointer" onclick="removeEditMention(${i})">&times;</span></div>
        `).join('');
    }

    function attachCurrentLocation() {
        openLocationPicker();
    }

    function attachEditLocation() {
        openLocationPicker('edit');
    }

    async function postNews() {
        const content = document.getElementById('news-content').value;
        if (!content && selectedFiles.length === 0) return alert("Post cannot be empty.");
        
        const btn = document.querySelector('button[onclick="postNews()"]');
        const oldText = btn.innerText;
        btn.innerText = "Uploading...";
        btn.disabled = true;

        try {
            const uploadedUrls = [];
            for (const file of selectedFiles) {
                const formData = new FormData();
                formData.append('file', file);
                const res = await fetch('/api/upload_media', { method: 'POST', body: formData });
                const data = await res.json();
                if(data.success) uploadedUrls.push(data.url);
            }
            
            const body = {
                content: content,
                media_urls: uploadedUrls,
                mentions: selectedMentions.map(m => ({ id: m.id, name: m.name })),
                location: selectedLocation
            };
            
            const res = await fetch('/api/posts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if ((await res.json()).success) {
                alert("Post shared successfully!");
                document.getElementById('news-content').value = '';
                selectedFiles = [];
                selectedMediaPreviews = [];
                selectedMentions = [];
                selectedLocation = null;
                document.getElementById('media-preview-container').innerHTML = '';
                resetLocationSearchBox();
                renderMentions();
                renderLocationPreview();
                loadNewsFeed();
            }
        } catch(e) {
            alert("Error posting news feed.");
        } finally {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }

    async function loadNewsFeed() {
        const res = await fetch('/api/posts');
        const query = (window.NAV_SEARCH_QUERY || '').toLowerCase();
        const posts = (await res.json()).filter(p => window.postMatchesSearch(p, query));
        window.POSTS_CACHE = posts;
        let html = '';
        posts.forEach(p => {
            const mentionNames = window.getMentionDisplayNames(p);
            const mentionsHtml = mentionNames.length > 0 ? 
                `<span style="color:var(--primary); font-size:13px;">with <b>${mentionNames.join(', ')}</b></span>` : '';
            const locationHtml = p.location ? 
                `<br><small style="color:#f3425f; font-weight:600;"><i class="fa-solid fa-location-dot"></i> ${p.location}</small>` : '';
            const authorPosition = p.author_position || ((p.author_role === 'bio' || p.author_role === 'official') ? 'Barangay Official' : '');
            
            let mediaHtml = '';
            if(p.media_urls && p.media_urls.length > 0) {
                const gridClass = p.media_urls.length >= 3 ? 'grid-3' : (p.media_urls.length === 2 ? 'grid-2' : 'grid-1');
                mediaHtml = `<div class="post-media-grid ${gridClass}">`;
                p.media_urls.forEach(url => {
                    if(url.includes('video') || url.startsWith('data:video')) {
                        mediaHtml += `<video src="${url}" controls></video>`;
                    } else {
                        mediaHtml += `<img src="${url}" onclick="window.open(this.src)">`;
                    }
                });
                mediaHtml += `</div>`;
            } else if (p.image_url) {
                mediaHtml = `<img src="${p.image_url}" style="width:100%; border-radius:10px; margin-top:10px;" onclick="window.open(this.src)" loading="lazy">`;
            }

            html += `<div class="glass-card" style="margin-bottom:20px; padding:20px; animation: fadeIn 0.4s ease;">
                <div style="display:flex; justify-content:space-between; margin-bottom:12px;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <img src="${p.author_pic || '/static/default-avatar.svg'}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;" loading="lazy">
                        <div>
                            <b style="font-size:15px; display:block;">${p.author_name}</b>
                            ${authorPosition ? `<small style="color:var(--primary); font-size:11px; font-weight:800; display:block; margin-top:2px;">${authorPosition}</small>` : ''}
                            <small style="color:var(--text-muted); font-size:11px;">${formatPhilippineDateTime(p.timestamp)}</small>
                        </div>
                    </div>
                </div>
                <p style="margin:0; font-size:15px; line-height:1.6; white-space: pre-wrap; color:var(--text-light);">${p.content} ${mentionsHtml}</p>
                ${locationHtml}
                ${mediaHtml}
                
                <div style="margin-top:15px; display:flex; gap:20px; align-items:center; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px;">
                    <div style="cursor:pointer; display:flex; align-items:center; gap:6px; font-size:18px;" onclick="toggleLike(${p.id})">
                        <i class="${p.is_liked ? 'fa-solid fa-heart' : 'fa-regular fa-heart'}" style="color:${p.is_liked ? '#f3425f' : 'inherit'}"></i>
                        <span style="font-size:14px; font-weight:600;">${p.likes_count || 0}</span>
                    </div>
                    <div style="position:relative;">
                        <i class="fa-solid fa-ellipsis" style="cursor:pointer; color:var(--text-muted); font-size:18px;" onclick="togglePostMenu(${p.id})"></i>
                        <div id="post-menu-${p.id}" style="display:none; position:absolute; left:0; bottom:25px; background:var(--bg-dark); border:1px solid var(--card-border); border-radius:10px; padding:5px; z-index:100; min-width:100px; box-shadow:0 5px 15px rgba(0,0,0,0.5);">
                            <div style="padding:8px; cursor:pointer; font-size:13px; border-radius:5px;" class="menu-item-hover" onclick="openEditPostModal(${p.id})"><i class="fa-solid fa-pen"></i> Edit Post</div>
                            <div style="padding:8px; cursor:pointer; font-size:13px; color:var(--danger); border-radius:5px;" class="menu-item-hover" onclick="deletePost(${p.id})"><i class="fa-solid fa-trash"></i> Delete Post</div>
                        </div>
                    </div>
                </div>
            </div>`;
        });
        document.getElementById('news-feed-box').innerHTML = html || 'No posts yet.';
    }

    window.togglePostMenu = (id) => {
        const menu = document.getElementById(`post-menu-${id}`);
        const isVisible = menu.style.display === 'block';
        document.querySelectorAll('[id^="post-menu-"]').forEach(m => m.style.display = 'none');
        if(!isVisible) menu.style.display = 'block';
    };

    window.openEditPostModal = async (id) => {
        const post = (window.POSTS_CACHE || []).find(p => p.id === id);
        if (!post) return;
        const mentionCandidates = await loadMentionCandidates();
        document.getElementById('ep-id').value = id;
        document.getElementById('ep-content').value = post.content || '';
        editPostFiles = [];
        editPostMedia = ((post.media_urls && post.media_urls.length ? post.media_urls : (post.image_url ? [post.image_url] : []))).map(url => ({
            type: (typeof url === 'string' && (url.includes('video') || url.startsWith('data:video'))) ? 'video' : 'image',
            url: typeof url === 'string' ? url : url.url,
            source: 'existing'
        }));
        editPostMentions = (post.mentions || []).map(m => {
            if (typeof m === 'string') {
                const match = mentionCandidates.find(user => (user.full_name || '').toLowerCase() === m.toLowerCase());
                return { id: match ? match.id : null, name: m };
            }

            const name = m.name || m.full_name || '';
            if (!name) return null;
            if (m.id !== undefined && m.id !== null && m.id !== '') {
                return { id: m.id, name };
            }

            const match = mentionCandidates.find(user => (user.full_name || '').toLowerCase() === name.toLowerCase());
            return { id: match ? match.id : null, name };
        }).filter(Boolean);
        editPostLocation = post.location || null;
        renderEditMediaPreviews();
        renderEditMentions();
        renderEditLocationPreview();
        resetLocationSearchBox('edit');
        document.getElementById('ep-mention-search-box').style.display = 'none';
        document.getElementById('ep-mention-input').value = '';
        document.getElementById('ep-mention-list').innerHTML = '';
        document.getElementById('ep-media').value = '';
        document.getElementById('edit-post-modal').style.display = 'block';
        document.querySelectorAll('[id^="post-menu-"]').forEach(m => m.style.display = 'none');
    };

    window.savePostEdit = async () => {
        const id = document.getElementById('ep-id').value;
        const content = document.getElementById('ep-content').value;
        const uploadedUrls = [];
        for (const file of editPostFiles) {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch('/api/upload_media', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.success) uploadedUrls.push({ tempId: file.tempId, url: data.url });
        }

        const mediaUrls = editPostMedia.map(media => {
            if (media.source === 'new') {
                const uploaded = uploadedUrls.find(item => item.tempId === media.tempId);
                return uploaded ? uploaded.url : null;
            }
            return media.url;
        }).filter(Boolean);

        await fetch(`/api/posts/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                content,
                media_urls: mediaUrls,
                mentions: editPostMentions.map(m => ({ id: m.id, name: m.name })),
                location: editPostLocation,
                image_url: null
            })
        });
        document.getElementById('edit-post-modal').style.display = 'none';
        resetLocationSearchBox('edit');
        loadNewsFeed();
    };

    window.deletePost = async (id) => {
        if(!confirm("Are you sure you want to delete this post?")) return;
        try {
            const res = await fetch(`/api/posts/${id}`, { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                alert(data.error || 'Unable to delete post.');
                return;
            }
            loadNewsFeed();
        } catch (error) {
            alert('Unable to delete post right now.');
        }
    };

    async function toggleLike(postId) {
        try {
            const res = await fetch(`/api/posts/${postId}/like`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                // Find the specific post in the feed and update its heart/count
                // Actually, it's easier to just update the local cache and re-render that specific card.
                // But for now, I'll just fetch the new state for that post if I had a single-post API.
                // Since I don't, I'll just update the icons locally for speed.
                const heartIcon = document.querySelector(`[onclick="toggleLike(${postId})"] i`);
                const countSpan = document.querySelector(`[onclick="toggleLike(${postId})"] span`);
                let currentCount = parseInt(countSpan.innerText);
                
                if (data.action === 'liked') {
                    heartIcon.className = 'fa-solid fa-heart';
                    heartIcon.style.color = '#f3425f';
                    countSpan.innerText = currentCount + 1;
                } else {
                    heartIcon.className = 'fa-regular fa-heart';
                    heartIcon.style.color = 'inherit';
                    countSpan.innerText = Math.max(0, currentCount - 1);
                }
            }
        } catch(e) { console.error("Like error", e); }
    }

    
    async function triggerEmergency(type) {
        if (!navigator.geolocation) return alert("Geolocation not supported.");
        navigator.geolocation.getCurrentPosition(async (pos) => {
            const body = { type, lat: pos.coords.latitude, lng: pos.coords.longitude, purok: "N/A" };
            await fetch('/api/emergency', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            alert('🚨 Emergency Alert Recorded.');
            loadEmergencies();
        });
    }

    async function triggerEmergency(type) {
        const result = await window.submitEmergencyReport(type, {
            successMessage: 'Emergency alert recorded for fellow barangay staff.',
            fallbackMessage: 'Location is unavailable right now. Allow location access or update your saved house coordinates, then try again.'
        });
        if (!result?.success) return;
        await refreshEmergencyPanels();
    }

    async function refreshEmergencyPanels() {
        await Promise.all([loadEmergencies(), loadEmgHistory()]);
    }

    async function loadEmergencies() {
        const box = document.getElementById('emg-box');
        if (box) box.innerHTML = '<p class="text-muted">Loading emergencies...</p>';

        try {
            const res = await fetch('/api/emergency', {
                cache: 'no-store',
                headers: { 'Cache-Control': 'no-cache' }
            });
            if (!res.ok) throw new Error('Unable to load emergencies.');

            const payload = await res.json();
            const data = Array.isArray(payload) ? payload : [];
            let html = '';

            data.forEach(e => {
                html += `<div style="border:1px solid var(--danger); padding:10px; border-radius:8px; margin-bottom:10px; background:rgba(239, 68, 68, 0.1);">
                    <strong>🚨 ${e.type.toUpperCase()} EMERGENCY</strong><br/>
                    Reported By: <b>${e.reported_by_name}</b><br/>
                    Purok: ${e.purok}<br/>
                    Time: ${formatPhilippineDateTime(e.timestamp)}<br/>
                    <div style="display:flex; gap:10px; margin-top:10px;">
                        <button class="btn btn-primary" style="padding: 5px 10px;" onclick="ackEmergency(${e.id})">Acknowledge</button>
                        <button class="btn btn-secondary" style="padding: 5px 10px;" onclick="viewEmergencyMap(${e.lat}, ${e.lng}, '${e.type}', '${e.reported_by_name.replace(/'/g, '\\\'')}')">View Map</button>
                    </div>
                </div>`;
            });

            if (box) box.innerHTML = html || 'No unacknowledged emergencies.';
        } catch (error) {
            if (box) box.innerHTML = '<p class="text-danger">Unable to load emergencies right now.</p>';
        }
    }
    async function ackEmergency(id) {
        const res = await fetch('/api/emergency/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
        if (!res.ok) {
            alert('Unable to acknowledge the emergency right now.');
            return;
        }
        await refreshEmergencyPanels();
    }

    async function submitIndividualRating(off_id) {
        const ratingVal = document.getElementById(`rating-${off_id}`).value;
        const feedback = document.getElementById(`fb-${off_id}`) ? document.getElementById(`fb-${off_id}`).value : '';
        
        const body = {
            official_id: off_id,
            rating: parseInt(ratingVal),
            feedback: feedback
        };
        const res = await fetch('/api/ratings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const d = await res.json();
        if (d.success) { 
            alert("Rating Submitted successfully (1-5 scale)."); 
            if(document.getElementById(`fb-${off_id}`)) document.getElementById(`fb-${off_id}`).value=''; 
            window.RATING_SUMMARY_CACHE = null;
            loadMembers();
        }
        else alert(d.error);
    }
    
    async function loadMembers() {
        // Load Residents
        const resM = await fetch('/api/members');
        const query = (window.NAV_SEARCH_QUERY || '').toLowerCase();
        window.MEMBERS_CACHE = (await resM.json()).filter(m => !query || (m.full_name || '').toLowerCase().includes(query));
        let html = '';
        window.MEMBERS_CACHE.forEach(m => {
            let statusBadge = '';
            if (!m.is_active) {
                statusBadge = `<br><span style="color:#64748b; font-weight:800; font-size:10px;">⚪ DEACTIVATED</span>`;
            } else if (m.is_banned) {
                const h = Math.floor(m.ban_remaining / 3600);
                const mm = Math.floor((m.ban_remaining % 3600) / 60);
                const ss = m.ban_remaining % 60;
                const timeStr = [h, mm, ss].map(v => v < 10 ? '0' + v : v).join(':');
                statusBadge = `<br><span style="color:var(--danger); font-weight:800; font-size:11px;">🚫 BANNED: ${timeStr}</span>`;
            }

            const warnBtn = `<button class="btn btn-secondary btn-compact member-admin-btn member-admin-warn" style="padding:4px 8px; font-size:10px; background:var(--warning); color:black;" onclick="issueWarning(${m.id}, '${m.full_name.replace(/'/g, "\\'")}')">⚠️ Warn</button>`;
            const toggleBtn = `<button class="btn btn-secondary btn-compact member-admin-btn member-admin-toggle" style="padding:4px 8px; font-size:10px; background:${m.is_active ? '#4ade80' : '#64748b'}; color:white;" onclick="toggleActive(${m.id})">${m.is_active ? 'Deactivate' : 'Activate'}</button>`;

            html += `<div style="background:rgba(255,255,255,0.05); padding:10px; border-radius:10px; display:flex; align-items:center; position:relative; margin-bottom:10px;">
                <img src="${m.pic_url || '/static/default-avatar.svg'}" style="width:40px;height:40px;border-radius:50%;margin-right:10px;object-fit:cover;">
                <div style="flex:1;"><b>${m.full_name}</b><br><small style="color:var(--text-muted)">Role: ${m.role.toUpperCase()} | Class: ${m.class_type || 'N/A'}</small>${statusBadge}</div>
                <div style="display:flex; flex-direction:column; gap:5px; align-items:flex-end;">
                    <div style="display:flex; gap:5px;">
                        ${warnBtn}
                        <button class="btn btn-secondary btn-compact member-admin-btn member-admin-edit" style="padding:4px 8px; font-size:10px;" onclick="openEditModal(${m.id})">Edit</button>
                    </div>
                    ${toggleBtn}
                </div>
            </div>`;
        });
        document.getElementById('members-list').innerHTML = html || 'No residents found.';
        
        // Load Officials
        const resO = await fetch('/api/officials');
        window.OFFICIALS_CACHE = (await resO.json()).filter(o => !query || (o.full_name || '').toLowerCase().includes(query));
        if (window.loadRatingScheduleStatus) await window.loadRatingScheduleStatus(true);
        if (window.loadRatingSummary) await window.loadRatingSummary(true);
        renderOfficialsList(window.NAV_SEARCH_QUERY || '');

        if(document.getElementById('bio-map')) {
            const allUsers = [...window.MEMBERS_CACHE, ...window.OFFICIALS_CACHE];
            window.initGlobalMap('bio-map', allUsers, false);
            window.MAP_INIT = true;
        }
    }

    function renderOfficialsList(query = '') {
        let offHtml = '';
        const filtered = window.OFFICIALS_CACHE.filter(o => o.full_name.toLowerCase().includes(query.toLowerCase()));
        filtered.forEach(o => {
            const isMe = o.id == 1;
            offHtml += `<div style="padding:15px; border:1px solid var(--card-border); border-radius:15px; background:${isMe ? 'rgba(69, 189, 98, 0.05)' : 'rgba(255,255,255,0.02)'}; margin-bottom:15px; border-left: ${isMe ? '4px solid #45bd62' : '1px solid var(--card-border)'};">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                    <img src="${o.pic_url || '/static/default-avatar.svg'}" style="width:50px;height:50px;border-radius:50%;object-fit:cover; border: 2px solid var(--primary);">
                    <div style="flex:1;">
                        <b style="font-size:16px;">${o.full_name} ${isMe ? '<span style="color:#45bd62; font-size:10px;">(YOU)</span>' : ''}</b><br>
                        <span style="color:var(--primary); font-size:12px; font-weight:700;">${(o.position || 'Barangay Official').toUpperCase()}</span>
                        ${window.buildVoteStatsHtml ? window.buildVoteStatsHtml(o.id) : ''}
                    </div>
                    <button class="btn btn-secondary btn-compact member-admin-btn member-admin-edit" style="padding:5px 10px; font-size:11px;" onclick="openEditModal(${o.id}, true)">Edit</button>
                </div>
                <div style="background:rgba(0,0,0,0.2); padding:10px; border-radius:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-size:13px;">Official Rating (1-5)</span>
                        <b id="val-label-${o.id}" style="color:var(--warning)">5.0</b>
                    </div>
                    <input type="range" id="rating-${o.id}" min="1" max="5" step="1" value="5" style="width:100%; accent-color:var(--warning);" oninput="document.getElementById('val-label-${o.id}').innerText = parseFloat(this.value).toFixed(1)">
                    <textarea id="fb-${o.id}" class="input-field" placeholder="Share your feedback or what they can improve..." rows="2" style="margin-top:10px; font-size:13px;"></textarea>
                    ${window.buildRatingActionHtml ? window.buildRatingActionHtml(o.id) : `<button class="btn btn-primary" style="width:100%; margin-top:5px; padding:8px;" onclick="submitIndividualRating(${o.id})">Rate Official</button>`}
                    <small style="display:block; text-align:center; margin-top:5px; color:var(--text-muted); font-size:10px;">BIO controls the official rating schedule.</small>
                </div>
            </div>`;
        });
        if(document.getElementById('officials-list')) document.getElementById('officials-list').innerHTML = offHtml || 'No officials registered yet.';
    }

    let addPinMap = null;
    let addPinMarker = null;

    function loadBioHome(force = false) {
        if (force || !bioTabState.homeLoaded) {
            bioTabState.homeLoaded = true;
            loadNewsFeed();
        }
    }

    function loadBioMembersSection(force = false) {
        if (force || !bioTabState.membersLoaded) {
            bioTabState.membersLoaded = true;
            loadMembers();
        }
    }

    function loadBioWelfareSection(force = false) {
        if (force || !bioTabState.welfareLoaded) {
            bioTabState.welfareLoaded = true;
            if (window.loadWelfareModule) window.loadWelfareModule(true);
        } else if (window.renderWelfareRecords) {
            window.renderWelfareRecords();
        }
    }

    function loadBioOfficialsSection(force = false) {
        if (force || !bioTabState.officialsLoaded) {
            bioTabState.officialsLoaded = true;
            loadBioRatingSchedule();
            loadMembers();
        } else if (!window.OFFICIALS_CACHE) {
            loadBioRatingSchedule();
            loadMembers();
        } else {
            loadBioRatingSchedule();
        }
    }

    function loadBioReportSection(force = false) {
        if (force || !bioTabState.reportLoaded) {
            bioTabState.reportLoaded = true;
            refreshEmergencyPanels();
        }
    }

    function loadBioHistorySection(force = false) {
        if (force || !bioTabState.historyLoaded) {
            bioTabState.historyLoaded = true;
            loadHistory();
        }
    }

    function loadBioMapSection(force = false) {
        if (window.MAP_INIT && !force) {
            setTimeout(() => { if(window.L && L.Map) window.dispatchEvent(new Event('resize')); }, 100);
            return;
        }

        if (force || !bioTabState.mapLoaded) {
            bioTabState.mapLoaded = true;
            loadMembers();
        }
    }

    window.addEventListener('tabChanged', (e) => {
        const tab = typeof e.detail === 'string' ? e.detail : e.detail.tabId;
        const forced = typeof e.detail === 'object' && e.detail.forced;
        if(tab === 'home') loadBioHome(forced);
        if(tab === 'members') loadBioMembersSection(forced);
        if(tab === 'welfare') loadBioWelfareSection(forced);
        if(tab === 'officials') loadBioOfficialsSection(forced);
        if(tab === 'notification') {
            loadAnnouncementPurokOptions();
            loadBioAnnouncements();
        }
        if(tab === 'report') loadBioReportSection(forced);
        if(tab === 'history') loadBioHistorySection(forced);
        if(tab === 'maps') loadBioMapSection(forced);
        if(tab === 'add') {
            if(!addPinMap && document.getElementById('add-pin-map')) {
                addPinMap = L.map('add-pin-map').setView([12.8797, 121.7740], 5);
                L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',{maxZoom: 20, subdomains:['mt0','mt1','mt2','mt3']}).addTo(addPinMap);
                
                if(window.USER_BRGY) {
                    fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(window.USER_BRGY + ', Philippines')}`)
                    .then(r => r.json())
                    .then(data => {
                        if(data.length > 0) addPinMap.setView([data[0].lat, data[0].lon], 15);
                    });
                }

                addPinMap.on('click', function(e) {
                    if(addPinMarker) addPinMap.removeLayer(addPinMarker);
                    addPinMarker = L.marker(e.latlng).addTo(addPinMap);
                    document.getElementById('r-lat').value = e.latlng.lat;
                    document.getElementById('r-lng').value = e.latlng.lng;
                });
            } else if(addPinMap) {
                setTimeout(() => { addPinMap.invalidateSize(); }, 100);
            }
        }
    });

    window.addEventListener('nameSearchChanged', (e) => {
        const tab = e.detail.tabId;
        if(tab === 'home') loadNewsFeed();
        if(tab === 'welfare' && window.renderWelfareRecords) window.renderWelfareRecords();
        if(tab === 'members' || tab === 'officials' || tab === 'maps') loadMembers();
    });

    let editPinMap = null;
    let editPinMarker = null;

    function openEditModal(id, isOfficial = false) {
        const m = isOfficial ? window.OFFICIALS_CACHE.find(x => x.id === id) : window.MEMBERS_CACHE.find(x => x.id === id);
        if(!m) return;
        document.getElementById('e-id').value = id;
        document.getElementById('edit-title').innerText = 'Edit ' + (m.full_name||'User');
        document.getElementById('e-name').value = m.full_name || '';
        document.getElementById('e-user').value = m.username || '';
        document.getElementById('e-role').value = m.role || 'resident';
        document.getElementById('e-pos').value = m.position || '';
        document.getElementById('e-bdate').value = m.birthdate || '';
        document.getElementById('e-bplace').value = m.birthplace || '';
        document.getElementById('e-purok').value = m.purok || '';
        document.getElementById('e-emp').value = m.employment_status || 'unspecified';
        document.getElementById('e-mother').value = m.mother_name || '';
        document.getElementById('e-father').value = m.father_name || '';
        document.getElementById('e-income').value = m.monthly_income || '';
        document.getElementById('e-lat').value = m.lat || '';
        document.getElementById('e-lng').value = m.lng || '';
        updateClassLabel(m.monthly_income || 0, 'e-class-tag');
        const deleteBtn = document.getElementById('delete-member-btn');
        if (deleteBtn) {
            const isSelfBio = m.role === 'bio' && m.id == 1;
            const canDelete = ['resident', 'official'].includes(m.role) || isSelfBio;
            deleteBtn.style.display = canDelete ? 'block' : 'none';
            deleteBtn.dataset.memberRole = m.role || '';
            deleteBtn.dataset.memberName = m.full_name || '';
            deleteBtn.dataset.selfDelete = isSelfBio ? '1' : '0';
            deleteBtn.innerText = isSelfBio
                ? 'Delete BIO Account Only'
                : (canDelete ? `Delete ${m.role === 'official' ? 'Official' : 'Resident'} Account` : 'Delete Account');
        }
        document.getElementById('edit-modal').style.display = 'block';

        setTimeout(() => {
            if(!editPinMap) {
                editPinMap = L.map('edit-pin-map').setView([m.lat || 12.8797, m.lng || 121.7740], m.lat ? 18 : 5);
                L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',{maxZoom: 20, subdomains:['mt0','mt1','mt2','mt3']}).addTo(editPinMap);
                editPinMap.on('click', (e) => {
                    if(editPinMarker) editPinMap.removeLayer(editPinMarker);
                    editPinMarker = L.marker([e.latlng.lat, e.latlng.lng]).addTo(editPinMap);
                    document.getElementById('e-lat').value = e.latlng.lat;
                    document.getElementById('e-lng').value = e.latlng.lng;
                });
            } else {
                editPinMap.setView([m.lat || 12.8797, m.lng || 121.7740], m.lat ? 18 : 5);
            }
            if(editPinMarker) editPinMap.removeLayer(editPinMarker);
            if(m.lat && m.lng) {
                editPinMarker = L.marker([m.lat, m.lng]).addTo(editPinMap);
            }
            editPinMap.invalidateSize();
        }, 300);
    }

    function updateClassLabel(val, tagId) {
        const inc = parseFloat(val) || 0;
        let c = 'D';
        if(inc > 30000) c = 'A';
        else if(inc > 20000) c = 'B';
        else if(inc > 10000) c = 'C';
        document.getElementById(tagId).innerText = 'CLASS ' + c;
    }

    async function saveEdit() {
        const id = document.getElementById('e-id').value;
        let picUrl = '';
        const picInput = document.getElementById('e-pic');
        if(picInput.files.length > 0) {
            const formData = new FormData();
            formData.append('file', picInput.files[0]);
            const upRes = await fetch('/api/upload_image', {method: 'POST', body: formData});
            const upData = await upRes.json();
            if(upData.success) picUrl = upData.url;
        }
        const body = {
            full_name: document.getElementById('e-name').value,
            username: document.getElementById('e-user').value,
            role: document.getElementById('e-role').value,
            birthdate: document.getElementById('e-bdate').value,
            birthplace: document.getElementById('e-bplace').value,
            purok: document.getElementById('e-purok').value,
            employment_status: document.getElementById('e-emp').value,
            mother_name: document.getElementById('e-mother').value,
            father_name: document.getElementById('e-father').value,
            monthly_income: document.getElementById('e-income').value,
            position: document.getElementById('e-pos').value,
            lat: document.getElementById('e-lat').value ? parseFloat(document.getElementById('e-lat').value) : null,
            lng: document.getElementById('e-lng').value ? parseFloat(document.getElementById('e-lng').value) : null
        };
        if(document.getElementById('e-pass').value) body.password = document.getElementById('e-pass').value;
        if(picUrl) body.pic_url = picUrl;

        await fetch('/api/bio/member/' + id, {method: 'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        document.getElementById('edit-modal').style.display = 'none';
        alert("Member Updated.");
        window.MENTION_CANDIDATES = null;
        loadMembers();
    }
    
    async function deleteMember() {
        const deleteBtn = document.getElementById('delete-member-btn');
        const isSelfDelete = deleteBtn && deleteBtn.dataset.selfDelete === '1';
        const confirmMessage = isSelfDelete
            ? "Are you sure you want to permanently delete only your BIO account? This will log you out and cannot be undone."
            : "Are you sure you want to permanently delete this resident/official account? This cannot be undone.";
        if(!confirm(confirmMessage)) return;
        const id = document.getElementById('e-id').value;
        try {
            const res = await fetch('/api/bio/member/' + id, {method: 'DELETE'});
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                alert(data.error || 'Unable to delete this account.');
                return;
            }
            document.getElementById('edit-modal').style.display = 'none';
            if (data.deleted_self && data.redirect_url) {
                window.location.href = data.redirect_url;
                return;
            }
            alert("Account deleted.");
            window.MENTION_CANDIDATES = null;
            loadMembers();
        } catch (error) {
            alert('Unable to delete this account right now.');
        }
    }

    async function loadHistory() {
        const res = await fetch('/api/history');
        const data = await res.json();
        let html = '';
        data.forEach(h => {
            html += `<div style="padding:15px; border-radius:8px; border-left:4px solid var(--primary); background:rgba(255,255,255,0.02); margin-bottom:10px;">
                <p style="margin:0; font-size:15px;">${h.action}</p>
                <small class="text-muted">${formatPhilippineDateTime(h.timestamp)}</small>
            </div>`;
        });
        if(document.getElementById('history-box')) document.getElementById('history-box').innerHTML = html || '<p class="text-muted">No history logs yet.</p>';
    }

    async function loadEmgHistory() {
        const historyBox = document.getElementById('emg-history-box');
        if (historyBox) historyBox.innerHTML = '<p class="text-muted">Loading emergency history...</p>';

        try {
            const res = await fetch('/api/emergency/history', {
                cache: 'no-store',
                headers: { 'Cache-Control': 'no-cache' }
            });
            if (!res.ok) throw new Error('Unable to load emergency history.');

            const payload = await res.json();
            const data = Array.isArray(payload) ? payload : [];
            let html = '';

            data.forEach(e => {
                html += `<div style="border:1px solid #555; padding:10px; border-radius:8px; margin-bottom:10px; background:rgba(255,255,255,0.05); opacity:0.8;">
                    <strong>✅ RESOLVED: ${e.type.toUpperCase()} EMERGENCY</strong><br/>
                    Reported By: <b>${e.reported_by_name}</b><br/>
                    Time: ${formatPhilippineDateTime(e.timestamp)}<br/>
                    <button class="btn btn-secondary" style="padding: 5px 10px; margin-top:10px;" onclick="viewEmergencyMap(${e.lat}, ${e.lng}, '${e.type}', '${e.reported_by_name.replace(/'/g, '\\\'')}')">View Historical Map</button>
                </div>`;
            });

            if (historyBox) historyBox.innerHTML = html || 'No historical records.';
        } catch (error) {
            if (historyBox) historyBox.innerHTML = '<p class="text-danger">Unable to load emergency history right now.</p>';
        }
    }

    setInterval(() => {
        if (!window.MEMBERS_CACHE) return;
        let needsRefresh = false;
        window.MEMBERS_CACHE.forEach(m => {
            if (m.is_banned && m.ban_remaining > 0) {
                m.ban_remaining--;
                needsRefresh = true;
            } else if (m.is_banned && m.ban_remaining <= 0) {
                m.is_banned = false;
                needsRefresh = true;
            }
        });
        if (needsRefresh) {
            // Re-render only if directory is visible or simple re-render
            const dir = document.getElementById('members-list');
            if (dir && dir.offsetParent !== null) {
                renderMembersList();
            }
        }
    }, 1000);

    function renderMembersList() {
        let html = '';
        window.MEMBERS_CACHE.forEach(m => {
            let statusBadge = '';
            if (!m.is_active) {
                statusBadge = `<br><span style="color:#64748b; font-weight:800; font-size:10px;">⚪ DEACTIVATED</span>`;
            } else if (m.is_banned) {
                const h = Math.floor(m.ban_remaining / 3600);
                const mm = Math.floor((m.ban_remaining % 3600) / 60);
                const ss = m.ban_remaining % 60;
                const timeStr = [h, mm, ss].map(v => v < 10 ? '0' + v : v).join(':');
                statusBadge = `<br><span style="color:var(--danger); font-weight:800; font-size:11px;">🚫 BANNED: ${timeStr}</span>`;
            }
            const warnBtn = (m.role === 'resident') ? 
                `<button class="btn btn-secondary btn-compact member-admin-btn member-admin-warn" style="padding:4px 8px; font-size:10px; background:var(--warning); color:black;" onclick="issueWarning(${m.id}, '${m.full_name.replace(/'/g, "\\'")}')">⚠️ Warn</button>` : '';

            const toggleBtn = `<button class="btn btn-secondary btn-compact member-admin-btn member-admin-toggle" style="padding:4px 8px; font-size:10px; background:${m.is_active ? '#4ade80' : '#64748b'}; color:white;" onclick="toggleActive(${m.id})">${m.is_active ? 'Deactivate' : 'Activate'}</button>`;

            html += `<div style="background:rgba(255,255,255,0.05); padding:10px; border-radius:10px; display:flex; align-items:center; position:relative; margin-bottom:10px;">
                <img src="${m.pic_url || '/static/default-avatar.svg'}" style="width:40px;height:40px;border-radius:50%;margin-right:10px;object-fit:cover;">
                <div style="flex:1;"><b>${m.role === 'official' ? m.full_name + ' (' + (m.position || 'Official') + ')' : m.full_name}</b><br><small style="color:var(--text-muted)">Role: ${m.role.toUpperCase()} | Class: ${m.class_type || 'N/A'}</small>${statusBadge}</div>
                <div style="display:flex; flex-direction:column; gap:5px; align-items:flex-end;">
                    <div style="display:flex; gap:5px;">
                        ${warnBtn}
                        <button class="btn btn-secondary btn-compact member-admin-btn member-admin-edit" style="padding:4px 8px; font-size:10px;" onclick="openEditModal(${m.id})">Edit</button>
                    </div>
                    ${toggleBtn}
                </div>
            </div>`;
        });
        document.getElementById('members-list').innerHTML = html;
    }

    window.calcRelief = async function() {
        const budget = document.getElementById('r-budget').value;
        if (!budget || parseFloat(budget) <= 0) return alert('Enter a valid budget first.');

        window.RELIEF_CALC_ITERATION = (window.RELIEF_CALC_ITERATION || 0);
        const iteration = window.RELIEF_CALC_ITERATION;
        window.RELIEF_CALC_ITERATION += 1;

        const res = await fetch('/api/relief/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ budget, iteration })
        });
        const d = await res.json();
        if (!res.ok || !d.success) {
            alert(d.error || 'Unable to generate the AI distribution right now.');
            return;
        }

        let h = `
            <div style="padding:12px; border-radius:12px; background:rgba(59,130,246,0.1); border:1px solid rgba(59,130,246,0.28); margin-bottom:12px; text-align:left;">
                <strong style="display:block; color:var(--secondary);">${d.strategy?.label || 'AI Scenario'}</strong>
                <small class="text-muted">Run #${d.strategy?.iteration || (iteration + 1)} · ${d.strategy?.focus || 'Dynamic barangay-based allocation strategy'}</small>
                <p style="margin:10px 0 0; line-height:1.5;">${d.ai_summary || ''}</p>
                <p style="margin:10px 0 0; line-height:1.5; color:rgba(255,255,255,0.88);">${d.ai_recommendation || ''}</p>
            </div>
            <ul style="padding-left:20px; text-align:left;">
        `;
        d.allocations.forEach(a => {
            const amount = Number(a.allocated_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            h += `<li>Fam ID #${a.family_id}: â‚±${amount} (${a.allocation_percent || 0}%)<br/><small style="color:var(--text-muted);">${a.explanation || 'AI-calculated household need factors'}</small></li>`;
        });
        h += '</ul>';
        if (!d.allocations || !d.allocations.length) {
            h += '<p class="text-muted" style="text-align:left;">No family records were available in this barangay for the AI calculator.</p>';
        }
        document.getElementById('r-results').innerHTML = h;
    };

    window.calcRelief = async function() {
        const budget = document.getElementById('r-budget').value;
        if (!budget || parseFloat(budget) <= 0) return alert('Enter a valid budget first.');

        window.RELIEF_CALC_ITERATION = (window.RELIEF_CALC_ITERATION || 0);
        const iteration = window.RELIEF_CALC_ITERATION;
        window.RELIEF_CALC_ITERATION += 1;

        const res = await fetch('/api/relief/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ budget, iteration })
        });
        const d = await res.json();
        if (!res.ok || !d.success) {
            alert(d.error || 'Unable to generate the AI distribution right now.');
            return;
        }

        let h = `
            <div style="padding:12px; border-radius:12px; background:rgba(59,130,246,0.1); border:1px solid rgba(59,130,246,0.28); margin-bottom:12px; text-align:left;">
                <strong style="display:block; color:var(--secondary);">${d.strategy?.label || 'AI Scenario'}</strong>
                <small class="text-muted">Run #${d.strategy?.iteration || (iteration + 1)} - ${d.strategy?.focus || 'Randomized class-based allocation strategy'}</small>
                <p style="margin:10px 0 0; line-height:1.5;">${d.ai_summary || ''}</p>
                <p style="margin:10px 0 0; line-height:1.5; color:rgba(255,255,255,0.88);">${d.ai_recommendation || ''}</p>
            </div>
            <ul style="padding-left:20px; text-align:left;">
        `;
        d.allocations.forEach(a => {
            const amount = Number(a.allocated_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            h += `<li>Fam ID #${a.family_id}: PHP ${amount} (${a.allocation_percent || 0}%)<br/><small style="color:var(--text-muted);">${a.explanation || 'AI-calculated class and household factors'}</small></li>`;
        });
        h += '</ul>';
        if (!d.allocations || !d.allocations.length) {
            h += '<p class="text-muted" style="text-align:left;">No family records were available in this barangay for the AI calculator.</p>';
        }
        document.getElementById('r-results').innerHTML = h;
    };

    loadBioHome();

    let emgMap = null;
    let emgMarker = null;

    window.viewEmergencyMap = function(lat, lng, type, reporter) {
        document.getElementById('emg-map-title').innerText = type.toUpperCase() + ' EMERGENCY';
        document.getElementById('emg-map-subtitle').innerText = 'Reported By: ' + reporter;
        document.getElementById('emg-map-modal').style.display = 'block';
        
        if(!emgMap) {
            emgMap = L.map('emg-pin-map').setView([lat, lng], 18);
            L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',{maxZoom: 20, subdomains:['mt0','mt1','mt2','mt3']}).addTo(emgMap);
            setTimeout(() => { emgMap.invalidateSize(); }, 300);
        } else {
            emgMap.setView([lat, lng], 18);
            setTimeout(() => { emgMap.invalidateSize(); }, 300);
        }
        
        if(emgMarker) emgMap.removeLayer(emgMarker);
        
        const pinHtml = '<div style="background:var(--danger); color:white; width:24px; height:24px; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 0 10px red;"><i class="fa-solid fa-triangle-exclamation" style="font-size:12px;"></i></div>';
        const icon = L.divIcon({className: 'emg-pin-icon', html: pinHtml, iconSize: [24, 24], iconAnchor: [12, 12]});
        emgMarker = L.marker([lat, lng], {icon: icon}).addTo(emgMap)
            .bindPopup(`<b>${type.toUpperCase()}</b><br>Reporter: ${reporter}`).openPopup();
    };

    window.issueWarning = async (id, name) => {
        if (!confirm(`Issue a formal warning to ${name}? This will trigger a temporary ban based on their warning history.`)) return;
        const res = await fetch('/api/bio/member/warn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        const data = await res.json();
        if (data.success) {
            alert(`Warning issued to ${name}. Account is banned until ${formatPhilippineDateTime(data.banned_until)}.`);
            loadMembers();
        } else {
            alert(data.error);
        }
    };

    window.toggleActive = async (id) => {
        const res = await fetch('/api/bio/member/toggle_active', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const d = await res.json();
        if(d.success) loadMembers();
    };

    let hotspotLayers = [];
    let aiActiveType = null;

    window.toggleAIHotspots = async function(type = null) {
        const map = window.GLOBAL_MAP_INSTANCE;
        if(!map) return alert("Map not ready.");

        // Clear existing before switching
        hotspotLayers.forEach(l => map.removeLayer(l));
        hotspotLayers = [];

        window.AI_ANALYSIS_ITERATIONS = window.AI_ANALYSIS_ITERATIONS || {};
        const analysisKey = type || 'all';
        const iteration = window.AI_ANALYSIS_ITERATIONS[analysisKey] || 0;
        window.AI_ANALYSIS_ITERATIONS[analysisKey] = iteration + 1;

        const url = type
            ? `/api/emergency/analysis?type=${type}&iteration=${iteration}`
            : `/api/emergency/analysis?iteration=${iteration}`;
        const res = await fetch(url);
        const data = await res.json();
        
        if(data.success) {
            if (window.renderAiCommunityAnalysis) {
                window.renderAiCommunityAnalysis(data);
            } else {
                document.getElementById('ai-insight-box').innerText = data.insight;
                document.getElementById('ai-insight-box').style.display = 'block';
            }
            
            data.hotspots.forEach(h => {
                const circleColor = h.risk_level === 'critical' ? '#dc2626' : (h.risk_level === 'high' ? '#f97316' : '#facc15');
                const purokLabel = h.purok && h.purok !== 'Unknown' ? `Purok ${h.purok}` : 'Mapped zone';
                const householdsText = h.nearby_households ? `<br/>Nearby households: ${h.nearby_households}` : '';
                const noteText = h.predictive_note ? `<br/>${h.predictive_note}` : '';
                const validationText = h.validation_note ? `<br/><small>${h.validation_note}</small>` : '';
                const circle = L.circle([h.lat, h.lng], {
                    color: circleColor,
                    weight: 3,
                    opacity: 0.8,
                    fillColor: circleColor,
                    fillOpacity: 0.35,
                    radius: h.radius,
                    className: 'hotspot-circle'
                }).addTo(map);
                circle.bindPopup(`<b><i class="fa-solid fa-triangle-exclamation"></i> ${h.risk_label || 'Prone Area'} (${purokLabel})</b><br/>AI detected ${h.count} recurring report(s) here.${householdsText}${noteText}${validationText}`);
                hotspotLayers.push(circle);
            });
            aiActiveType = type || 'all';
        }
    };



        window.USER_ROLE = "bio";
        window.USER_ID = 1;
        window.USER_BRGY = "Mabuhay";
        window.USER_PUROK = 1;
        window.USER_HOME_LAT = null;
        window.USER_HOME_LNG = null;
        window.CURRENT_TAB = 'home';
        window.NAV_SEARCH_QUERY = '';
        window._loadedAssets = {};
        window.APP_THEME_OPTIONS = {
            dark: { label: 'Dark Mode' },
            light: { label: 'Day Mode' }
        };
        window.NOTIFICATION_SOUND_DEFINITIONS = {
            emergency: {
                defaultLabel: 'Default alarm ringtone',
                defaultSrc: 'https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg'
            },
            announcement: {
                defaultLabel: 'Default announcement bell',
                defaultSrc: 'https://actions.google.com/sounds/v1/alarms/beep_short.ogg'
            },
            acknowledgment: {
                defaultLabel: 'Default acknowledgment bell',
                defaultSrc: 'https://actions.google.com/sounds/v1/alarms/beep_short.ogg'
            },
            post: {
                defaultLabel: 'Default post bell',
                defaultSrc: 'https://actions.google.com/sounds/v1/alarms/beep_short.ogg'
            }
        };
        window.NOTIFICATION_ACTIVE_PLAYERS = {};
        window.NOTIFICATION_AUDIO_CONTEXT = null;
        window.NOTIFICATION_SERVICE_WORKER_REGISTRATION = null;
        window.NOTIFICATION_PUSH_AVAILABILITY = null;

        function getNavSearchInputs() {
            return Array.from(document.querySelectorAll('.nav-search-field'));
        }

        function readSavedEmergencyCoordinates() {
            const lat = Number(window.USER_HOME_LAT);
            const lng = Number(window.USER_HOME_LNG);
            if (Number.isFinite(lat) && Number.isFinite(lng)) {
                return { lat, lng, source: 'saved' };
            }
            return null;
        }

        function requestLiveEmergencyCoordinates() {
            if (!navigator.geolocation) {
                return Promise.resolve(null);
            }

            return new Promise(resolve => {
                navigator.geolocation.getCurrentPosition(
                    pos => resolve({
                        lat: pos.coords.latitude,
                        lng: pos.coords.longitude,
                        source: 'live'
                    }),
                    () => resolve(null),
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
                );
            });
        }

        async function getEmergencyCoordinates() {
            const liveCoordinates = await requestLiveEmergencyCoordinates();
            if (liveCoordinates) return liveCoordinates;
            return readSavedEmergencyCoordinates();
        }

        async function submitEmergencyReport(type, options = {}) {
            const successMessage = options.successMessage || 'Emergency alert sent.';
            const fallbackMessage = options.fallbackMessage || 'Live location is unavailable. Update your saved house coordinates or allow location access, then try again.';
            const coordinates = await getEmergencyCoordinates();

            if (!coordinates) {
                alert(fallbackMessage);
                return { success: false, error: 'location_unavailable' };
            }

            try {
                const res = await fetch('/api/emergency', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        type,
                        lat: coordinates.lat,
                        lng: coordinates.lng,
                        purok: window.USER_PUROK ?? 'N/A'
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.success) {
                    alert(data.error || 'Unable to send the emergency alert right now.');
                    return { success: false, error: data.error || 'request_failed' };
                }

                const usedSavedLocation = coordinates.source === 'saved';
                alert(usedSavedLocation ? `${successMessage} Saved profile coordinates were used.` : successMessage);
                return { success: true, data, usedSavedLocation };
            } catch (error) {
                alert('Unable to send the emergency alert right now.');
                return { success: false, error: 'network_error' };
            }
        }

        window.submitEmergencyReport = submitEmergencyReport;

        async function wipeBarangayPage() {
            if (window.USER_ROLE !== 'bio') {
                alert('Only BIO accounts can delete a barangay page.');
                return;
            }

            const barangayName = (window.USER_BRGY || '').trim();
            if (!barangayName) {
                alert('No barangay is assigned to this BIO account.');
                return;
            }

            const expectedText = `DELETE ${barangayName}`;
            const confirmationText = prompt(
                `This will permanently wipe the entire ${barangayName} barangay page and all its records.\n\nType exactly: ${expectedText}`
            );
            if (confirmationText === null) return;

            try {
                const res = await fetch('/api/bio/barangay/wipe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirmation_text: confirmationText })
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.success) {
                    alert(data.error || 'Unable to delete the barangay page.');
                    return;
                }

                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                    return;
                }

                window.location.reload();
            } catch (error) {
                alert('Unable to delete the barangay page right now.');
            }
        }

        window.wipeBarangayPage = wipeBarangayPage;

        function getNotificationAudioContext() {
            const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextCtor) return null;
            if (!window.NOTIFICATION_AUDIO_CONTEXT) {
                window.NOTIFICATION_AUDIO_CONTEXT = new AudioContextCtor();
            }
            return window.NOTIFICATION_AUDIO_CONTEXT;
        }

        function getNotificationSoundBoost(eventKey) {
            if (eventKey === 'emergency') return 2.7;
            if (eventKey === 'post') return 2.1;
            return 1;
        }

        function attachNotificationSoundBoost(audio, eventKey) {
            const boost = getNotificationSoundBoost(eventKey);
            audio.volume = 1;
            if (boost <= 1) return () => {};

            const context = getNotificationAudioContext();
            if (!context) return () => {};

            try {
                audio.crossOrigin = 'anonymous';
                if (context.state === 'suspended') {
                    context.resume().catch(() => {});
                }
                const sourceNode = context.createMediaElementSource(audio);
                const gainNode = context.createGain();
                gainNode.gain.value = boost;
                sourceNode.connect(gainNode);
                gainNode.connect(context.destination);
                return () => {
                    try { sourceNode.disconnect(); } catch (error) {}
                    try { gainNode.disconnect(); } catch (error) {}
                };
            } catch (error) {
                console.error('Failed to boost notification sound', error);
                return () => {};
            }
        }

        function browserSupportsBackgroundPush() {
            return 'serviceWorker' in navigator && 'PushManager' in window;
        }

        function urlBase64ToUint8Array(base64String) {
            const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
            const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
            const rawData = window.atob(base64);
            const outputArray = new Uint8Array(rawData.length);
            for (let index = 0; index < rawData.length; index += 1) {
                outputArray[index] = rawData.charCodeAt(index);
            }
            return outputArray;
        }

        async function loadNotificationPushAvailability(force = false) {
            if (!force && window.NOTIFICATION_PUSH_AVAILABILITY) {
                return window.NOTIFICATION_PUSH_AVAILABILITY;
            }

            try {
                const response = await fetch('/api/push/public-key');
                const payload = await response.json();
                window.NOTIFICATION_PUSH_AVAILABILITY = {
                    available: Boolean(payload.available && payload.publicKey),
                    publicKey: payload.publicKey || '',
                    reason: payload.reason || ''
                };
            } catch (error) {
                console.error('Failed to load web push settings', error);
                window.NOTIFICATION_PUSH_AVAILABILITY = {
                    available: false,
                    publicKey: '',
                    reason: 'Background web push could not be checked right now.'
                };
            }

            return window.NOTIFICATION_PUSH_AVAILABILITY;
        }

        async function getNotificationServiceWorkerRegistration() {
            if (!browserSupportsBackgroundPush()) return null;
            if (window.NOTIFICATION_SERVICE_WORKER_REGISTRATION) {
                return window.NOTIFICATION_SERVICE_WORKER_REGISTRATION;
            }

            try {
                window.NOTIFICATION_SERVICE_WORKER_REGISTRATION = await navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
            } catch (error) {
                console.error('Failed to register notification service worker', error);
                return null;
            }

            return window.NOTIFICATION_SERVICE_WORKER_REGISTRATION;
        }

        async function getExistingBackgroundPushSubscription() {
            const registration = await getNotificationServiceWorkerRegistration();
            if (!registration) return null;
            try {
                return await registration.pushManager.getSubscription();
            } catch (error) {
                console.error('Failed to read background push subscription', error);
                return null;
            }
        }

        window.ensureBackgroundPushSubscription = async function(options = {}) {
            const showErrors = options.showErrors !== false;
            const promptPermission = options.promptPermission === true;
            const silent = options.silent === true;

            if (!window.USER_ID) return false;
            if (!browserSupportsBackgroundPush()) {
                if (showErrors && !silent) {
                    setNotificationSettingsError('This browser can show alerts while open, but it does not support background push after the tab is closed.');
                }
                updateDesktopNotificationStatus();
                return false;
            }

            if (!('Notification' in window)) {
                if (showErrors && !silent) {
                    setNotificationSettingsError('This browser does not support popup notifications.');
                }
                updateDesktopNotificationStatus();
                return false;
            }

            let permission = Notification.permission;
            if (permission !== 'granted' && promptPermission) {
                permission = await Notification.requestPermission();
            }
            if (permission !== 'granted') {
                updateDesktopNotificationStatus();
                return false;
            }

            const pushAvailability = await loadNotificationPushAvailability();
            if (!pushAvailability.available || !pushAvailability.publicKey) {
                if (showErrors && !silent) {
                    setNotificationSettingsError(pushAvailability.reason || 'Background alerts are not configured on the server yet.');
                }
                updateDesktopNotificationStatus();
                return false;
            }

            try {
                const registration = await getNotificationServiceWorkerRegistration();
                if (!registration) {
                    throw new Error('The browser service worker could not be started for background alerts.');
                }

                let subscription = await registration.pushManager.getSubscription();
                if (!subscription) {
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(pushAvailability.publicKey)
                    });
                }

                const response = await fetch('/api/push/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(subscription.toJSON())
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.error || 'Background alerts could not be saved for this browser.');
                }

                updateDesktopNotificationStatus();
                return true;
            } catch (error) {
                console.error('Failed to enable background push alerts', error);
                if (showErrors && !silent) {
                    setNotificationSettingsError(error.message || 'Background alerts could not be enabled right now.');
                }
                updateDesktopNotificationStatus();
                return false;
            }
        };

        window.unsubscribeBackgroundPush = async function(options = {}) {
            const silent = options.silent === true;

            if (!browserSupportsBackgroundPush()) return true;

            try {
                const registration = await getNotificationServiceWorkerRegistration();
                if (!registration) return true;

                const subscription = await registration.pushManager.getSubscription();
                if (!subscription) {
                    updateDesktopNotificationStatus();
                    return true;
                }

                const endpoint = subscription.endpoint;
                await fetch('/api/push/unsubscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ endpoint })
                }).catch(() => {});
                await subscription.unsubscribe().catch(() => {});
                updateDesktopNotificationStatus();
                return true;
            } catch (error) {
                console.error('Failed to unsubscribe background push alerts', error);
                if (!silent) {
                    setNotificationSettingsError('Background alerts could not be turned off on this device.');
                }
                return false;
            }
        };

        window.handleLogout = async function(event) {
            if (event) event.preventDefault();
            try {
                await window.unsubscribeBackgroundPush({ silent: true });
            } catch (error) {
                console.error('Background push cleanup failed during logout', error);
            }
            window.location.href = '/logout';
        };

        function syncNavSearchInputs(value, sourceInput = null) {
            getNavSearchInputs().forEach(input => {
                if (input !== sourceInput) input.value = value;
            });
        }

        function getThemeStorageKey() {
            return 'ibarangay_theme_preference';
        }

        function normalizeAppTheme(theme) {
            return theme === 'light' ? 'light' : 'dark';
        }

        function loadThemePreference() {
            try {
                return normalizeAppTheme(localStorage.getItem(getThemeStorageKey()));
            } catch (error) {
                console.error('Failed to load theme preference', error);
                return 'dark';
            }
        }

        function saveThemePreference(theme) {
            try {
                localStorage.setItem(getThemeStorageKey(), normalizeAppTheme(theme));
            } catch (error) {
                console.error('Failed to save theme preference', error);
            }
        }

        function applyThemeChoice(theme) {
            const normalizedTheme = normalizeAppTheme(theme);
            document.documentElement.dataset.theme = normalizedTheme;
            window.APP_THEME = normalizedTheme;
        }

        function cloneDefaultNotificationSettings() {
            return Object.keys(window.NOTIFICATION_SOUND_DEFINITIONS).reduce((acc, key) => {
                acc[key] = { mode: 'default', customSrc: '', customName: '', customStorage: '' };
                return acc;
            }, {});
        }

        function getNotificationSoundStorageKey() {
            return `ibarangay_notification_sounds_${window.USER_ID || 'guest'}`;
        }

        function getNotificationStateStorageKey() {
            return `ibarangay_notification_state_${window.USER_ID || 'guest'}`;
        }

        function supportsNotificationSoundDatabase() {
            return typeof indexedDB !== 'undefined';
        }

        function getNotificationSoundDatabaseName() {
            return 'ibarangay_notification_audio';
        }

        function getNotificationSoundStoreName() {
            return 'sounds';
        }

        function getNotificationSoundRecordKey(eventKey) {
            return `${window.USER_ID || 'guest'}:${eventKey}`;
        }

        function getNotificationSoundObjectUrls() {
            if (!window.NOTIFICATION_SOUND_OBJECT_URLS) {
                window.NOTIFICATION_SOUND_OBJECT_URLS = {};
            }
            return window.NOTIFICATION_SOUND_OBJECT_URLS;
        }

        function revokeNotificationSoundObjectUrl(eventKey) {
            const urls = getNotificationSoundObjectUrls();
            const current = urls[eventKey];
            if (current) {
                URL.revokeObjectURL(current);
                delete urls[eventKey];
            }
        }

        function openNotificationSoundDatabase() {
            if (!supportsNotificationSoundDatabase()) {
                return Promise.reject(new Error('IndexedDB is not available in this browser.'));
            }
            if (!window._notificationSoundDbPromise) {
                window._notificationSoundDbPromise = new Promise((resolve, reject) => {
                    const request = indexedDB.open(getNotificationSoundDatabaseName(), 1);
                    request.onupgradeneeded = () => {
                        const db = request.result;
                        if (!db.objectStoreNames.contains(getNotificationSoundStoreName())) {
                            db.createObjectStore(getNotificationSoundStoreName(), { keyPath: 'id' });
                        }
                    };
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error || new Error('Unable to open the notification sound database.'));
                }).catch(error => {
                    window._notificationSoundDbPromise = null;
                    throw error;
                });
            }
            return window._notificationSoundDbPromise;
        }

        function readNotificationSoundBlob(eventKey) {
            return openNotificationSoundDatabase().then(db => new Promise((resolve, reject) => {
                const tx = db.transaction(getNotificationSoundStoreName(), 'readonly');
                const store = tx.objectStore(getNotificationSoundStoreName());
                const request = store.get(getNotificationSoundRecordKey(eventKey));
                request.onsuccess = () => {
                    const record = request.result;
                    resolve(record && record.blob ? record.blob : null);
                };
                request.onerror = () => reject(request.error || new Error('Unable to read the saved notification sound.'));
            }));
        }

        function writeNotificationSoundBlob(eventKey, blob, fileName = '') {
            return openNotificationSoundDatabase().then(db => new Promise((resolve, reject) => {
                const tx = db.transaction(getNotificationSoundStoreName(), 'readwrite');
                const store = tx.objectStore(getNotificationSoundStoreName());
                const request = store.put({
                    id: getNotificationSoundRecordKey(eventKey),
                    blob: blob,
                    fileName: fileName,
                    updatedAt: Date.now()
                });
                request.onsuccess = () => resolve(true);
                request.onerror = () => reject(request.error || new Error('Unable to save the notification sound.'));
            }));
        }

        async function deleteNotificationSoundBlob(eventKey) {
            try {
                const db = await openNotificationSoundDatabase();
                await new Promise((resolve, reject) => {
                    const tx = db.transaction(getNotificationSoundStoreName(), 'readwrite');
                    const store = tx.objectStore(getNotificationSoundStoreName());
                    const request = store.delete(getNotificationSoundRecordKey(eventKey));
                    request.onsuccess = () => resolve(true);
                    request.onerror = () => reject(request.error || new Error('Unable to remove the notification sound.'));
                });
                return true;
            } catch (error) {
                return false;
            }
        }

        function setNotificationSoundBlobSource(eventKey, blob, fileName = '') {
            revokeNotificationSoundObjectUrl(eventKey);
            const objectUrl = URL.createObjectURL(blob);
            getNotificationSoundObjectUrls()[eventKey] = objectUrl;
            const current = window.NOTIFICATION_SOUND_SETTINGS[eventKey] || cloneDefaultNotificationSettings()[eventKey];
            window.NOTIFICATION_SOUND_SETTINGS[eventKey] = {
                ...current,
                mode: 'custom',
                customSrc: objectUrl,
                customName: fileName || current.customName || 'Custom music',
                customStorage: 'indexeddb'
            };
        }

        function clearNotificationSoundCustomData(eventKey, options = {}) {
            const removePersisted = options.removePersisted !== false;
            revokeNotificationSoundObjectUrl(eventKey);
            const setting = window.NOTIFICATION_SOUND_SETTINGS[eventKey];
            if (setting) {
                setting.customSrc = '';
                setting.customName = '';
                setting.customStorage = '';
            }
            if (removePersisted) {
                deleteNotificationSoundBlob(eventKey).catch(error => {
                    console.error('Failed to remove notification sound blob', error);
                });
            }
        }

        function serializeNotificationSoundSettings() {
            const payload = cloneDefaultNotificationSettings();
            Object.keys(payload).forEach(key => {
                const current = window.NOTIFICATION_SOUND_SETTINGS[key] || {};
                const usesIndexedDb = current.customStorage === 'indexeddb';
                payload[key] = {
                    mode: ['default', 'custom', 'mute'].includes(current.mode) ? current.mode : 'default',
                    customSrc: usesIndexedDb ? '' : (current.customSrc || ''),
                    customName: current.customName || '',
                    customStorage: usesIndexedDb ? 'indexeddb' : ''
                };
            });
            return payload;
        }

        function setNotificationSettingsError(message = '') {
            const box = document.getElementById('notification-settings-error');
            if (!box) return;
            if (!message) {
                box.style.display = 'none';
                box.textContent = '';
                return;
            }
            box.textContent = message;
            box.style.display = 'block';
        }

        function loadNotificationSoundSettings() {
            const defaults = cloneDefaultNotificationSettings();
            try {
                const raw = localStorage.getItem(getNotificationSoundStorageKey());
                if (!raw) return defaults;
                const parsed = JSON.parse(raw);
                Object.keys(defaults).forEach(key => {
                    if (!parsed || typeof parsed[key] !== 'object') return;
                    defaults[key] = {
                        mode: ['default', 'custom', 'mute'].includes(parsed[key].mode) ? parsed[key].mode : 'default',
                        customSrc: parsed[key].customSrc || '',
                        customName: parsed[key].customName || '',
                        customStorage: parsed[key].customStorage === 'indexeddb' ? 'indexeddb' : ''
                    };
                });
            } catch (error) {
                console.error('Failed to load notification sound settings', error);
            }
            return defaults;
        }

        function saveNotificationSoundSettings() {
            try {
                localStorage.setItem(getNotificationSoundStorageKey(), JSON.stringify(serializeNotificationSoundSettings()));
                return true;
            } catch (error) {
                console.error('Failed to save notification sound settings', error);
                setNotificationSettingsError('Notification sound settings could not be saved in this browser right now.');
                return false;
            }
        }

        async function hydrateNotificationSoundSettings() {
            const customKeys = Object.keys(window.NOTIFICATION_SOUND_SETTINGS || {}).filter(key => {
                const setting = window.NOTIFICATION_SOUND_SETTINGS[key];
                return setting
                    && setting.mode === 'custom'
                    && setting.customStorage === 'indexeddb'
                    && !setting.customSrc;
            });

            await Promise.all(customKeys.map(async key => {
                try {
                    const blob = await readNotificationSoundBlob(key);
                    if (blob) {
                        setNotificationSoundBlobSource(key, blob, window.NOTIFICATION_SOUND_SETTINGS[key]?.customName || '');
                    } else {
                        const current = window.NOTIFICATION_SOUND_SETTINGS[key];
                        if (current) {
                            current.mode = 'default';
                            current.customName = '';
                            current.customStorage = '';
                        }
                    }
                } catch (error) {
                    console.error(`Failed to hydrate notification sound for ${key}`, error);
                }
            }));
        }

        function loadNotificationState() {
            try {
                const raw = localStorage.getItem(getNotificationStateStorageKey());
                return raw ? JSON.parse(raw) : {};
            } catch (error) {
                console.error('Failed to load notification state', error);
                return {};
            }
        }

        function saveNotificationState(state) {
            try {
                localStorage.setItem(getNotificationStateStorageKey(), JSON.stringify(state));
            } catch (error) {
                console.error('Failed to save notification state', error);
            }
        }

        window.NOTIFICATION_SOUND_SETTINGS = loadNotificationSoundSettings();
        window.NOTIFICATION_POLL_STATE = loadNotificationState();
        window.saveNotificationState = saveNotificationState;
        window.loadNotificationState = loadNotificationState;

        window.getNotificationSoundSource = function(eventKey) {
            const definition = window.NOTIFICATION_SOUND_DEFINITIONS[eventKey];
            const setting = window.NOTIFICATION_SOUND_SETTINGS[eventKey];
            if (!definition || !setting || setting.mode === 'mute') {
                return null;
            }
            if (setting.mode === 'custom' && setting.customSrc) {
                return {
                    src: setting.customSrc,
                    label: setting.customName || 'Custom music'
                };
            }
            return {
                src: definition.defaultSrc,
                label: definition.defaultLabel
            };
        };

        window.playNotificationSound = function(eventKey, options = {}) {
            const source = window.getNotificationSoundSource(eventKey);
            if (!source || !source.src) return;

            const previous = window.NOTIFICATION_ACTIVE_PLAYERS[eventKey];
            if (previous) {
                if (typeof previous._boostCleanup === 'function') previous._boostCleanup();
                previous.pause();
                previous.currentTime = 0;
            }

            const audio = new Audio(source.src);
            audio.preload = 'auto';
            audio.loop = Boolean(options.loop);
            audio.volume = typeof options.volume === 'number' ? options.volume : 1;
            audio._boostCleanup = attachNotificationSoundBoost(audio, eventKey);
            window.NOTIFICATION_ACTIVE_PLAYERS[eventKey] = audio;

            const cleanup = () => {
                if (typeof audio._boostCleanup === 'function') {
                    audio._boostCleanup();
                    audio._boostCleanup = null;
                }
                if (window.NOTIFICATION_ACTIVE_PLAYERS[eventKey] === audio) {
                    delete window.NOTIFICATION_ACTIVE_PLAYERS[eventKey];
                }
            };

            audio.addEventListener('ended', cleanup, { once: true });
            audio.addEventListener('error', cleanup, { once: true });

            const playResult = audio.play();
            if (playResult && typeof playResult.catch === 'function') {
                playResult.catch(() => {});
            }

            if (!audio.loop) {
                window.setTimeout(cleanup, 15000);
            }
        };

        window.stopNotificationSound = function(eventKey) {
            const audio = window.NOTIFICATION_ACTIVE_PLAYERS[eventKey];
            if (!audio) return;
            if (typeof audio._boostCleanup === 'function') {
                audio._boostCleanup();
                audio._boostCleanup = null;
            }
            audio.pause();
            audio.currentTime = 0;
            delete window.NOTIFICATION_ACTIVE_PLAYERS[eventKey];
        };

        function updateNotificationSoundSummary(eventKey) {
            const status = document.getElementById(`sound-status-${eventKey}`);
            if (!status) return;
            const setting = window.NOTIFICATION_SOUND_SETTINGS[eventKey];
            const source = window.getNotificationSoundSource(eventKey);
            if (setting && setting.mode === 'custom' && !source && setting.customName) {
                status.textContent = `${setting.customName} (loading...)`;
                status.classList.remove('muted');
                return;
            }
            if (!source) {
                status.textContent = 'Muted';
                status.classList.add('muted');
                return;
            }
            status.textContent = source.label;
            status.classList.remove('muted');
        }

        async function updateDesktopNotificationStatus() {
            const status = document.getElementById('desktop-alert-status');
            if (!status) return;
            const setStatus = (label, muted) => {
                status.textContent = label;
                status.classList.toggle('muted', Boolean(muted));
            };

            if (!('Notification' in window)) {
                setStatus('Not Supported', true);
                return;
            }

            if (Notification.permission === 'denied') {
                setStatus('Blocked', true);
                return;
            }

            const pushSupported = browserSupportsBackgroundPush();
            const pushAvailability = await loadNotificationPushAvailability();
            let hasBackgroundSubscription = false;

            if (Notification.permission === 'granted' && pushSupported && pushAvailability.available) {
                const subscription = await getExistingBackgroundPushSubscription();
                hasBackgroundSubscription = Boolean(subscription);
            }

            if (Notification.permission === 'granted') {
                if (hasBackgroundSubscription) {
                    setStatus('Enabled + Background', false);
                } else if (pushSupported && pushAvailability.available) {
                    setStatus('Enabled', false);
                } else {
                    setStatus('Enabled (Open Browser)', false);
                }
                return;
            }

            if (!pushSupported || !pushAvailability.available) {
                setStatus('Open Browser Only', true);
                return;
            }

            setStatus('Not Enabled', true);
        }

        window.renderNotificationSettings = function() {
            document.querySelectorAll('.sound-setting-card').forEach(card => {
                const roles = String(card.dataset.roles || '').split(',').map(role => role.trim()).filter(Boolean);
                const isAllowed = roles.length === 0 || roles.includes(window.USER_ROLE);
                card.style.display = isAllowed ? '' : 'none';
            });

            updateDesktopNotificationStatus();
            Object.keys(window.NOTIFICATION_SOUND_DEFINITIONS).forEach(updateNotificationSoundSummary);
        };

        hydrateNotificationSoundSettings().then(() => {
            if (typeof window.renderNotificationSettings === 'function') {
                window.renderNotificationSettings();
            }
            if (window.USER_ID && 'Notification' in window && Notification.permission === 'granted') {
                window.ensureBackgroundPushSubscription({
                    showErrors: false,
                    promptPermission: false,
                    silent: true
                });
            }
        }).catch(error => {
            console.error('Failed to restore custom notification sounds', error);
        });

        window.openNotificationSettings = function() {
            const modal = document.getElementById('notification-settings-modal');
            if (!modal) return;
            setNotificationSettingsError('');
            window.renderNotificationSettings();
            modal.style.display = 'flex';
        };

        window.closeNotificationSettings = function() {
            const modal = document.getElementById('notification-settings-modal');
            if (modal) modal.style.display = 'none';
            setNotificationSettingsError('');
        };

        window.openProfileInfo = function() {
            const modal = document.getElementById('profile-info-modal');
            if (modal) modal.style.display = 'flex';
        };

        window.closeProfileInfo = function() {
            const modal = document.getElementById('profile-info-modal');
            if (modal) modal.style.display = 'none';
        };

        window.previewNotificationSound = function(eventKey) {
            setNotificationSettingsError('');
            const source = window.getNotificationSoundSource(eventKey);
            if (!source) {
                const setting = window.NOTIFICATION_SOUND_SETTINGS[eventKey];
                if (setting && setting.mode === 'custom' && setting.customName) {
                    setNotificationSettingsError('Your custom music is still loading. Please try again in a moment.');
                } else {
                    setNotificationSettingsError('This alert is muted right now.');
                }
                return;
            }
            window.stopNotificationSound(eventKey);
            window.playNotificationSound(eventKey);
        };

        window.setNotificationSoundMode = function(eventKey, mode) {
            if (!window.NOTIFICATION_SOUND_SETTINGS[eventKey]) return;
            window.stopNotificationSound(eventKey);
            window.NOTIFICATION_SOUND_SETTINGS[eventKey] = {
                ...window.NOTIFICATION_SOUND_SETTINGS[eventKey],
                mode: mode
            };
            if (mode !== 'custom') {
                clearNotificationSoundCustomData(eventKey);
            }
            if (saveNotificationSoundSettings()) {
                setNotificationSettingsError('');
                updateNotificationSoundSummary(eventKey);
            }
        };

        window.requestDesktopNotificationPermission = async function() {
            setNotificationSettingsError('');
            if (!('Notification' in window)) {
                setNotificationSettingsError('This browser does not support desktop popup notifications.');
                updateDesktopNotificationStatus();
                return;
            }

            try {
                const permission = Notification.permission === 'granted'
                    ? 'granted'
                    : await Notification.requestPermission();
                if (permission !== 'granted') {
                    setNotificationSettingsError('Desktop popup notifications were not enabled.');
                    updateDesktopNotificationStatus();
                    return;
                }

                const subscribed = await window.ensureBackgroundPushSubscription({
                    showErrors: false,
                    promptPermission: false,
                    silent: true
                });
                const pushAvailability = await loadNotificationPushAvailability();

                if (!subscribed) {
                    if (!browserSupportsBackgroundPush()) {
                        setNotificationSettingsError('Popup alerts are enabled, but this browser only supports alerts while the app stays open.');
                    } else if (!pushAvailability.available) {
                        setNotificationSettingsError(pushAvailability.reason || 'Popup alerts are enabled. Background alerts after the tab is closed still need server push setup.');
                    }
                } else {
                    setNotificationSettingsError('');
                }
                updateDesktopNotificationStatus();
            } catch (error) {
                console.error('Notification permission failed', error);
                setNotificationSettingsError('Desktop popup notifications could not be enabled.');
                updateDesktopNotificationStatus();
            }
        };

        window.showDesktopNotification = function(eventKey, title, body, options = {}) {
            if (!('Notification' in window) || Notification.permission !== 'granted') {
                return null;
            }

            const notification = new Notification(title, {
                body: body,
                tag: options.tag || `ibarangay-${eventKey}`,
                requireInteraction: options.requireInteraction !== false,
                silent: true
            });

            if (!window.ACTIVE_DESKTOP_NOTIFICATIONS) {
                window.ACTIVE_DESKTOP_NOTIFICATIONS = {};
            }

            if (window.ACTIVE_DESKTOP_NOTIFICATIONS[eventKey]) {
                window.ACTIVE_DESKTOP_NOTIFICATIONS[eventKey].close();
            }
            window.ACTIVE_DESKTOP_NOTIFICATIONS[eventKey] = notification;

            window.playNotificationSound(eventKey, { loop: options.loopSound !== false });

            const stopAndCleanup = () => {
                window.stopNotificationSound(eventKey);
                if (window.ACTIVE_DESKTOP_NOTIFICATIONS[eventKey] === notification) {
                    delete window.ACTIVE_DESKTOP_NOTIFICATIONS[eventKey];
                }
            };

            notification.onclick = () => {
                if (typeof window.focus === 'function') {
                    window.focus();
                }
                stopAndCleanup();
                notification.close();
            };

            notification.onclose = stopAndCleanup;
            window.setTimeout(() => {
                stopAndCleanup();
                notification.close();
            }, options.timeoutMs || 60000);

            return notification;
        };

        window.triggerNotificationSoundUpload = function(eventKey) {
            const input = document.getElementById(`sound-upload-${eventKey}`);
            if (input) input.click();
        };

        window.handleNotificationSoundUpload = async function(eventKey, event) {
            const file = event.target.files && event.target.files[0];
            if (!file) return;
            if (file.size > 20 * 1024 * 1024) {
                setNotificationSettingsError('Please choose an audio file smaller than 20 MB.');
                event.target.value = '';
                return;
            }
            try {
                await writeNotificationSoundBlob(eventKey, file, file.name);
                window.stopNotificationSound(eventKey);
                setNotificationSoundBlobSource(eventKey, file, file.name);
                if (saveNotificationSoundSettings()) {
                    setNotificationSettingsError('');
                    updateNotificationSoundSummary(eventKey);
                }
            } catch (error) {
                console.error('Failed to save custom notification music', error);
                setNotificationSettingsError('The selected audio file could not be saved. Please try again with the same file or a different browser.');
            } finally {
                event.target.value = '';
            }
        };

        window.resetAllNotificationSounds = function() {
            Object.keys(window.NOTIFICATION_ACTIVE_PLAYERS).forEach(window.stopNotificationSound);
            Object.keys(window.NOTIFICATION_SOUND_SETTINGS || {}).forEach(eventKey => {
                clearNotificationSoundCustomData(eventKey);
            });
            window.NOTIFICATION_SOUND_SETTINGS = cloneDefaultNotificationSettings();
            if (saveNotificationSoundSettings()) {
                setNotificationSettingsError('');
                window.renderNotificationSettings();
            }
        };

        window.stopAllDesktopNotificationSounds = function() {
            Object.keys(window.NOTIFICATION_ACTIVE_PLAYERS || {}).forEach(window.stopNotificationSound);
        };

        window.renderAppearanceSettings = function() {
            const theme = normalizeAppTheme(window.APP_THEME);
            document.querySelectorAll('[data-theme-option]').forEach(card => {
                const isActive = card.dataset.themeOption === theme;
                card.classList.toggle('active', isActive);
                card.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                const badge = card.querySelector('.theme-option-badge');
                if (badge) badge.textContent = isActive ? 'Active' : 'Available';
            });

            const status = document.getElementById('theme-setting-status');
            if (status) {
                status.textContent = `${window.APP_THEME_OPTIONS[theme].label} is active on this browser.`;
            }
        };

        window.setAppTheme = function(theme) {
            const normalizedTheme = normalizeAppTheme(theme);
            applyThemeChoice(normalizedTheme);
            saveThemePreference(normalizedTheme);
            window.renderAppearanceSettings();
        };

        window.openAppearanceSettings = function() {
            const modal = document.getElementById('appearance-settings-modal');
            if (!modal) return;
            window.renderAppearanceSettings();
            modal.style.display = 'flex';
        };

        window.closeAppearanceSettings = function() {
            const modal = document.getElementById('appearance-settings-modal');
            if (modal) modal.style.display = 'none';
        };

        window.APP_THEME = loadThemePreference();
        applyThemeChoice(window.APP_THEME);

        window.addEventListener('focus', () => {
            window.stopAllDesktopNotificationSounds();
        });

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                window.stopAllDesktopNotificationSounds();
            }
        });

        function loadStylesheetOnce(href, key) {
            if (window._loadedAssets[key]) return window._loadedAssets[key];
            window._loadedAssets[key] = new Promise((resolve, reject) => {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = href;
                link.onload = () => resolve(true);
                link.onerror = reject;
                document.head.appendChild(link);
            }).catch(() => false);
            return window._loadedAssets[key];
        }

        function loadScriptOnce(src, key) {
            if (window._loadedAssets[key]) return window._loadedAssets[key];
            window._loadedAssets[key] = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src;
                script.async = true;
                script.onload = () => resolve(true);
                script.onerror = reject;
                document.body.appendChild(script);
            }).catch(() => false);
            return window._loadedAssets[key];
        }

        window.loadLeafletAssets = async function() {
            const cssOk = await loadStylesheetOnce('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', 'leaflet-css');
            const jsOk = await loadScriptOnce('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', 'leaflet-js');
            return Boolean(cssOk && jsOk && window.L);
        };

        // Load optional icon styles only after the page has fully finished loading.
        window.addEventListener('load', () => {
            setTimeout(() => {
                loadStylesheetOnce('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css', 'fontawesome');
            }, 0);
        });
        
        function switchTab(tabId, event) {
            if(event) event.preventDefault();
            const isSameTab = window.CURRENT_TAB === tabId;
            window.CURRENT_TAB = tabId;
            
            window.dispatchEvent(new CustomEvent('tabChanged', {
                detail: {
                    tabId: tabId,
                    forced: isSameTab
                }
            }));
            
            document.querySelectorAll('.tab-section').forEach(sec => sec.classList.remove('active'));
            document.querySelectorAll('.nav-icon, .mobile-shortcut-btn').forEach(icon => icon.classList.remove('active'));
            
            const target = document.getElementById('tab-' + tabId);
            if(target) target.classList.add('active');

            document.querySelectorAll(`[data-tab-target="${tabId}"]`).forEach(icon => icon.classList.add('active'));

            if (window.innerWidth <= 768) {
                window.requestAnimationFrame(() => {
                    window.scrollTo({
                        top: 0,
                        behavior: 'smooth'
                    });
                });
            }
        }

        function applyRequestedTabFromLocation() {
            const validTabs = new Set(
                Array.from(document.querySelectorAll('.tab-section'))
                    .map(section => section.id.replace(/^tab-/, ''))
                    .filter(Boolean)
            );

            const params = new URLSearchParams(window.location.search);
            const requestedTab = (params.get('tab') || window.location.hash.replace(/^#/, '') || '').trim().toLowerCase();
            if (!requestedTab || !validTabs.has(requestedTab)) return;

            switchTab(requestedTab);
            params.delete('tab');
            const nextQuery = params.toString();
            const cleanUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`;
            window.history.replaceState({}, '', cleanUrl);
        }

        applyRequestedTabFromLocation();

        function toggleSidebar() {
            const sidebar = document.getElementById('main-sidebar');
            const overlay = document.getElementById('sidebar-overlay');
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
            if(sidebar.classList.contains('active')) {
                loadSidebarStats();
            }
        }

        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        const PH_TIME_ZONE = 'Asia/Manila';

        function getPhilippineFormatter(options = {}) {
            return new Intl.DateTimeFormat('en-PH', {
                timeZone: PH_TIME_ZONE,
                ...options
            });
        }

        function parsePhilippineDateValue(value) {
            if (value === null || value === undefined || value === '') return null;
            if (value instanceof Date) {
                return Number.isNaN(value.getTime()) ? null : value;
            }

            const raw = String(value).trim();
            if (!raw) return null;

            if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
                const [year, month, day] = raw.split('-').map(Number);
                return new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
            }

            if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(raw)) {
                return new Date(`${raw}Z`);
            }

            const parsed = new Date(raw);
            return Number.isNaN(parsed.getTime()) ? null : parsed;
        }

        function formatPhilippineDateTime(value, options = {}) {
            const parsed = parsePhilippineDateValue(value);
            if (!parsed) return value ? String(value) : '';
            return getPhilippineFormatter({
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                ...options
            }).format(parsed);
        }

        function formatPhilippineDate(value, options = {}) {
            const parsed = parsePhilippineDateValue(value);
            if (!parsed) return value ? String(value) : '';
            return getPhilippineFormatter({
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                ...options
            }).format(parsed);
        }

        function getPhilippineDateParts(date = new Date()) {
            return Object.fromEntries(
                getPhilippineFormatter({
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit'
                })
                    .formatToParts(date)
                    .filter(part => part.type !== 'literal')
                    .map(part => [part.type, part.value])
            );
        }

        function getPhilippineTodayInputValue() {
            const parts = getPhilippineDateParts();
            return `${parts.year}-${parts.month}-${parts.day}`;
        }

        function getPhilippineCurrentYear() {
            return Number(getPhilippineDateParts().year);
        }

        window.PH_TIME_ZONE = PH_TIME_ZONE;
        window.formatPhilippineDateTime = formatPhilippineDateTime;
        window.formatPhilippineDate = formatPhilippineDate;
        window.getPhilippineTodayInputValue = getPhilippineTodayInputValue;
        window.getPhilippineCurrentYear = getPhilippineCurrentYear;

        function roleLabel(role) {
            if (role === 'bio') return 'Official / BIO';
            if (role === 'official') return 'Official';
            if (role === 'resident') return 'Resident';
            return role || 'Member';
        }

        function officialPositionLabel(user) {
            if (user?.position) return user.position;
            if (user?.author_position) return user.author_position;
            if (user?.role === 'bio' || user?.author_role === 'bio' || user?.role === 'official' || user?.author_role === 'official') {
                return 'Barangay Official';
            }
            return '';
        }

        function getMentionDisplayNames(post) {
            if (Array.isArray(post?.mention_names) && post.mention_names.length) {
                return post.mention_names;
            }

            const mentions = Array.isArray(post?.mentions) ? post.mentions : [];
            return mentions
                .map(mention => typeof mention === 'string'
                    ? mention
                    : (mention?.name || mention?.full_name || ''))
                .filter(Boolean);
        }

        function postMatchesSearch(post, query) {
            if (!query) return true;
            const normalized = String(query).toLowerCase();
            const authorName = String(post.author_name || '').toLowerCase();
            const authorPosition = String(post.author_position || '').toLowerCase();
            const content = String(post.content || '').toLowerCase();
            const location = String(post.location || '').toLowerCase();
            const mentions = getMentionDisplayNames(post);

            return authorName.includes(normalized)
                || authorPosition.includes(normalized)
                || content.includes(normalized)
                || location.includes(normalized)
                || mentions.some(mention => String(mention).toLowerCase().includes(normalized));
        }

        window.getMentionDisplayNames = getMentionDisplayNames;
        window.postMatchesSearch = postMatchesSearch;

        window.RATING_SCHEDULE_CACHE = null;

        async function loadRatingScheduleStatus(force = false) {
            if (!force && window.RATING_SCHEDULE_CACHE) return window.RATING_SCHEDULE_CACHE;
            try {
                const res = await fetch('/api/ratings/schedule');
                if (!res.ok) throw new Error('Unable to load rating schedule');
                window.RATING_SCHEDULE_CACHE = await res.json();
            } catch (error) {
                window.RATING_SCHEDULE_CACHE = {
                    is_configured: false,
                    is_open: true,
                    message: 'Rating schedule status is unavailable.'
                };
            }
            return window.RATING_SCHEDULE_CACHE;
        }

        function buildRatingActionHtml(officialId) {
            const schedule = window.RATING_SCHEDULE_CACHE;
            if (schedule && !schedule.is_open) {
                return `
                    <button class="btn btn-secondary" style="width:100%; margin-top:5px; padding:8px; opacity:0.7;" disabled>Rating Closed</button>
                    <small style="display:block; text-align:center; margin-top:5px; color:var(--warning); font-size:10px;">${escapeHtml(schedule.message || 'Ratings are currently closed.')}</small>
                `;
            }

            return `<button class="btn btn-primary" style="width:100%; margin-top:5px; padding:8px;" onclick="submitIndividualRating(${officialId})">Rate Official</button>`;
        }

        window.RATING_SUMMARY_CACHE = null;

        async function loadRatingSummary(force = false) {
            if (!force && window.RATING_SUMMARY_CACHE) return window.RATING_SUMMARY_CACHE;
            const res = await fetch('/api/ratings/summary');
            if (!res.ok) throw new Error('Unable to load rating summary');
            const data = await res.json();
            window.RATING_SUMMARY_CACHE = data.summary;
            return window.RATING_SUMMARY_CACHE;
        }

        function getOfficialVoteSummary(officialId) {
            const officials = window.RATING_SUMMARY_CACHE?.officials || [];
            return officials.find(item => Number(item.official_id) === Number(officialId));
        }

        function buildVoteStatsHtml(officialId) {
            const summary = getOfficialVoteSummary(officialId);
            if (!summary) return '';
            return `
                <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
                    <span class="search-chip">${escapeHtml(summary.initials)}</span>
                    <span class="search-chip limited">${summary.total_votes} vote${summary.total_votes === 1 ? '' : 's'}</span>
                    <span class="search-chip ${summary.total_votes ? 'full' : 'limited'}">Avg ${Number(summary.average_rating || 0).toFixed(2)}</span>
                </div>
            `;
        }

        function buildRatingSummaryHtml(summary) {
            const officials = summary?.officials || [];
            if (!officials.length) {
                return '<p class="text-muted">No officials are available for this barangay yet.</p>';
            }

            return officials.map((official, index) => {
                const purokRows = (official.ratings_by_purok || []).length
                    ? official.ratings_by_purok.map(row => `
                        <tr>
                            <td style="padding:6px; border-bottom:1px solid var(--card-border);">Purok ${escapeHtml(row.purok)}</td>
                            <td style="padding:6px; border-bottom:1px solid var(--card-border);">${row.total_votes}</td>
                            <td style="padding:6px; border-bottom:1px solid var(--card-border);">${Number(row.average_rating || 0).toFixed(2)}</td>
                        </tr>
                    `).join('')
                    : '<tr><td colspan="3" class="text-muted" style="padding:6px;">No votes yet.</td></tr>';

                return `
                    <div style="border:1px solid var(--card-border); border-radius:16px; padding:15px; margin-bottom:12px; background:rgba(255,255,255,0.03);">
                        <div style="display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;">
                            <div>
                                <strong style="font-size:17px;">#${index + 1} ${escapeHtml(official.full_name)}</strong>
                                <div style="color:var(--primary); font-size:12px; font-weight:800; margin-top:3px;">${escapeHtml(official.position || 'Barangay Official')}</div>
                            </div>
                            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                                <span class="search-chip">${escapeHtml(official.initials)}</span>
                                <span class="search-chip limited">${official.total_votes} vote${official.total_votes === 1 ? '' : 's'}</span>
                                <span class="search-chip full">Avg ${Number(official.average_rating || 0).toFixed(2)}</span>
                            </div>
                        </div>
                        <table style="width:100%; border-collapse:collapse; margin-top:12px; font-size:13px;">
                            <thead>
                                <tr>
                                    <th style="text-align:left; padding:6px; border-bottom:1px solid var(--card-border);">Purok / All</th>
                                    <th style="text-align:left; padding:6px; border-bottom:1px solid var(--card-border);">Votes</th>
                                    <th style="text-align:left; padding:6px; border-bottom:1px solid var(--card-border);">Average</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td style="padding:6px; border-bottom:1px solid var(--card-border);"><strong>All</strong></td>
                                    <td style="padding:6px; border-bottom:1px solid var(--card-border);">${official.total_votes}</td>
                                    <td style="padding:6px; border-bottom:1px solid var(--card-border);">${Number(official.average_rating || 0).toFixed(2)}</td>
                                </tr>
                                ${purokRows}
                            </tbody>
                        </table>
                    </div>
                `;
            }).join('');
        }

        async function openRatingSummary() {
            const modal = document.getElementById('rating-summary-modal');
            const content = document.getElementById('rating-summary-content');
            if (!modal || !content) return;
            modal.style.display = 'block';
            content.innerHTML = '<p class="text-muted">Loading vote summary...</p>';
            try {
                const summary = await loadRatingSummary(true);
                content.innerHTML = buildRatingSummaryHtml(summary);
            } catch (error) {
                content.innerHTML = '<p class="text-muted">Unable to load vote summary right now.</p>';
            }
        }

        function closeRatingSummary() {
            const modal = document.getElementById('rating-summary-modal');
            if (modal) modal.style.display = 'none';
        }

        window.loadRatingScheduleStatus = loadRatingScheduleStatus;
        window.buildRatingActionHtml = buildRatingActionHtml;
        window.loadRatingSummary = loadRatingSummary;
        window.buildVoteStatsHtml = buildVoteStatsHtml;
        window.openRatingSummary = openRatingSummary;
        window.closeRatingSummary = closeRatingSummary;

        function buildSearchProfileHtml(profile) {
            const fields = Array.isArray(profile.fields) ? profile.fields : [];
            const fieldHtml = fields.length
                ? `<div class="search-field-list">${fields.map(field => `
                    <div class="search-field">
                        <span class="search-field-label">${escapeHtml(field.label)}</span>
                        <div class="search-field-value">${escapeHtml(field.value)}</div>
                    </div>
                `).join('')}</div>`
                : `<div class="search-empty" style="padding:14px; margin-top:14px;">No additional profile details are available for your role.</div>`;

            return `
                <div class="search-profile-card">
                    <div class="search-profile-top">
                        <img src="${escapeHtml(profile.pic_url || '/static/default-avatar.svg')}" class="search-avatar" alt="${escapeHtml(profile.full_name)}">
                        <div style="min-width:0;">
                            <div style="font-size:16px; font-weight:800;">${escapeHtml(profile.full_name)}</div>
                            ${profile.position ? `<div class="text-muted" style="font-size:13px; margin-top:4px;">${escapeHtml(profile.position)}</div>` : ''}
                            <div class="search-role-line">
                                <span class="search-chip">${escapeHtml(roleLabel(profile.role))}</span>
                                <span class="search-chip ${profile.access_level === 'full' ? 'full' : 'limited'}">${profile.access_level === 'full' ? 'Full View' : 'Limited View'}</span>
                            </div>
                        </div>
                    </div>
                    ${fieldHtml}
                </div>
            `;
        }

        function buildSearchMediaHtml(post) {
            const media = Array.isArray(post.media_urls) ? post.media_urls : [];
            if (media.length > 0) {
                return `
                    <div class="post-media-grid" style="grid-template-columns: repeat(${media.length > 1 ? 2 : 1}, 1fr); margin-top:12px;">
                        ${media.map(item => {
                            const mediaUrl = typeof item === 'string' ? item : item.url;
                            const type = typeof item === 'object' ? item.type : '';
                            const isVideo = type === 'video' || /\.(mp4|webm|ogg)$/i.test(mediaUrl || '');
                            return isVideo
                                ? `<video src="${escapeHtml(mediaUrl || '')}" controls preload="metadata"></video>`
                                : `<img src="${escapeHtml(mediaUrl || '')}" alt="Search result media" loading="lazy">`;
                        }).join('')}
                    </div>
                `;
            }

            if (post.image_url) {
                return `<img src="${escapeHtml(post.image_url)}" alt="Search result image" style="width:100%; border-radius:12px; margin-top:12px;" loading="lazy">`;
            }

            return '';
        }

        function buildSearchPostHtml(post) {
            const mentions = Array.isArray(post.mentions) ? post.mentions : [];
            const reasons = Array.isArray(post.match_reasons) ? post.match_reasons : [];
            const authorPosition = officialPositionLabel(post);
            const mentionHtml = mentions.length
                ? `<div class="search-match-list" style="margin-top:12px;">${mentions.map(name => `<span class="mention-tag">@${escapeHtml(name)}</span>`).join('')}</div>`
                : '';
            const reasonHtml = reasons.length
                ? `<div class="search-match-list">${reasons.map(reason => `<span class="search-chip limited">${escapeHtml(reason)}</span>`).join('')}</div>`
                : '';

            return `
                <div class="search-post-card">
                    <div class="search-post-meta">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <img src="${escapeHtml(post.author_pic || '/static/default-avatar.svg')}" class="search-avatar" alt="${escapeHtml(post.author_name)}" style="width:40px; height:40px;">
                            <div>
                                <div style="font-weight:700;">${escapeHtml(post.author_name || 'Unknown')}</div>
                                ${authorPosition ? `<small style="color:var(--primary); font-size:11px; font-weight:800; display:block; margin-top:2px;">${escapeHtml(authorPosition)}</small>` : ''}
                                <small class="text-muted">${escapeHtml(formatPhilippineDateTime(post.timestamp))}</small>
                            </div>
                        </div>
                        ${reasonHtml}
                    </div>
                    <div style="line-height:1.6; white-space:pre-wrap;">${escapeHtml(post.content || '')}</div>
                    ${post.location ? `<div class="location-tag"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(post.location)}</div>` : ''}
                    ${mentionHtml}
                    ${buildSearchMediaHtml(post)}
                </div>
            `;
        }

        function hideGlobalSearch() {
            const panel = document.getElementById('global-search-panel');
            const label = document.getElementById('global-search-label');
            const results = document.getElementById('global-search-results');
            if (panel) panel.classList.remove('active');
            if (label) label.textContent = '';
            if (results) results.innerHTML = '';
        }

        function clearGlobalSearch() {
            syncNavSearchInputs('');
            window.NAV_SEARCH_QUERY = '';
            hideGlobalSearch();
            window.dispatchEvent(new CustomEvent('nameSearchChanged', {
                detail: {
                    query: '',
                    tabId: window.CURRENT_TAB
                }
            }));
        }

        function renderGlobalSearchResults(data) {
            const results = document.getElementById('global-search-results');
            if (!results) return;

            const profiles = Array.isArray(data.profiles) ? data.profiles : [];
            const posts = Array.isArray(data.posts) ? data.posts : [];

            results.innerHTML = `
                <div class="global-search-layout">
                    <section class="search-section">
                        <div class="search-section-header">
                            <h4 style="margin:0;">Matching Profiles</h4>
                            <span class="search-count">${profiles.length} result${profiles.length === 1 ? '' : 's'}</span>
                        </div>
                        ${profiles.length ? `<div class="search-profile-grid">${profiles.map(buildSearchProfileHtml).join('')}</div>` : '<div class="search-empty">No residents or officials matched that name.</div>'}
                    </section>
                    <section class="search-section">
                        <div class="search-section-header">
                            <h4 style="margin:0;">Related Posts</h4>
                            <span class="search-count">${posts.length} result${posts.length === 1 ? '' : 's'}</span>
                        </div>
                        ${posts.length ? `<div class="search-post-list">${posts.map(buildSearchPostHtml).join('')}</div>` : '<div class="search-empty">No posts found where this person was posted, named, tagged, or mentioned.</div>'}
                    </section>
                </div>
            `;
        }

        window._searchRequestId = 0;
        async function runGlobalNameSearch(query) {
            const panel = document.getElementById('global-search-panel');
            const label = document.getElementById('global-search-label');
            const results = document.getElementById('global-search-results');
            if (!panel || !label || !results) return;

            if (!query) {
                hideGlobalSearch();
                return;
            }

            const requestId = ++window._searchRequestId;
            panel.classList.add('active');
            label.textContent = query;
            results.innerHTML = '<div class="search-empty">Searching profiles and tagged posts...</div>';

            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const data = await res.json();
                if (requestId !== window._searchRequestId) return;
                renderGlobalSearchResults(data);
            } catch (error) {
                if (requestId !== window._searchRequestId) return;
                results.innerHTML = '<div class="search-empty">Unable to load search results right now.</div>';
            }
        }

        let navSearchTimer = null;
        window.addEventListener('load', () => {
            const searchInputs = getNavSearchInputs();
            if (!searchInputs.length) return;
            searchInputs.forEach(searchInput => {
                searchInput.addEventListener('input', (event) => {
                    const rawValue = event.target.value;
                    syncNavSearchInputs(rawValue, event.target);
                    clearTimeout(navSearchTimer);
                    navSearchTimer = setTimeout(() => {
                        window.NAV_SEARCH_QUERY = rawValue.trim();
                        window.dispatchEvent(new CustomEvent('nameSearchChanged', {
                            detail: {
                                query: window.NAV_SEARCH_QUERY,
                                tabId: window.CURRENT_TAB
                            }
                        }));
                        runGlobalNameSearch(window.NAV_SEARCH_QUERY);
                    }, 150);
                });
            });
        });

        window.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            window.closeAppearanceSettings();
            window.closeNotificationSettings();
            window.closeProfileInfo();
        });

        async function loadSidebarStats() {
            try {
                const res = await fetch('/api/dashboard/stats');
                const data = await res.json();
                document.getElementById('stat-members').innerText = data.members;
                document.getElementById('stat-officials').innerText = data.officials;
                document.getElementById('stat-incidents').innerText = data.incidents;
                document.getElementById('stat-health').innerText = data.health;
                document.getElementById('stat-posts').innerText = data.posts;
            } catch (e) {
                console.error("Failed to load stats", e);
            }
        }
    




        // Setup Map globally if element exists
        window.initGlobalMap = async function(mapId, elementsData, isLimited) {
            if(!document.getElementById(mapId)) return;
            const leafletReady = await window.loadLeafletAssets();
            if(!leafletReady || !window.L) return;
            const mapHtml = document.getElementById(mapId);
            mapHtml.innerHTML = '';

            if (window.GLOBAL_MAP_INSTANCE) {
                window.GLOBAL_MAP_INSTANCE.remove();
                window.GLOBAL_MAP_INSTANCE = null;
            }
            
            // Focus on roughly center of Philippines. Wait, wait for elements.
            let center = [12.8797, 121.7740]; // Default PH center
            let zoom = 5;
            
            const map = L.map(mapId).setView(center, zoom);
            window.GLOBAL_MAP_INSTANCE = map;
            
            L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',{
                maxZoom: 20,
                subdomains:['mt0','mt1','mt2','mt3']
            }).addTo(map);

            if(elementsData.length > 0 && elementsData[0].lat && elementsData[0].lng) {
                map.setView([elementsData[0].lat, elementsData[0].lng], 15);
            } else if (window.USER_BRGY) {
                fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(window.USER_BRGY + ', Philippines')}`)
                .then(r => r.json())
                .then(data => {
                    if(data.length > 0) map.setView([data[0].lat, data[0].lon], 15);
                })
                .catch(() => {});
            }

            elementsData.forEach(user => {
                if(!user.lat || !user.lng) return;
                const marker = L.marker([user.lat, user.lng]).addTo(map);
                const position = officialPositionLabel(user);
                let popup = `<b>${escapeHtml(user.full_name)}</b>`;
                if(position) popup += `<br/><small style="color:#60a5fa; font-weight:700;">${escapeHtml(position)}</small>`;
                popup += `<br/>Role: ${escapeHtml(roleLabel(user.role))}`;
                if(!isLimited) popup += `<br/>Income: ₱${user.monthly_income || 0}<br/>Purok: ${user.purok || 'N/A'}`;
                if(user.pic_url) popup += `<br/><img src="${escapeHtml(user.pic_url)}" alt="pic" style="width:50px;height:50px;border-radius:5px;object-fit:cover;margin-top:5px;"/>`;
                marker.bindPopup(popup);
                marker.bindTooltip(`<b>${escapeHtml(user.full_name)}</b><br><small style="color:#aaa">${escapeHtml(position || roleLabel(user.role))}</small>`, {direction: 'top', offset: [0, -10], opacity: 0.9});
            });
        };
    