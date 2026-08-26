/**
 * ATLAS OS — Location Service
 *
 * Wraps the browser Geolocation API with a never-throws, Promise-based
 * interface.  Callers always receive a result object; the GPS failure path
 * is NOT an error — it is a normal outcome.
 *
 * Result shape:
 *   {
 *     latitude:   number | null,
 *     longitude:  number | null,
 *     accuracy:   number | null,   // metres
 *     timestamp:  number | null,   // Unix epoch seconds (converted from ms)
 *     status:     "granted" | "denied" | "unavailable" | "unsupported"
 *   }
 *
 * Rules:
 *   - NEVER imported at module load time with side-effects
 *   - The permission prompt is triggered only when requestLocation() is called
 *   - All Promise rejections are caught internally; the outer promise always resolves
 *   - A 5-second timeout aborts stale GPS requests gracefully
 */

const GPS_TIMEOUT_MS = 5000;

/**
 * Request the browser's current GPS position.
 * Returns a resolved Promise with a location result object.
 * Never rejects — GPS failure is a normal, handled outcome.
 *
 * @returns {Promise<{latitude, longitude, accuracy, timestamp, status}>}
 */
export function requestLocation() {
    return new Promise((resolve) => {
        // Guard: Geolocation API not present in this browser / context
        if (!navigator.geolocation) {
            resolve({
                latitude: null,
                longitude: null,
                accuracy: null,
                timestamp: null,
                status: "unsupported",
            });
            return;
        }

        const timeoutId = setTimeout(() => {
            resolve({
                latitude: null,
                longitude: null,
                accuracy: null,
                timestamp: null,
                status: "unavailable",
            });
        }, GPS_TIMEOUT_MS + 500); // slight buffer beyond the API timeout

        navigator.geolocation.getCurrentPosition(
            // Success
            (position) => {
                clearTimeout(timeoutId);
                resolve({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    // Browser returns ms; store as Unix seconds for backend consistency
                    timestamp: position.timestamp / 1000,
                    status: "granted",
                });
            },
            // Error
            (err) => {
                clearTimeout(timeoutId);
                // GeolocationPositionError codes:
                //   1 = PERMISSION_DENIED
                //   2 = POSITION_UNAVAILABLE
                //   3 = TIMEOUT
                const status =
                    err.code === 1 ? "denied" : "unavailable";
                resolve({
                    latitude: null,
                    longitude: null,
                    accuracy: null,
                    timestamp: null,
                    status,
                });
            },
            {
                enableHighAccuracy: false,  // battery-friendly; accuracy is best-effort
                timeout: GPS_TIMEOUT_MS,
                maximumAge: 30000,          // accept a 30-second cached fix
            }
        );
    });
}

/**
 * Build a compact status badge HTML snippet for display in the UI.
 *
 * @param {{status: string, accuracy: number|null}} locationResult
 * @returns {string} HTML string
 */
export function buildLocationBadgeHtml(locationResult) {
    if (!locationResult) {
        return `<span class="loc-badge loc-unavailable">&#9679; Location Unavailable</span>`;
    }

    switch (locationResult.status) {
        case "granted":
            const acc = locationResult.accuracy != null
                ? ` &mdash; &plusmn;${Math.round(locationResult.accuracy)}m`
                : "";
            return `<span class="loc-badge loc-granted">&#9679; Location Captured${acc}</span>`;

        case "denied":
            return `<span class="loc-badge loc-denied">&#9679; Permission Denied</span>`;

        case "unsupported":
        case "unavailable":
        default:
            return `<span class="loc-badge loc-unavailable">&#9679; Location Unavailable</span>`;
    }
}
