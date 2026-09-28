// NO /** @odoo-module **/ directive — plain IIFE, no OWL

(function () {
    'use strict';

    // =====================================================
    // GLOBAL BOOT GUARD
    // =====================================================
    if (window.__realEstateBooted) {
        console.warn('[RealEstate] Duplicate script execution detected — aborting.');
        return;
    }
    window.__realEstateBooted = true;

    // =====================================================
    // AI INVESTMENT NEWS TICKER
    // =====================================================

    function getCity() {
        try { return new URLSearchParams(window.location.search).get('city') || ''; }
        catch (e) { return ''; }
    }

    function insertTicker(newsText, city) {
        if (!newsText) return;

        var old = document.getElementById('ai-news-ticker-box');
        if (old) old.parentNode.removeChild(old);

        var isCity = !!(city);

        // ⭐ NEW - red "TRENDING" strip + "Market Insights" pill, to match
        // the showcase page's ticker banner. Falls back to the previous
        // blue "LIVE" styling when a city is selected.
        var safe = newsText
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        var wrapper = document.createElement('div');
        wrapper.id  = 'ai-news-ticker-box';

        if (isCity) {
            var title = '&#x1F4C8; Top Investment Opportunities in <b style="color:#fecaca;">' + city + '</b>';
            wrapper.innerHTML =
                '<style>@keyframes _ai_scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}</style>' +
                '<div style="background:linear-gradient(90deg,#dc2626 0%,#b91c1c 100%);' +
                    'padding:10px 24px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">' +
                    '<span style="background:#fff;color:#b91c1c;padding:4px 12px;border-radius:5px;font-weight:800;font-size:11.5px;letter-spacing:0.5px;white-space:nowrap;">&#x1F534; LIVE</span>' +
                    '<span style="color:#fff;font-size:13.5px;font-weight:600;">' + title + '</span>' +
                    '<div style="flex:1 1 200px;overflow:hidden;min-width:120px;">' +
                        '<div style="display:inline-flex;align-items:center;white-space:nowrap;animation:_ai_scroll 45s linear infinite;">' +
                            '<span style="padding:0 30px;color:#fff;font-size:13px;">' + safe + '</span>' +
                            '<span style="padding:0 30px;color:#fff;font-size:13px;">' + safe + '</span>' +
                        '</div>' +
                    '</div>' +
                '</div>';
        } else {
            wrapper.innerHTML =
                '<style>@keyframes _ai_scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}</style>' +
                '<div style="background:#dc2626;padding:9px 24px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">' +
                    '<span style="color:#fff;font-weight:800;font-size:12.5px;letter-spacing:0.5px;white-space:nowrap;">&#x25B2; TRENDING</span>' +
                    '<span style="background:#fff;color:#b91c1c;padding:4px 12px;border-radius:5px;font-weight:800;font-size:11px;letter-spacing:0.3px;white-space:nowrap;">&#x1F4C8; Market Insights</span>' +
                    '<div style="flex:1 1 200px;overflow:hidden;min-width:120px;">' +
                        '<div style="display:inline-flex;align-items:center;white-space:nowrap;animation:_ai_scroll 45s linear infinite;">' +
                            '<span style="padding:0 30px;color:#fff;font-size:13px;">' + safe + '</span>' +
                            '<span style="padding:0 30px;color:#fff;font-size:13px;">|</span>' +
                            '<span style="padding:0 30px;color:#fff;font-size:13px;">' + safe + '</span>' +
                            '<span style="padding:0 30px;color:#fff;font-size:13px;">|</span>' +
                        '</div>' +
                    '</div>' +
                '</div>';
        }

        var anchor  = document.getElementById('ai-ticker-anchor');
        var topBar  = document.getElementById('top-bar');
        var mapDisp = document.getElementById('map-display');
        var wrap    = document.getElementById('wrap');
        var header  = document.getElementById('top');

        if (anchor)                              { anchor.appendChild(wrapper); }
        else if (topBar && topBar.parentNode)    { topBar.parentNode.insertBefore(wrapper, topBar.nextSibling); }
        else if (mapDisp && mapDisp.parentNode)  { mapDisp.parentNode.insertBefore(wrapper, mapDisp); }
        else if (wrap)                           { wrap.insertBefore(wrapper, wrap.firstChild); }
        else if (header && header.parentNode)    { header.parentNode.insertBefore(wrapper, header.nextSibling); }
        else                                      { document.body.insertBefore(wrapper, document.body.firstChild); }
    }

    function loadTicker() {
        var city = getCity();
        console.log('[Ticker] Requesting news, city="' + city + '"');
        fetch('/api/investment-news?city=' + encodeURIComponent(city))
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                if (data && data.news) insertTicker(data.news, data.city || '');
            })
            .catch(function (err) { console.error('[Ticker] Failed:', err); });
    }

    // =====================================================
    // PRICE FORMATTING (Indian numbering)
    // =====================================================

    // Full "₹1,23,456" style grouping, used in the left-hand card list.
    function formatINR(num) {
        num = Math.round(Number(num) || 0);
        var s = String(num);
        var lastThree = s.length > 3 ? s.slice(-3) : s;
        var rest = s.length > 3 ? s.slice(0, -3) : '';
        if (rest) { lastThree = ',' + lastThree; }
        return '\u20B9' + rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + lastThree;
    }

    // Short "₹20.0L" / "₹2.3Cr" style, used on the map's price-bubble markers.
    function formatShort(num) {
        num = Number(num) || 0;
        if (num >= 10000000) return '\u20B9' + (num / 10000000).toFixed(1) + 'Cr';
        if (num >= 100000)   return '\u20B9' + (num / 100000).toFixed(1) + 'L';
        return formatINR(num);
    }

    // =====================================================
    // BOTTOM "PROFILE" INFO CARDS (Location + Photo) - update on hover
    // =====================================================

    var psDefaultProfile = null; // captured once, lazily, so we can restore it

    function captureDefaultProfile() {
        if (psDefaultProfile !== null) return;
        var titleEl = document.getElementById('psLocTitle');
        var addrEl  = document.getElementById('psLocAddr');
        var imgBody = document.getElementById('psImageCardBody');
        psDefaultProfile = {
            title: titleEl ? titleEl.innerHTML : '',
            addr:  addrEl ? addrEl.innerHTML : '',
            img:   imgBody ? imgBody.innerHTML : ''
        };
    }

    function showPropertyProfile(p) {
        if (!p) return;
        captureDefaultProfile();
        var titleEl = document.getElementById('psLocTitle');
        var addrEl  = document.getElementById('psLocAddr');
        var imgBody = document.getElementById('psImageCardBody');
        if (titleEl) titleEl.textContent = p.name || 'Property';
        if (addrEl)  addrEl.textContent  = p.full_address || p.city || '';
        if (imgBody) {
            var img = p.image_url || '/web/static/img/placeholder.png';
            imgBody.innerHTML =
                '<img src="' + img + '" onerror="this.src=\'/web/static/img/placeholder.png\'" alt="' + (p.name || '') + '"/>';
        }
    }

    function restorePropertyProfile() {
        if (psDefaultProfile === null) return;
        var titleEl = document.getElementById('psLocTitle');
        var addrEl  = document.getElementById('psLocAddr');
        var imgBody = document.getElementById('psImageCardBody');
        if (titleEl) titleEl.innerHTML = psDefaultProfile.title;
        if (addrEl)  addrEl.innerHTML  = psDefaultProfile.addr;
        if (imgBody) imgBody.innerHTML = psDefaultProfile.img;
    }

    // =====================================================
    // LEFT-HAND PROPERTY CARD LIST (synced with the map)
    // =====================================================

    function renderPropertyCardList(properties, categoryColors, markersById) {
        var listEl = document.getElementById('psCardsList');
        if (!listEl) return;

        if (!properties.length) {
            listEl.innerHTML = '<div class="ps-empty-list">No properties found.</div>';
            return;
        }

        // ⭐ Sort low -> high by price for this strip only (map markers keep
        // their original order). Plain price sort - no grouping by category.
        var sortedProperties = properties.slice().sort(function (a, b) {
            return (Number(a.price) || 0) - (Number(b.price) || 0);
        });

        // ⭐ NEW - lookup by id, so hovering a card can also update the
        // bottom profile cards (Location + Photo) with that property.
        var propsById = {};
        properties.forEach(function (p) { propsById[p.id] = p; });

        listEl.innerHTML = sortedProperties.map(function (p) {
            var color   = categoryColors[p.property_type] || '#4f46e5';
            var img     = p.image_url || '/web/static/img/placeholder.png';
            var premium = p.is_featured
                ? '<span class="ps-card-premium">+ PREMIUM</span>' : '';
            return (
                '<a href="/property/' + p.id + '" class="ps-card" data-pid="' + p.id + '">' +
                    '<div class="ps-card-img">' +
                        '<img src="' + img + '" onerror="this.src=\'/web/static/img/placeholder.png\'" alt="' + (p.name || '') + '"/>' +
                        '<span class="ps-card-badge" style="background:' + color + '">' + (p.property_type || 'Property') + '</span>' +
                        premium +
                    '</div>' +
                    '<div class="ps-card-body">' +
                        '<div class="ps-card-price">' + formatINR(p.price) + '</div>' +
                        '<div class="ps-card-name">' + (p.name || '') + '</div>' +
                        '<div class="ps-card-loc"><i class="fas fa-map-marker-alt"/>' + (p.full_address || p.city || '') + '</div>' +
                        '<div class="ps-card-rating">' + (p.rating_html || '') + '</div>' +
                        '<div class="ps-card-type" style="color:' + color + '">' + (p.property_type || '') + '</div>' +
                    '</div>' +
                '</a>'
            );
        }).join('');

        // Hover a card -> show that property's profile in the bottom
        // Location/Photo cards. (No longer opens/highlights anything on
        // the map itself - hovering the card list stays map-independent.)
        Array.prototype.forEach.call(listEl.querySelectorAll('.ps-card'), function (cardEl) {
            var pid = cardEl.getAttribute('data-pid');
            cardEl.addEventListener('mouseenter', function () {
                showPropertyProfile(propsById[pid]);
            });
            cardEl.addEventListener('mouseleave', function () {
                restorePropertyProfile();
            });
        });
    }

    // =====================================================
    // TOP-LEFT "TOP RATED" PANEL - small cards for 5-star properties
    // =====================================================

    function renderFiveStarPanel(properties) {
        var panelEl = document.getElementById('fiveStarPanel');
        var listEl  = document.getElementById('fiveStarCardsList');
        if (!panelEl || !listEl) return;

        var fiveStar = properties.filter(function (p) {
            return String(p.rating) === '5';
        });

        if (!fiveStar.length) {
            panelEl.classList.add('ps-hidden');
            listEl.innerHTML = '';
            return;
        }

        panelEl.classList.remove('ps-hidden');

        listEl.innerHTML = fiveStar.map(function (p) {
            var img = p.image_url || '/web/static/img/placeholder.png';
            return (
                '<div class="ps-fs-card">' +
                    '<div class="ps-fs-img">' +
                        '<img src="' + img + '" onerror="this.src=\'/web/static/img/placeholder.png\'" alt="' + (p.name || '') + '"/>' +
                    '</div>' +
                    '<div class="ps-fs-body">' +
                        '<div class="ps-fs-name">' + (p.name || '') + '</div>' +
                        '<div class="ps-fs-price">' + formatShort(p.price) + '</div>' +
                        '<div class="ps-fs-stars">' + (p.rating_html || '') + '</div>' +
                        '<a href="/property/' + p.id + '" class="ps-fs-view">View Details &#8250;</a>' +
                    '</div>' +
                '</div>'
            );
        }).join('');
    }

    // =====================================================
    // PIE CHART - listings by property type (Location card)
    // =====================================================

    function renderCategoryPie(properties, categoryColors) {
        var pieEl    = document.getElementById('psCategoryPie');
        var legendEl = document.getElementById('psCategoryLegend');
        if (!pieEl || !legendEl) return;

        if (!properties.length) {
            pieEl.style.background = '#f0efe9';
            legendEl.innerHTML = '<div class="ps-empty-list">No listings yet.</div>';
            return;
        }

        // Count properties per category, preserving first-seen order.
        var order  = [];
        var counts = {};
        properties.forEach(function (p) {
            var cat = p.property_type || 'Property';
            if (!counts[cat]) { counts[cat] = 0; order.push(cat); }
            counts[cat] += 1;
        });

        var total = properties.length;
        var stops = [];
        var cursor = 0;
        order.forEach(function (cat) {
            var color = categoryColors[cat] || '#4f46e5';
            var slice = (counts[cat] / total) * 100;
            stops.push(color + ' ' + cursor + '% ' + (cursor + slice) + '%');
            cursor += slice;
        });
        pieEl.style.background = stops.length
            ? 'conic-gradient(' + stops.join(', ') + ')'
            : '#f0efe9';

        legendEl.innerHTML = order.map(function (cat) {
            var color = categoryColors[cat] || '#4f46e5';
            return (
                '<div class="ps-cat-legend-item">' +
                    '<span class="ps-cat-dot" style="background:' + color + '"/>' +
                    '<span class="ps-cat-name">' + cat + '</span>' +
                    '<span class="ps-cat-count">' + counts[cat] + '</span>' +
                '</div>'
            );
        }).join('');
    }

    // Marker hover -> highlight the matching card in the bottom strip (no auto-scroll).
    function highlightCard(pid, isActive) {
        var cardEl = document.querySelector('.ps-card[data-pid="' + pid + '"]');
        if (!cardEl) return;
        if (isActive) {
            cardEl.classList.add('ps-card-active');
        } else {
            cardEl.classList.remove('ps-card-active');
        }
    }

    // =====================================================
    // PROPERTY MAP
    // =====================================================

    function initPropertyMap() {
        var dataEl   = document.getElementById('property-data');
        var legendEl = document.getElementById('category-legend');
        var mapEl    = document.getElementById('propertyMap');

        if (!dataEl || !legendEl || !mapEl) return;

        // ⭐ FIX: guarantee non-zero container size even if property_map.css
        // hasn't finished loading by the time this runs.
        if (!mapEl.style.height) { mapEl.style.height = '600px'; }
        if (!mapEl.style.width)  { mapEl.style.width  = '100%'; }

        // --- NEW: INJECT LEAFLET CSS AND JS DYNAMICALLY ---
        if (!document.getElementById('leaflet-css')) {
            var link = document.createElement('link');
            link.id = 'leaflet-css';
            link.rel = 'stylesheet';
            link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(link);
        }

        if (typeof L === 'undefined' && !document.getElementById('leaflet-js')) {
            var script = document.createElement('script');
            script.id = 'leaflet-js';
            script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
            document.head.appendChild(script);
        }
        // --------------------------------------------------

        if (mapEl._leaflet_id) {
            console.warn('[PropertyMap] Stale Leaflet state found — cleaning up before init');
            try {
                var staleMap = mapEl._leaflet_id && L && L.Map && L.Map._instances
                    ? L.Map._instances[mapEl._leaflet_id]
                    : null;
                if (staleMap) staleMap.remove();
            } catch (e) { /* ignore */ }
            mapEl._leaflet_id = null;
            mapEl.innerHTML   = '';
        }

        var properties = [];
        try {
            properties = JSON.parse(dataEl.dataset.properties || '[]');
            if (!Array.isArray(properties)) properties = [];
        } catch (e) { console.error('[PropertyMap] bad JSON', e); }

        var categoryColors = {};
        try {
            categoryColors = JSON.parse(legendEl.dataset.colors || '{}');
        } catch (e) { console.error('[PropertyMap] bad colors JSON', e); }

        console.log('[PropertyMap] ' + properties.length + ' properties');

        // ⭐ NEW - top-left "Top Rated" panel doesn't need Leaflet, so
        // populate it as soon as the property data itself is ready.
        renderFiveStarPanel(properties);

        var leafletWaitElapsed = 0;
        function waitForLeaflet(cb) {
            if (typeof L !== 'undefined') { cb(); return; }
            leafletWaitElapsed += 200;
            if (leafletWaitElapsed >= 10000) {
                console.error('[PropertyMap] Leaflet failed to load within 10s.');
                mapEl.innerHTML =
                    '<div style="display:flex;align-items:center;justify-content:center;' +
                    'height:100%;background:#f3f4f6;color:#6b7280;font-weight:600;' +
                    'text-align:center;padding:24px;border-radius:20px;">' +
                    '⚠️ Map could not load. Please check your internet connection and refresh the page.' +
                    '</div>';
                return;
            }
            setTimeout(function () { waitForLeaflet(cb); }, 200);
        }

        waitForLeaflet(function () {
            console.log('[PropertyMap] Leaflet ready — initialising map');

            var map = L.map(mapEl);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19
            }).addTo(map);

            var openPopupMarker    = null;
            var pointerInsidePopup = false;
            // ⭐ Property cards should only appear when the user points at
            // (hovers/taps) a marker — not permanently for every marker.
            // The hover/tap logic below already does exactly this; this
            // flag just needs to be off.
            var ALWAYS_SHOW_POPUPS = false;

            function createIcon(color) {
                return L.divIcon({
                    className: 'custom-marker',
                    html: '<div style="width:32px;height:32px;border-radius:50%;' +
                          'background:' + color + ';border:3px solid white;' +
                          'box-shadow:0 3px 12px rgba(0,0,0,0.3);' +
                          'display:flex;align-items:center;justify-content:center;' +
                          'font-size:14px;color:white;cursor:pointer;">📍</div>',
                    iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -16]
                });
            }

            // ⭐ NEW - price-bubble marker used by the showcase page (a colored
            // pill showing the short-form price, e.g. ₹20.0L) instead of a plain pin.
            function createPriceIcon(color, priceText) {
                return L.divIcon({
                    className: 'custom-marker',
                    html: '<div class="ps-price-marker" style="background:' + color + '">' + priceText + '</div>',
                    iconSize: null, iconAnchor: [30, 14], popupAnchor: [0, -14]
                });
            }

            function popupHtml(p) {
                var img   = p.image_url || '/web/static/img/placeholder.png';
                var price = p.price > 0
                    ? '₹' + Number(p.price).toLocaleString('en-IN')
                    : 'Price on Request';
                return '<div class="property-hover-card">' +
                    '<img src="' + img + '" class="property-image" ' +
                         'onerror="this.src=\'/web/static/img/placeholder.png\'"/>' +
                    '<div class="property-content">' +
                        '<h4 class="property-title">' + (p.name || '') + '</h4>' +
                        '<div class="property-category">' + (p.property_type || '') + '</div>' +
                        '<div class="property-location">📍 ' + (p.full_address || '') + '</div>' +
                        '<div class="property-price">' + price + '</div>' +
                        '<div class="property-details">' +
                            (p.plot_area ? '<div class="detail-item">📐 ' + p.plot_area + ' sqft</div>' : '') +
                        '</div>' +
                        '<div class="action-buttons">' +
                            '<a href="/property/' + p.id + '" class="btn-sm btn-primary">View Details</a>' +
                            (p.contact_phone
                                ? '<a href="tel:' + p.contact_phone + '" class="btn-sm btn-outline">📞 Call</a>'
                                : '') +
                        '</div>' +
                    '</div></div>';
            }

            var markerLatLngs = [];
            var allMarkers    = [];
            // ⭐ NEW - keyed by property id, so hovering a card in the
            // left-hand list can open its matching marker, and vice versa.
            var markersById   = {};

            properties.forEach(function (p) {
                if (!p.latitude || !p.longitude) return;

                var color  = categoryColors[p.property_type] || '#4f46e5';
                var marker = L.marker([p.latitude, p.longitude], {
                    icon: createPriceIcon(color, formatShort(p.price))
                }).addTo(map);
                markerLatLngs.push([p.latitude, p.longitude]);
                markersById[p.id] = marker;

                marker.bindPopup(popupHtml(p), {
                    closeButton: false, autoClose: false, closeOnClick: false,
                    className: 'custom-popup', minWidth: 280, maxWidth: 320
                });

                // ⭐ FIX: don't open the popup here yet - the map has no
                // view (center/zoom) set until after this whole loop runs,
                // so Leaflet can't position the popup correctly and it
                // stays invisible until you click the marker. Instead,
                // track this marker and open its popup further below,
                // AFTER the map's view is set.
                allMarkers.push(marker);

                marker.on('mouseover', function () {
                    if (openPopupMarker && openPopupMarker !== marker) openPopupMarker.closePopup();
                    marker.openPopup();
                    openPopupMarker = marker;
                    highlightCard(p.id, true);
                    // ⭐ NEW: show this property's profile in the bottom
                    // Location/Photo cards while hovering its map pin.
                    showPropertyProfile(p);
                });

                marker.on('mouseout', function () {
                    highlightCard(p.id, false);
                    // ⭐ NEW: revert the bottom profile cards back to default
                    // once the pointer leaves this marker.
                    restorePropertyProfile();
                    // ⭐ NEW: don't auto-close when popups are meant to stay
                    // permanently open - existing hover-close behavior is
                    // kept below, just skipped while this flag is on.
                    if (ALWAYS_SHOW_POPUPS) return;
                    setTimeout(function () {
                        if (openPopupMarker === marker && !pointerInsidePopup) {
                            marker.closePopup();
                            openPopupMarker = null;
                        }
                    }, 100);
                });

                marker.on('popupopen', function (ev) {
                    var popupEl = ev && ev.popup ? ev.popup.getElement() : null;
                    if (!popupEl) return;
                    popupEl.addEventListener('mouseenter', function () { pointerInsidePopup = true; });
                    popupEl.addEventListener('mouseleave', function () {
                        pointerInsidePopup = false;
                        setTimeout(function () {
                            if (openPopupMarker === marker && !pointerInsidePopup) {
                                marker.closePopup();
                                openPopupMarker = null;
                            }
                        }, 100);
                    });
                });
            });

            // ⭐ NEW - populate the left-hand card list (showcase page only;
            // harmless no-op wherever #psCardsList doesn't exist).
            renderPropertyCardList(properties, categoryColors, markersById);

            // ⭐ NEW - pie chart in the Location card: listings by property type.
            renderCategoryPie(properties, categoryColors);

            map.on('click', function () {
                // ⭐ NEW: keep this existing feature, just skip it while
                // popups are meant to stay permanently open.
                if (ALWAYS_SHOW_POPUPS) return;
                if (openPopupMarker) { openPopupMarker.closePopup(); openPopupMarker = null; }
            });

            legendEl.innerHTML = Object.entries(categoryColors).map(function (e) {
                return '<div class="legend-item">' +
                       '<div class="legend-color" style="background:' + e[1] + '"></div>' +
                       '<span>' + e[0] + '</span></div>';
            }).join('');

            if (markerLatLngs.length === 1) {
                map.setView(markerLatLngs[0], 15);
            } else if (markerLatLngs.length > 1) {
                var grp    = L.featureGroup(markerLatLngs.map(function (ll) { return L.marker(ll); }));
                var bounds = grp.getBounds();
                if (bounds.isValid()) {
                    map.fitBounds(bounds.pad(0.1));
                    if (map.getZoom() < 8) map.setView(bounds.getCenter(), 10);
                } else {
                    map.setView([20.5937, 78.9629], 5);
                }
            } else {
                map.setView([20.5937, 78.9629], 5);
            }

            // ⭐ FIX: NOW that the map has a real center/zoom, it's safe to
            // open every marker's popup so it's visible without any click.
            function openAllPopups() {
                if (!ALWAYS_SHOW_POPUPS) return;
                allMarkers.forEach(function (m) { m.openPopup(); });
            }
            openAllPopups();

            function fixMapSize() {
                try { map.invalidateSize(); } catch (e) { /* ignore */ }
                // ⭐ FIX: invalidateSize() can shift/redraw the map and drop
                // popup positions - reopen them each time to keep every
                // card visible without needing a click.
                openAllPopups();
            }
            setTimeout(fixMapSize, 100);
            setTimeout(fixMapSize, 500);
            setTimeout(fixMapSize, 1200);
            window.addEventListener('load', fixMapSize);
        });
    }

    // =====================================================
    // THEME TOGGLE (light / dark) — WEBSITE COLORS ONLY.
    // Does not touch the map, its tiles, or any map settings.
    // =====================================================
    function initThemeToggle() {
        var root   = document.getElementById('home-page-root');
        var toggle = document.getElementById('themeSwitch');
        if (!root) return;

        var saved = localStorage.getItem('reo-theme') || 'light';

        function applyTheme(theme) {
            root.setAttribute('data-theme', theme);
            localStorage.setItem('reo-theme', theme);
        }

        if (toggle) {
            toggle.checked = (saved === 'dark');
            toggle.addEventListener('change', function () {
                applyTheme(this.checked ? 'dark' : 'light');
            });
        }

        applyTheme(saved);
    }

    // =====================================================
    // BOOT
    // =====================================================
    function boot() {
        // ⭐ NEW: set the data-theme attribute before anything else renders.
        initThemeToggle();
        // ⭐ RE-ENABLED - the showcase page has a dedicated #ai-ticker-anchor
        // slot right under the top bar for this.
        loadTicker();
        initPropertyMap();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }

})();