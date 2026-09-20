"""
Base Service Layer and Data Normalization / Validation Foundation.
Enforces separation of concerns:
- Validation decides if data meets domain constraints.
- Normalization cleanses and standardizes valid input prior to persistence.
- Services encapsulate business transactions without polluting views or models.
"""

import re
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ServiceValidationError(Exception):
    """Domain-level validation failure carrying field-specific errors."""
    def __init__(self, message: str, errors: Optional[Dict[str, List[str]]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or {}


@dataclass
class ValidationResult:
    """Standardized outcome for validation operations."""
    is_valid: bool
    errors: Dict[str, List[str]] = field(default_factory=dict)
    cleaned_data: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, field_name: str, error_message: str):
        self.is_valid = False
        if field_name not in self.errors:
            self.errors[field_name] = []
        self.errors[field_name].append(error_message)


class DataNormalizer:
    """
    Standardizes user and system inputs before persistence.
    Transparently applied according to business rules.
    """

    @staticmethod
    def normalize_registration_number(reg_num: str) -> str:
        """Uppercase, strip whitespace and special punctuation from vehicle license plates."""
        if not reg_num:
            return ""
        # Keep alphanumeric characters and uppercase them
        return re.sub(r'[^A-Z0-9]', '', reg_num.strip().upper())

    @staticmethod
    def normalize_vin_or_chassis(chassis: str) -> str:
        """Uppercase and strip whitespace from VIN/Chassis numbers."""
        if not chassis:
            return ""
        return re.sub(r'[^A-HJ-NPR-Z0-9]', '', chassis.strip().upper())

    @staticmethod
    def normalize_email(email: str) -> str:
        """Strip whitespace and lowercase email."""
        if not email:
            return ""
        return email.strip().lower()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Extract digits and optional leading plus sign."""
        if not phone:
            return ""
        cleaned = re.sub(r'[^\d+]', '', phone.strip())
        return cleaned

    @staticmethod
    def normalize_text(text: str) -> str:
        """Strip leading/trailing whitespace and collapse internal whitespace."""
        if not text:
            return ""
        return " ".join(text.strip().split())


class BaseService:
    """
    Abstract base service providing standardized logging and validation helpers.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__module__)

    def log_action(self, action_name: str, details: Dict[str, Any]):
        self.logger.info(f"[{self.__class__.__name__}] {action_name}: {details}")


class NotificationService:
    """
    In-app notification dispatcher.
    Creates Notification records for authenticated users.
    Never raises exceptions — notification failure must not break primary workflows.
    """

    @staticmethod
    def notify(
        recipient,
        title: str,
        message: str,
        notification_type: str = 'GENERAL',
        action_url: str = '',
    ) -> Optional[Any]:
        """
        Creates a Notification record for the given recipient.
        Silently logs and returns None on failure — never propagates exceptions.
        """
        try:
            from core.models import Notification
            return Notification.objects.create(
                recipient=recipient,
                title=title,
                message=message,
                notification_type=notification_type,
                action_url=action_url,
            )
        except Exception as exc:
            logger.error(f"[NotificationService] Failed to create notification for {getattr(recipient, 'email', '?')}: {exc}")
            return None

    @staticmethod
    def notify_claim_status_change(recipient, claim_number: str, new_status: str, action_url: str = '') -> None:
        """Convenience method for claim status change notifications."""
        NotificationService.notify(
            recipient=recipient,
            title=f"Claim {claim_number} Status Update",
            message=f"Your claim {claim_number} has been updated to status: {new_status}.",
            notification_type='CLAIM_STATUS',
            action_url=action_url,
        )

    @staticmethod
    def notify_policy_renewal_reminder(recipient, policy_number: str, days_remaining: int, action_url: str = '') -> None:
        """Convenience method for policy renewal reminders."""
        NotificationService.notify(
            recipient=recipient,
            title=f"Policy {policy_number} — Renewal Reminder",
            message=f"Your policy {policy_number} expires in {days_remaining} days. Please renew to maintain uninterrupted coverage.",
            notification_type='RENEWAL_REMINDER',
            action_url=action_url,
        )

    @staticmethod
    def mark_read(user, notification_id) -> bool:
        """Marks a notification as read for the given user."""
        try:
            from core.models import Notification
            updated = Notification.objects.filter(
                id=notification_id,
                recipient=user,
            ).update(is_read=True)
            return updated > 0
        except Exception:
            return False

    @staticmethod
    def get_unread_count(user) -> int:
        """Returns the count of unread notifications for a user."""
        try:
            from core.models import Notification
            return Notification.objects.filter(recipient=user, is_read=False).count()
        except Exception:
            return 0

