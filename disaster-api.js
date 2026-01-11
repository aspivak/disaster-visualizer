/**
 * Disaster API - Pure JavaScript implementation
 * Migrated from Python backend (app.py, disaster_polygons.py)
 */

// ============================================================================
// Configuration
// ============================================================================

const CORS_PROXY = 'https://corsproxy.io/?';

// Detect if running from file:// protocol (needs CORS proxy for all requests)
const NEEDS_CORS_PROXY = window.location.protocol === 'file:';

const COUNTRY_MAP = {
    'at': 'austria', 'be': 'belgium', 'ba': 'bosnia-herzegovina', 'bg': 'bulgaria',
    'hr': 'croatia', 'cy': 'cyprus', 'cz': 'czech-republic', 'dk': 'denmark',
    'ee': 'estonia', 'fi': 'finland', 'fr': 'france', 'de': 'germany',
    'gr': 'greece', 'hu': 'hungary', 'is': 'iceland', 'ie': 'ireland',
    'it': 'italy', 'lv': 'latvia', 'lt': 'lithuania', 'lu': 'luxembourg',
    'mt': 'malta', 'md': 'moldova', 'me': 'montenegro', 'nl': 'netherlands',
    'mk': 'north-macedonia', 'no': 'norway', 'pl': 'poland', 'pt': 'portugal',
    'ro': 'romania', 'rs': 'serbia', 'sk': 'slovakia', 'si': 'slovenia',
    'es': 'spain', 'se': 'sweden', 'ch': 'switzerland', 'uk': 'united-kingdom',
    'il': 'israel'
};

// ============================================================================
// Geometry Utilities
// ============================================================================

/**
 * Convert a point to a buffered circle polygon WKT
 * @param {number} lon - Longitude
 * @param {number} lat - Latitude  
 * @param {number} buffer - Buffer in degrees (default 0.5)
 * @returns {string} WKT POLYGON string
 */
function pointToPolygonWKT(lon, lat, buffer = 0.5) {
    const numPoints = 32;
    const coords = [];

    for (let i = 0; i <= numPoints; i++) {
        const angle = (2 * Math.PI * i) / numPoints;
        const x = lon + buffer * Math.cos(angle);
        const y = lat + buffer * Math.sin(angle);
        coords.push(`${x.toFixed(6)} ${y.toFixed(6)}`);
    }

    return `POLYGON ((${coords.join(', ')}))`;
}

/**
 * Parse CAP polygon coordinates to WKT format
 * CAP format: "lat1,lon1 lat2,lon2 ..." 
 * @param {string} polygonStr - CAP polygon string
 * @returns {string|null} WKT POLYGON string or null
 */
function parseCapPolygon(polygonStr) {
    if (!polygonStr) return null;

    const parts = polygonStr.trim().split(/\s+/);
    const coords = [];

    for (const p of parts) {
        if (p.includes(',')) {
            const [lat, lon] = p.split(',').map(parseFloat);
            if (!isNaN(lat) && !isNaN(lon)) {
                coords.push(`${lon} ${lat}`);
            }
        }
    }

    if (coords.length > 0) {
        // Close the polygon if not already closed
        if (coords[0] !== coords[coords.length - 1]) {
            coords.push(coords[0]);
        }
        return `POLYGON ((${coords.join(', ')}))`;
    }

    return null;
}

// ============================================================================
// Gemini API
// ============================================================================

/**
 * Search for crisis events using Gemini API
 * @param {string} date - Date in YYYY-MM-DD format
 * @param {string} apiKey - Gemini API key
 * @param {string} customPrompt - Custom prompt (optional)
 * @returns {Promise<Object>} Events data
 */
async function searchGemini(date, apiKey, customPrompt = '') {
    if (!date) throw new Error('Date is required');
    if (!apiKey) throw new Error('Gemini API key is required');

    const dt = new Date(date);
    const readableDate = dt.toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric'
    });
    const dateCompact = date.replace(/-/g, '');

    const url = `https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key=${apiKey}`;

    let prompt;
    if (customPrompt) {
        prompt = customPrompt
            .replace(/{date}/g, readableDate)
            .replace(/{date_compact}/g, dateCompact);
    } else {
        prompt = `Search for disaster and crisis-related events on ${readableDate}.
Include: natural disasters, severe weather, conflicts, major accidents.
Return JSON: {"events": [{"event_name": "name", "location": "city", "country": "country", 
"description": "brief", "estimated_lat": 0.0, "estimated_lon": 0.0}]}`;
    }

    const payload = {
        contents: [{ parts: [{ text: prompt }] }]
    };

    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error?.message || 'Gemini API request failed');
    }

    const geminiResponse = await response.json();

    // Extract text from response
    let responseText;
    try {
        responseText = geminiResponse.candidates[0].content.parts[0].text.trim();
    } catch (e) {
        throw new Error('Invalid Gemini API response structure');
    }

    // Parse JSON from response
    const eventsData = parseGeminiJson(responseText);

    // Check if it's the new nested structure
    if (eventsData[dateCompact]) {
        return eventsData;
    }

    // Legacy parsing for flat "events" list
    const results = [];
    for (const event of (eventsData.events || [])) {
        try {
            const lat = parseFloat(event.estimated_lat || 0);
            const lon = parseFloat(event.estimated_lon || 0);
            const wkt = pointToPolygonWKT(lon, lat, 0.5);

            results.push({
                date: dateCompact,
                country: event.country || 'Unknown',
                event: `${event.event_name} - ${event.description || ''}`,
                polygon: wkt
            });
        } catch (e) {
            continue;
        }
    }

    return { events: results, count: results.length };
}

