
        (function() {
            try {
                const savedTheme = localStorage.getItem('ibarangay_theme_preference');
                document.documentElement.dataset.theme = savedTheme === 'light' ? 'light' : 'dark';
            } catch (error) {
                document.documentElement.dataset.theme = 'dark';
            }
        })();
    


    const residentTabState = {
        homeLoaded: false,
        membersLoaded: false,
        welfareLoaded: false,
        officialsLoaded: false,
        notificationsLoaded: false,
        historyLoaded: false,
        mapLoaded: false
    };

    async function triggerEmergency(type) {
        if (!navigator.geolocation) return alert("Geolocation not supported. Call hotline.");
        navigator.geolocation.getCurrentPosition(async (pos) => {
            const body = { type, lat: pos.coords.latitude, lng: pos.coords.longitude, purok: "N/A" };
            await fetch('/api/emergency', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            alert('🚨 Emergency Alert Sent to Brgy Hall. Assistance is on the way.');
        });
    }

    async function triggerEmergency(type) {
        const result = await window.submitEmergencyReport(type, {
            successMessage: 'Emergency alert sent to Brgy Hall. Assistance is on the way.',
            fallbackMessage: 'Location is unavailable right now. Allow location access or update your saved house coordinates, then try again.'
        });
        if (!result?.success) return;
    }

    async function loadFeed() {
        const [annRes, evRes] = await Promise.all([fetch('/api/announcements'), fetch('/api/events')]);
        const anns = await annRes.json();
        const evs = await evRes.json();
        let html = '';
        anns.forEach(a => {
            html += `<div style="border-left:3px solid var(--primary); padding-left:10px; margin-bottom:15px;">
                <small style="color:var(--text-muted)">📢 Announcement (${formatPhilippineDate(a.date)})</small>
                <p style="margin:5px 0; font-size:14px;">${a.message}</p>
            </div>`;
        });
        evs.forEach(e => {
            html += `<div style="border-left:3px solid var(--secondary); padding-left:10px; margin-bottom:15px;">
                <small style="color:var(--text-muted)">🏆 ${e.type.toUpperCase()} • ${formatPhilippineDateTime(e.date)}</small>
                <p style="margin:5px 0; font-weight:800; font-size:14px;">${e.title}</p>
                <p style="margin:0; font-size:12px; color:var(--text-muted)">${e.desc}</p>
            </div>`;
        });
        document.getElementById('feed-box').innerHTML = html || 'No updates yet.';
    }

    async function submitRating() {
        const body = {
            responsiveness: parseInt(document.getElementById('r-resp').value),
            fairness: parseInt(document.getElementById('r-fair').value),
            service_quality: 5,
            community_involvement: 5,
            feedback: document.getElementById('r-text').value
        };
        const res = await fetch('/api/ratings', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const d = await res.json();
        if (d.success) { alert("Rating Submitted. Thank you for your feedback."); document.getElementById('r-text').value=''; }
        else alert(d.error);
    }

    async function checkSummons() {
        const res = await fetch('/api/summons');
        const data = await res.json();
        const box = document.getElementById('summon-list');
        if (data.length === 0) { box.innerHTML = '<p style="font-size:14px; color:var(--secondary)">✅ All clear.</p>'; return; }
        
        let html = '';
        data.forEach(s => {
            html += `<div style="background:rgba(239, 68, 68, 0.1); border:1px solid var(--danger); padding:10px; border-radius:10px; margin-bottom:10px;">
                <p style="margin:0; font-size:14px;"><b>Mandatory Appearance</b></p>
                <p style="margin:5px 0; font-size:12px;">Reason: ${s.reason}</p>
                <button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="ackSummon(${s.id})">Acknowledge</button>
            </div>`;
        });
        box.innerHTML = html;
        document.getElementById('stat-patawag').innerText = data.length;
    }

    async function ackSummon(id) {
        await fetch('/api/summons/ack', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        checkSummons();
    }

    async function viewFinance() {
        const res = await fetch('/api/finance');
        const data = await res.json();
        const box = document.getElementById('finance-modal');
        if (data.length === 0) { box.innerText = "No published reports."; }
        else {
            const latest = data[0];
            box.innerHTML = `<p><b>Report for ${latest.month}/${latest.year}</b></p><p style="font-style:italic">"${latest.summary}"</p>`;
        }
        box.style.display = 'block';
    }


    async function loadNewsFeed() {
        try {
            const res = await fetch('/api/posts');
            if (!res.ok) throw new Error('Failed to load posts');
            const query = (window.NAV_SEARCH_QUERY || '').toLowerCase();
            const posts = (await res.json()).filter(p => window.postMatchesSearch(p, query));
            let html = '';
            posts.forEach(p => {
                const mentionsHtml = Array.isArray(p.mentions) && p.mentions.length > 0
                    ? p.mentions.map(m => `<span class="mention-tag">@${typeof m === 'string' ? m : (m.name || '')}</span>`).join(' ')
                    : '';
                const locationHtml = p.location ? `<small style="color:var(--secondary); display:block; margin-top:4px;"><i class="fa-solid fa-location-dot"></i> ${p.location}</small>` : '';
                const authorPosition = p.author_position || ((p.author_role === 'bio' || p.author_role === 'official') ? 'Barangay Official' : '');
                let mediaHtml = '';
                if (Array.isArray(p.media_urls) && p.media_urls.length > 0) {
                    mediaHtml = `<div class="post-media-grid" style="grid-template-columns: repeat(${p.media_urls.length > 1 ? 2 : 1}, 1fr);">
                        ${p.media_urls.map(m => {
                            const mediaUrl = typeof m === 'string' ? m : m.url;
                            const isVideo = typeof m === 'object' ? m.type === 'video' : /\.(mp4|webm|ogg)$/i.test(mediaUrl || '');
                            return isVideo
                                ? `<video src="${mediaUrl}" controls style="width:100%; border-radius:10px;" preload="metadata"></video>`
                                : `<img src="${mediaUrl}" style="width:100%; border-radius:10px;" loading="lazy">`;
                        }).join('')}
                    </div>`;
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
                    </div>
                </div>`;
            });
            document.getElementById('news-feed-box').innerHTML = html || 'No posts yet.';
        } catch (e) {
            console.error('Feed load error', e);
            document.getElementById('news-feed-box').innerHTML = '<p class="text-muted">Unable to load posts right now.</p>';
        }
    }

    async function toggleLike(postId) {
        try {
            const res = await fetch(`/api/posts/${postId}/like`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
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

    function loadResidentHome(force = false) {
        if (force || !residentTabState.homeLoaded) {
            residentTabState.homeLoaded = true;
            loadNewsFeed();
        }
    }

    function loadResidentMembersSection(force = false) {
        if (force || !residentTabState.membersLoaded) {
            residentTabState.membersLoaded = true;
            loadMembers();
        }
    }

    function loadResidentWelfareSection(force = false) {
        if (force || !residentTabState.welfareLoaded) {
            residentTabState.welfareLoaded = true;
            if (window.loadWelfareModule) window.loadWelfareModule(true);
        } else if (window.renderWelfareRecords) {
            window.renderWelfareRecords();
        }
    }

    function loadResidentOfficialsSection(force = false) {
        if (force || !residentTabState.officialsLoaded) {
            residentTabState.officialsLoaded = true;
            loadMembers();
        } else if (!window.OFFICIALS_CACHE) {
            loadMembers();
        }
    }

    function loadResidentNotifications(force = false) {
        if (force || !residentTabState.notificationsLoaded) {
            residentTabState.notificationsLoaded = true;
            loadFeed();
            checkSummons();
        }
    }

    function loadResidentHistorySection(force = false) {
        if (force || !residentTabState.historyLoaded) {
            residentTabState.historyLoaded = true;
            loadHistory();
        }
    }

    function loadResidentMapSection(force = false) {
        if (window.MAP_INIT && !force) {
            setTimeout(() => { if(window.L && L.Map) window.dispatchEvent(new Event('resize')); }, 100);
            return;
        }

        if (force || !residentTabState.mapLoaded) {
            residentTabState.mapLoaded = true;
            loadMembers();
        }
    }

    window.addEventListener('tabChanged', (e) => {
        const tab = typeof e.detail === 'string' ? e.detail : e.detail.tabId;
        const forced = typeof e.detail === 'object' && e.detail.forced;
        if(tab === 'home') loadResidentHome(forced);
        if(tab === 'members') loadResidentMembersSection(forced);
        if(tab === 'welfare') loadResidentWelfareSection(forced);
        if(tab === 'officials') loadResidentOfficialsSection(forced);
        if(tab === 'notification') loadResidentNotifications(forced);
        if(tab === 'history') loadResidentHistorySection(forced);
        if(tab === 'maps') loadResidentMapSection(forced);
    });

    window.addEventListener('nameSearchChanged', (e) => {
        const tab = e.detail.tabId;
        if(tab === 'home') loadNewsFeed();
        if(tab === 'welfare' && window.renderWelfareRecords) window.renderWelfareRecords();
        if(tab === 'members' || tab === 'officials' || tab === 'maps') loadMembers();
    });

    async function loadMembers() {
        const resM = await fetch('/api/members');
        const query = (window.NAV_SEARCH_QUERY || '').toLowerCase();
        window.MEMBERS_CACHE = (await resM.json()).filter(m => !query || (m.full_name || '').toLowerCase().includes(query));
        let html = '';
        window.MEMBERS_CACHE.forEach(m => {
            html += `<div style="background:rgba(255,255,255,0.05); padding:10px; border-radius:10px; display:flex; align-items:center;">
                <img src="${m.pic_url || '/static/default-avatar.svg'}" style="width:40px;height:40px;border-radius:50%;margin-right:10px;object-fit:cover;">
                <div><b>${m.role === 'official' ? m.full_name + ' (' + (m.position || 'Official') + ')' : m.full_name}</b><br><small style="color:var(--text-muted)">Role: ${m.role.toUpperCase()} | Class: ${m.class_type || 'N/A'}</small></div>
            </div>`;
        });
        document.getElementById('members-list').innerHTML = html || 'No residents found.';
        
        // Load Officials
        const resO = await fetch('/api/officials');
        const officials = (await resO.json()).filter(o => !query || (o.full_name || '').toLowerCase().includes(query));
        window.OFFICIALS_CACHE = officials;
        if (window.loadRatingScheduleStatus) await window.loadRatingScheduleStatus(true);
        if (window.loadRatingSummary) await window.loadRatingSummary(true);

        if(document.getElementById('res-map') && !window.MAP_INIT) {
            const allUsers = [...window.MEMBERS_CACHE, ...window.OFFICIALS_CACHE];
            window.initGlobalMap('res-map', allUsers, true);
            window.MAP_INIT = true;
        }
        let offHtml = '';
        officials.forEach(o => {
            offHtml += `<div style="padding:15px; border:1px solid var(--card-border); border-radius:15px; background:rgba(255,255,255,0.02); margin-bottom:15px;">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                    <img src="${o.pic_url || '/static/default-avatar.svg'}" style="width:50px;height:50px;border-radius:50%;object-fit:cover; border: 2px solid var(--primary);">
                    <div>
                        <b style="font-size:16px;">${o.full_name}</b><br>
                        <span style="color:var(--primary); font-size:12px; font-weight:700;">${(o.position || 'Barangay Official').toUpperCase()}</span>
                        ${window.buildVoteStatsHtml ? window.buildVoteStatsHtml(o.id) : ''}
                    </div>
                </div>
                <div style="background:rgba(0,0,0,0.2); padding:10px; border-radius:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-size:13px;">Official Rating (1-5)</span>
                        <b id="val-label-${o.id}" style="color:var(--warning)">5.0</b>
                    </div>
                    <input type="range" id="rating-${o.id}" min="1" max="5" step="1" value="5" style="width:100%; accent-color:var(--warning);" oninput="document.getElementById('val-label-${o.id}').innerText = parseFloat(this.value).toFixed(1)">
                    <textarea id="fb-${o.id}" class="input-field" placeholder="Share your feedback..." rows="2" style="margin-top:10px; font-size:13px;"></textarea>
                    ${window.buildRatingActionHtml ? window.buildRatingActionHtml(o.id) : `<button class="btn btn-primary" style="width:100%; margin-top:5px; padding:8px;" onclick="submitIndividualRating(${o.id})">Rate Official</button>`}
                </div>
            </div>`;
        });
        if(document.getElementById('officials-list')) document.getElementById('officials-list').innerHTML = offHtml || 'No officials registered yet.';
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

    let hotspotLayers = [];
    let aiActiveType = null;
    window.toggleAIHotspots = async function(type = null) {
        const map = window.GLOBAL_MAP_INSTANCE;
        if(!map) return alert("Map not ready.");

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

    window.addEventListener('tabChanged', (e) => {
        const tab = typeof e.detail === 'string' ? e.detail : e.detail.tabId;
        if(tab === 'maps' && window.MAP_INIT) {
            // Give it time to display block before invalidating size
            setTimeout(() => { if(window.L && L.Map) window.dispatchEvent(new Event('resize')); }, 100);
        }
    });

    loadResidentHome();



        window.USER_ROLE = "resident";
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
    