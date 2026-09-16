from typing import Optional, Dict, Any
from django.utils import timezone
from audit.models import AuditLog, AuditAction
from accounts.models import User


class AuditService:
    """
    Centralized compliance and non-repudiation audit logging service.
    Guarantees immutable records of state mutations across policies,
    claims, staff workload reassignment, and automated tools.
    """

    SENSITIVE_KEYS = {
        'password', 'password1', 'password2', 'token', 'access_token', 'refresh_token',
        'otp', 'otp_code', 'code', 'secret', 'secret_key', 'api_key', 'private_key',
        'card_number', 'cvv', 'cvc', 'security_code', 'credentials', 'auth_token'
    }

    @classmethod
    def sanitize_details(cls, data: Any) -> Any:
        """
        Recursively sanitizes details payloads to strip or redact sensitive values
        (passwords, tokens, OTPs, CVVs, API keys, credentials).
        """
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if any(sensitive in str(k).lower() for sensitive in cls.SENSITIVE_KEYS):
                    clean[k] = "[REDACTED]"
                else:
                    clean[k] = cls.sanitize_details(v)
            return clean
        elif isinstance(data, (list, tuple)):
            return [cls.sanitize_details(item) for item in data]
        return data

    @classmethod
    def log(
        cls,
        action: str,
        target_entity: str,
        target_id: str,
        actor: Optional[User] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        is_success: bool = True,
    ) -> AuditLog:
        """
        Creates an immutable audit log entry.
        """
        if details is None:
            details = {}

        clean_details = cls.sanitize_details(details)

        actor_email = ""
        actor_role = "SYSTEM"

        if actor and getattr(actor, 'is_authenticated', True):
            actor_email = getattr(actor, 'email', '')
            actor_role = getattr(actor, 'role', 'SYSTEM')

        entry = AuditLog.objects.create(
            actor=actor if actor and getattr(actor, 'pk', None) else None,
            actor_email=actor_email,
            actor_role=actor_role,
            action=action,
            target_entity=target_entity,
            target_id=str(target_id),
            details=clean_details,
            ip_address=ip_address,
            is_success=is_success,
        )
        return entry

    @classmethod
    def get_logs_for_entity(cls, target_entity: str, target_id: str):
        """Returns chronological audit records for a given target entity."""
        return AuditLog.objects.filter(
            target_entity=target_entity,
            target_id=str(target_id),
        ).order_by('-created_at')
