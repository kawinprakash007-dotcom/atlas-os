import time

class RiskCalculator:
    @staticmethod
    def calculate_risk(person, audit_records):
        """
        Calculates the risk level and reasons based on the person's profile
        and their recent audit history.
        
        Returns:
            {"level": "LOW|MEDIUM|HIGH", "reasons": list[str]}
        """
        if not person:
            return {"level": "LOW", "reasons": ["User data unavailable"]}

        level = "LOW"
        reasons = []

        # 1. Profile-level checks
        if getattr(person, 'account_lock_status', False):
            level = "HIGH"
            reasons.append("Account is currently locked due to security policy")
        
        # 2. Audit history checks
        now = time.time()
        one_hour_ago = now - 3600

        # Filter recent records (last 1 hour)
        recent_records = [r for r in audit_records if r.timestamp >= one_hour_ago]

        failed_logins = [r for r in recent_records if r.event_type == "LOGIN_FAILED" or (r.event_type.startswith("LOGIN") and r.access_result != "SUCCESS")]
        failed_biometrics = [r for r in recent_records if r.event_type == "BIOMETRIC_FAILED" or (r.event_type.startswith("BIOMETRIC") and r.access_result != "SUCCESS")]
        denied_accesses = [r for r in recent_records if "DENIED" in r.event_type or r.access_result == "DENIED"]

        # HIGH risk conditions
        if len(failed_logins) >= 5 or len(denied_accesses) >= 3 or level == "HIGH":
            level = "HIGH"
            if len(failed_logins) >= 5:
                reasons.append(f"{len(failed_logins)} failed login attempts in the last hour")
            if len(denied_accesses) >= 3:
                reasons.append(f"{len(denied_accesses)} denied access attempts in the last hour")

        # MEDIUM risk conditions (if not already HIGH)
        elif len(failed_logins) >= 2 or len(failed_biometrics) >= 2 or getattr(person, 'failed_login_attempts', 0) > 2:
            level = "MEDIUM"
            if len(failed_logins) >= 2:
                reasons.append(f"{len(failed_logins)} failed login attempts in the last hour")
            elif getattr(person, 'failed_login_attempts', 0) > 2:
                reasons.append(f"Multiple recent failed login attempts ({getattr(person, 'failed_login_attempts', 0)} total)")
            if len(failed_biometrics) >= 2:
                reasons.append(f"{len(failed_biometrics)} failed biometric verifications in the last hour")
            if len(denied_accesses) > 0:
                reasons.append(f"{len(denied_accesses)} denied access attempts in the last hour")

        # LOW risk conditions
        if level == "LOW":
            if len(recent_records) > 0:
                reasons.append("Normal successful access")
            else:
                reasons.append("No recent failures")

        return {
            "level": level,
            "reasons": reasons
        }
