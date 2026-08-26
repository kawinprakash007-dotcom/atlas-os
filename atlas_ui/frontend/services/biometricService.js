export class BiometricService {
    static async _safeParseJson(response) {
        const rawText = await response.text();
        let data = {};
        if (rawText) {
            try {
                data = JSON.parse(rawText);
            } catch (error) {
                console.error("[BIOMETRIC] Backend returned non-JSON response:", rawText);
                throw new Error(`Server returned an invalid response (HTTP ${response.status})`);
            }
        }
        return data;
    }

    static async getStatus(personId) {
        const response = await fetch(`/api/v1/biometric/status/${personId}`);
        const data = await BiometricService._safeParseJson(response);
        if (!response.ok) {
            throw new Error(data.message || "Failed to fetch biometric status");
        }
        return data;
    }

    static async enroll(personId, imageData = null) {
        const payload = { person_id: personId };
        if (imageData) {
            payload.image_data = imageData;
        }
        const response = await fetch("/api/v1/biometric/enroll", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });
        const data = await BiometricService._safeParseJson(response);
        if (!response.ok) {
            throw new Error(data.message || data.reason || "Enrollment failed");
        }
        return data;
    }

    static async verify(personId, imageData = null, locationData = null) {
        const payload = { person_id: personId };
        if (imageData) {
            payload.image_data = imageData;
        }
        // Attach GPS when available — backend accepts null gracefully
        if (locationData) {
            payload.gps_location = {
                latitude:  locationData.latitude,
                longitude: locationData.longitude,
                accuracy:  locationData.accuracy,
                timestamp: locationData.timestamp,
                status:    locationData.status,
            };
        }
        const response = await fetch("/api/v1/biometric/verify", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });
        const data = await BiometricService._safeParseJson(response);
        // Return data even on 400 (re-enrollment) or 409 (camera busy) to handle gracefully in UI
        if (!response.ok && response.status === 500) {
            throw new Error(data.message || "Verification failed due to server error");
        }
        return data;
    }

    static async reset(username, password) {
        const response = await fetch("/api/v1/biometric/reset", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ username, password })
        });
        const data = await BiometricService._safeParseJson(response);
        if (!response.ok) {
            throw new Error(data.message || "Failed to reset biometric profile");
        }
        return data;
    }
}