/**
 * Parse JSON from Gemini response with robust error handling
 */
function parseGeminiJson(responseText) {
    // Try to find JSON object in response
    const jsonMatch = responseText.match(/\{[\s\S]*\}/);

    if (jsonMatch) {
        let jsonStr = jsonMatch[0];

        // Fix double curly braces (LLM artifact)
        if (jsonStr.includes('{{')) {
            jsonStr = jsonStr.replace(/\{\{/g, '{').replace(/\}\}/g, '}');
        }

        try {
            return JSON.parse(jsonStr);
        } catch (e) {
            // Try cleaning markdown code blocks
            let cleanText = responseText.replace(/```json/g, '').replace(/```/g, '').trim();
            if (cleanText.includes('{{')) {
                cleanText = cleanText.replace(/\{\{/g, '{').replace(/\}\}/g, '}');
            }

            try {
                return JSON.parse(cleanText);
            } catch (e2) {
                throw new Error('Failed to parse Gemini JSON response');
            }
        }
    }

    // Try direct parse
    try {
        return JSON.parse(responseText);
    } catch (e) {
        throw new Error('Invalid JSON format from Gemini');
    }
}

// ============================================================================
// EONET API (NASA)
// ============================================================================

/**
 * Fetch events from NASA EONET API
 * @param {string} startDate - Start date YYYY-MM-DD
 * @param {string} endDate - End date YYYY-MM-DD (optional, defaults to startDate)
 * @param {boolean} useCorsProxy - Whether to use CORS proxy
 * @returns {Promise<Array>} Array of event objects
 */
async function fetchEONET(startDate, endDate = null, useCorsProxy = NEEDS_CORS_PROXY) {
    let url = new URL('https://eonet.gsfc.nasa.gov/api/v3/events');
    url.searchParams.set('start', startDate);
    url.searchParams.set('end', endDate || startDate);
    url.searchParams.set('status', 'all');

    const fetchUrl = useCorsProxy ? CORS_PROXY + encodeURIComponent(url.toString()) : url.toString();

    const response = await fetch(fetchUrl);
    if (!response.ok) throw new Error('EONET API request failed');

    const data = await response.json();
    const events = [];

    for (const event of (data.events || [])) {
        const geometries = event.geometry || [];
        if (geometries.length === 0) continue;

        const lastGeo = geometries[geometries.length - 1];
        const eventDate = lastGeo.date.substring(0, 10).replace(/-/g, '');

        const polygons = [];
        for (const geo of geometries) {
            if (geo.type === 'Point') {
                const [lon, lat] = geo.coordinates;
                polygons.push(pointToPolygonWKT(lon, lat, 0.1));
            } else if (geo.type === 'Polygon') {
                const coords = geo.coordinates[0]
                    .map(c => `${c[0]} ${c[1]}`)
                    .join(', ');
                polygons.push(`POLYGON ((${coords}))`);
            }
        }

        if (polygons.length > 0) {
            const wkt = polygons.length === 1
                ? polygons[0]
                : `MULTIPOLYGON (${polygons.map(p => p.replace('POLYGON ', '')).join(', ')})`;

            events.push({
                date: eventDate,
                country: event.categories?.[0]?.title || 'Unknown',
                event: event.title || 'Unknown Event',
                polygon: wkt
            });
        }
    }

    console.log(`EONET: Fetched ${events.length} events`);
    return events;
}

// ============================================================================
// GDACS API
// ============================================================================

/**
 * Fetch events from GDACS RSS feed
 * @param {boolean} useCorsProxy - Whether to use CORS proxy
 * @returns {Promise<Array>} Array of event objects
 */
