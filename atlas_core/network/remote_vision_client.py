import os
import json
import urllib.request
import urllib.error
import urllib.parse
import time
from typing import Dict, Any, Optional

class RemoteVisionClient:
    """
    Centralized HTTP client for the remote ATLAS Vision subsystem (10.9.96.13:8765).

    Designed around the REAL Vision API contract (confirmed v1.5.0, contract_version 1.0):
      GET  /health                     → {status, service, version, contract_version, camera}
      GET  /api/v1/vision/status       → {service, status, camera_status, recognition_status, active_tracks, ...}
      GET  /api/v1/incidents           → QUERY_RESPONSE envelope with data.incidents list
      GET  /api/v1/incidents/recent    → QUERY_RESPONSE envelope with data.incidents list (recent)
      GET  /api/v1/security/alerts     → QUERY_RESPONSE envelope with data.alerts list

    NOTE: The following are NOT supported by the current Vision API:
      - POST /api/v1/events            (Vision does not accept incoming events from OS)
      - POST /api/v1/commands/acknowledge  (not exposed by Vision)
      - POST /api/v1/commands/resolve      (not exposed by Vision)
      - POST /api/v1/vision/sync       (Identity sync — not on remote Vision)
      - POST /api/v1/vision/biometric-sync (Biometric sync — not on remote Vision)

    The Vision→OS event direction is handled by polling from OS side.
    Automatic Vision event push to OS is a Vision-side task (requires ATLAS_OS_URL on Vision).

    All methods return a safe dict — never raise exceptions.
    """

    # Real Vision API endpoints (confirmed by live probing 2026-08-27)
    ENDPOINT_HEALTH          = "/health"
    ENDPOINT_STATUS          = "/api/v1/vision/status"
    ENDPOINT_INCIDENTS       = "/api/v1/incidents"
    ENDPOINT_INCIDENTS_RECENT= "/api/v1/incidents/recent"
    ENDPOINT_ALERTS          = "/api/v1/security/alerts"

    def __init__(self):
        self.enabled = os.environ.get("ATLAS_VISION_ENABLED", "true").lower() == "true"
        self.base_url = os.environ.get("ATLAS_VISION_BASE_URL", "http://10.9.96.13:8765").rstrip("/")

        try:
            self.timeout = float(os.environ.get("ATLAS_VISION_TIMEOUT", "10"))
        except ValueError:
            self.timeout = 10.0

        self.integration_token = os.environ.get("ATLAS_VISION_INTEGRATION_TOKEN", "")

    # ────────────────────────────────────────────────────────────────────────
    # Internal HTTP helper
    # ────────────────────────────────────────────────────────────────────────

    def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request and return a safe result dict."""
        if not self.enabled:
            return {"status": "disabled", "error": "Remote Vision integration is disabled."}

        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        req_data = None
        if data is not None:
            req_data = json.dumps(data).encode("utf-8")

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.integration_token:
            headers["Authorization"] = f"Bearer {self.integration_token}"

        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read().decode("utf-8")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"status": "success", "raw_response": content}

        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
                detail = json.loads(error_body)
            except Exception:
                detail = e.reason
            return {
                "status": "error",
                "error_type": "http_error",
                "code": e.code,
                "detail": detail,
            }
        except urllib.error.URLError as e:
            return {
                "status": "offline",
                "error_type": "unreachable",
                "detail": f"Remote Vision unreachable at {self.base_url}: {e.reason}",
            }
        except (TimeoutError, OSError) as e:
            return {
                "status": "error",
                "error_type": "timeout",
                "detail": str(e),
            }
        except Exception as e:
            return {
                "status": "error",
                "error_type": "exception",
                "detail": str(e),
            }

    # ────────────────────────────────────────────────────────────────────────
    # Public API — Health & Status (confirmed working)
    # ────────────────────────────────────────────────────────────────────────

    def get_health(self) -> Dict[str, Any]:
        """
        GET /health
        Returns: {status, service, version, contract_version, camera: {status}}
        """
        return self._make_request("GET", self.ENDPOINT_HEALTH)

    def get_status(self) -> Dict[str, Any]:
        """
        GET /api/v1/vision/status
        Returns: {service, status, camera_status, recognition_status, active_tracks, headless, server_port}
        """
        return self._make_request("GET", self.ENDPOINT_STATUS)

    # ────────────────────────────────────────────────────────────────────────
    # Public API — Incidents (confirmed working, uses QUERY_RESPONSE envelope)
    # ────────────────────────────────────────────────────────────────────────

    def get_incidents(self) -> Dict[str, Any]:
        """
        GET /api/v1/incidents
        Response envelope: {contract_version, message_type, query_type, data: {incidents: [...]}, error}
        """
        return self._make_request("GET", self.ENDPOINT_INCIDENTS)

    def get_recent_incidents(self) -> Dict[str, Any]:
        """
        GET /api/v1/incidents/recent
        Response envelope: {contract_version, message_type, query_type, data: {incidents: [...]}, error}
        """
        return self._make_request("GET", self.ENDPOINT_INCIDENTS_RECENT)

    # ────────────────────────────────────────────────────────────────────────
    # Public API — Security Alerts (confirmed working)
    # ────────────────────────────────────────────────────────────────────────

    def get_security_alerts(self) -> Dict[str, Any]:
        """
        GET /api/v1/security/alerts
        Response envelope: {contract_version, message_type, query_type, data: {alerts: [...]}, error}
        """
        return self._make_request("GET", self.ENDPOINT_ALERTS)

    # ────────────────────────────────────────────────────────────────────────
    # NOT SUPPORTED — documented explicitly to prevent silent failures
    # ────────────────────────────────────────────────────────────────────────

    def acknowledge_command(self, incident_id: str) -> Dict[str, Any]:
        """
        NOT SUPPORTED by the current remote Vision API (v1.5.0).
        Returns an explicit unsupported response — never silently pretends to work.
        """
        return {
            "status": "unsupported",
            "detail": (
                "Remote ATLAS Vision v1.5.0 does not expose an acknowledge command endpoint. "
                "This capability must be added on the Vision machine before it can be used."
            ),
            "incident_id": incident_id,
        }

    def resolve_command(self, incident_id: str, resolution_notes: str = "") -> Dict[str, Any]:
        """
        NOT SUPPORTED by the current remote Vision API (v1.5.0).
        Returns an explicit unsupported response — never silently pretends to work.
        """
        return {
            "status": "unsupported",
            "detail": (
                "Remote ATLAS Vision v1.5.0 does not expose a resolve command endpoint. "
                "This capability must be added on the Vision machine before it can be used."
            ),
            "incident_id": incident_id,
            "notes": resolution_notes,
        }

    def get_incident_details(self, incident_id: str) -> Dict[str, Any]:
        """
        NOT SUPPORTED by the current remote Vision API (v1.5.0).
        Individual incident lookup by ID is not exposed.
        """
        return {
            "status": "unsupported",
            "detail": "Individual incident lookup is not exposed by Vision v1.5.0.",
            "incident_id": incident_id,
        }

    # ────────────────────────────────────────────────────────────────────────
    # Connectivity helper
    # ────────────────────────────────────────────────────────────────────────

    def connection_state(self) -> str:
        """
        Returns one of: ONLINE | OFFLINE | DISABLED | UNAVAILABLE
        Uses /health to determine reachability.
        """
        if not self.enabled:
            return "DISABLED"
        result = self.get_health()
        s = result.get("status", "")
        if s == "disabled":
            return "DISABLED"
        elif s in ("offline",):
            return "OFFLINE"
        elif s in ("error",):
            return "UNAVAILABLE"
        elif result.get("error_type") in ("unreachable", "timeout"):
            return "OFFLINE"
        else:
            return "ONLINE"