async function fetchGDACS(useCorsProxy = NEEDS_CORS_PROXY) {
    const baseUrl = 'https://www.gdacs.org/xml/rss.xml';
    const url = useCorsProxy ? CORS_PROXY + encodeURIComponent(baseUrl) : baseUrl;

    const response = await fetch(url);
    if (!response.ok) throw new Error('GDACS RSS request failed');

    const xmlText = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlText, 'text/xml');

    const events = [];
    const items = doc.querySelectorAll('item');

    for (const item of items) {
        const title = item.querySelector('title')?.textContent;
        const pubDate = item.querySelector('pubDate')?.textContent;
        const geoPoint = item.getElementsByTagNameNS('http://www.georss.org/georss', 'point')[0];

        if (title && pubDate && geoPoint) {
            try {
                const dt = new Date(pubDate);
                const formattedDate = dt.toISOString().substring(0, 10).replace(/-/g, '');

                const coords = geoPoint.textContent.trim().split(/\s+/);
                if (coords.length === 2) {
                    const [lat, lon] = coords.map(parseFloat);
                    const wkt = pointToPolygonWKT(lon, lat, 0.5);

                    // Extract country from title
                    // GDACS formats: "Green alert for flood in COUNTRY" or "Earthquake in COUNTRY" 
                    // or "M 4.6 ... in COUNTRY date" or "Event Type, COUNTRY, Date"
                    let country = 'Unknown';

                    // Try "in COUNTRY" pattern first (for earthquakes and floods)
                    const inMatch = title.match(/\s+in\s+([A-Za-z\s-]+?)(?:\s+\d|$)/i);
                    if (inMatch && inMatch[1]) {
                        country = inMatch[1].trim();
                    } else if (title.includes(',')) {
                        // Fallback: try comma-separated format
                        const parts = title.split(',');
                        if (parts.length >= 2) {
                            // Take the last word before numbers as country
                            const potentialCountry = parts[1].trim().split(/\s+\d/)[0].trim();
                            if (potentialCountry && potentialCountry.length > 1) {
                                country = potentialCountry;
                            }
                        }
                    }

                    events.push({
                        date: formattedDate,
                        country: country,
                        event: title,
                        polygon: wkt
                    });
                }
            } catch (e) {
                continue;
            }
        }
    }

    console.log(`GDACS: Fetched ${events.length} events`);
    return events;
}

// ============================================================================
// MeteoAlarm API
// ============================================================================

/**
 * Fetch events from MeteoAlarm feeds
 * @param {string} startDate - Start date YYYYMMDD
 * @param {string} corsProxy - CORS proxy URL (optional)
 * @returns {Promise<Array>} Array of event objects
 */
async function fetchMeteoAlarm(startDate, corsProxy = CORS_PROXY) {
    const targetDate = new Date(
        startDate.substring(0, 4),
        parseInt(startDate.substring(4, 6)) - 1,
        startDate.substring(6, 8)
    );

    const events = [];
    const activeEntries = [];

    // Fetch all country feeds in parallel
    const feedPromises = Object.entries(COUNTRY_MAP).map(async ([iso, slug]) => {
        try {
            const url = `${corsProxy}https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-${slug}`;
            const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
            if (!response.ok) return null;

            const xmlText = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(xmlText, 'text/xml');

            const entries = doc.querySelectorAll('entry');
            console.log(`[${iso.toUpperCase()}] ${entries.length} found`);

            for (const entry of entries) {
                // Check expiry
                const expires = entry.querySelector('expires')?.textContent;
                if (expires) {
                    try {
                        const expiresDate = new Date(expires.replace('Z', '+00:00'));
                        if (expiresDate < targetDate) continue;
                    } catch (e) { }
                }

                // Find CAP link
                const links = entry.querySelectorAll('link');
                let capLink = null;
                for (const link of links) {
                    if (link.getAttribute('type') === 'application/cap+xml') {
                        capLink = link.getAttribute('href');
                        break;
                    }
                }

                if (capLink) {
                    activeEntries.push({
                        countryCode: iso,
                        countryName: slug,
                        capLink: capLink
                    });
                }
            }
        } catch (e) {
            console.debug(`[${iso.toUpperCase()}] Feed error:`, e.message);
        }
    });

    await Promise.all(feedPromises);
    console.log(`Fetching details for ${activeEntries.length} MeteoAlarm warnings...`);

    // Fetch CAP details in parallel (with concurrency limit)
    const batchSize = 20;
    for (let i = 0; i < activeEntries.length; i += batchSize) {
        const batch = activeEntries.slice(i, i + batchSize);

        const capPromises = batch.map(async (item) => {
            try {
                const url = `${corsProxy}${item.capLink}`;
                const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
                if (!response.ok) return;

                const xmlText = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(xmlText, 'text/xml');

                // Find info element (prefer English)
                const infos = doc.querySelectorAll('info');
                let selectedInfo = null;
                for (const info of infos) {
                    const lang = info.querySelector('language')?.textContent || '';
                    if (lang.includes('en')) {
                        selectedInfo = info;
                        break;
                    }
                }
                if (!selectedInfo && infos.length > 0) selectedInfo = infos[0];
                if (!selectedInfo) return;

                const eventType = selectedInfo.querySelector('event')?.textContent || 'Unknown Event';
                const severity = selectedInfo.querySelector('severity')?.textContent || 'Unknown';
                const onset = selectedInfo.querySelector('onset')?.textContent ||
                    selectedInfo.querySelector('effective')?.textContent || 'Unknown';
                const headline = selectedInfo.querySelector('headline')?.textContent || `${severity} ${eventType}`;
                const description = selectedInfo.querySelector('description')?.textContent || '';
                const shortDesc = description.length > 75 ? description.substring(0, 75) + '..' : description;

                let countryName = item.countryName.split('-').map(w =>
                    w.charAt(0).toUpperCase() + w.slice(1)
                ).join(' ');
                if (countryName === 'United Kingdom') countryName = 'United Kingdom';
                if (countryName === 'Bosnia Herzegovina') countryName = 'Bosnia and Herzegovina';

                let eventDate = startDate;
                let onsetFmt = onset;
                try {
                    const dt = new Date(onset.replace('Z', '+00:00'));
                    onsetFmt = dt.toLocaleString('en-GB', {
                        day: '2-digit', month: '2-digit', year: 'numeric',
                        hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
                    });
                    eventDate = dt.toISOString().substring(0, 10).replace(/-/g, '');
                } catch (e) { }

                const keyStr = `${headline} in ${countryName} ${onsetFmt}, ${shortDesc}`;

                // Extract polygons
                const areas = selectedInfo.querySelectorAll('area');
                for (const area of areas) {
                    const polyElem = area.querySelector('polygon');
                    if (polyElem) {
                        const wkt = parseCapPolygon(polyElem.textContent);
                        if (wkt) {
                            events.push({
                                date: eventDate,
                                country: countryName,
                                event: keyStr,
                                polygon: wkt
                            });
                        }
                    }
                }
            } catch (e) {
                console.debug('CAP fetch error:', e.message);
            }
        });

        await Promise.all(capPromises);
    }

    console.log(`MeteoAlarm: Fetched ${events.length} events`);
    return events;
}

// ============================================================================
// Combined Data Fetching
// ============================================================================

/**
 * Fetch all disaster data for a given date
 * @param {string} dateYYYYMMDD - Date in YYYYMMDD format
 * @param {Object} options - Options { includeMeteoAlarm, corsProxy, useCorsProxy }
 * @returns {Promise<Object>} Grouped results by date/country/event
 */
async function fetchAllDisasterData(dateYYYYMMDD, options = {}) {
    const formattedDate = `${dateYYYYMMDD.substring(0, 4)}-${dateYYYYMMDD.substring(4, 6)}-${dateYYYYMMDD.substring(6, 8)}`;
    const {
        includeMeteoAlarm = false,
        corsProxy = CORS_PROXY,
        useCorsProxy = NEEDS_CORS_PROXY
    } = options;

    const tasks = [
        fetchEONET(formattedDate, formattedDate, useCorsProxy).catch(e => { console.error('EONET error:', e); return []; }),
        fetchGDACS(useCorsProxy).catch(e => { console.error('GDACS error:', e); return []; })
    ];

    if (includeMeteoAlarm) {
        tasks.push(fetchMeteoAlarm(dateYYYYMMDD, corsProxy).catch(e => {
            console.error('MeteoAlarm error:', e);
            return [];
        }));
    }

    const results = await Promise.all(tasks);

    // Flatten and filter by date
    let allEvents = results.flat().filter(e => e.date === dateYYYYMMDD);

    // Group by date -> country -> event -> polygons
    const grouped = {};
    for (const event of allEvents) {
        const d = event.date;
        const c = event.country;
        const e = event.event;
        const p = event.polygon;

        if (!grouped[d]) grouped[d] = {};
        if (!grouped[d][c]) grouped[d][c] = {};
        if (!grouped[d][c][e]) grouped[d][c][e] = [];
        grouped[d][c][e].push(p);
    }

    console.log(`Total: Fetched ${allEvents.length} events for ${dateYYYYMMDD}`);
    return grouped;
}

// Export for use in browser
window.DisasterAPI = {
    searchGemini,
    fetchEONET,
    fetchGDACS,
    fetchMeteoAlarm,
    fetchAllDisasterData,
    pointToPolygonWKT,
    parseCapPolygon
};
