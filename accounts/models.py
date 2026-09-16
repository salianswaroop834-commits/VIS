import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    CUSTOMER = 'CUSTOMER', 'Customer'
    UNDERWRITER = 'UNDERWRITER', 'Underwriter'
    CLAIMS_HANDLER = 'CLAIMS_HANDLER', 'Claims Handler'
    ADMINISTRATOR = 'ADMINISTRATOR', 'Administrator'


class User(AbstractUser):
    """
    Custom user model for Nexisure platform.
    Key features:
    - UUID primary key for Supabase alignment
    - Email as primary unique identifier
    - Explicit role-based access control
    - Direct hook for Supabase auth synchronization
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField('Email Address', unique=True, db_index=True)
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.CUSTOMER,
        db_index=True,
    )
    phone_number = models.CharField(max_length=20, blank=True, db_index=True)
    supabase_uid = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text='Associated Supabase Auth User ID',
    )
    email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER

    @property
    def is_underwriter(self) -> bool:
        return self.role == UserRole.UNDERWRITER

    @property
    def is_claims_handler(self) -> bool:
        return self.role == UserRole.CLAIMS_HANDLER

    @property
    def is_administrator(self) -> bool:
        return self.role == UserRole.ADMINISTRATOR or self.is_superuser

    @property
    def underwriter_profile(self):
        """Direct accessor to specialized UnderwriterProfile via staff_profile."""
        if hasattr(self, 'staff_profile') and hasattr(self.staff_profile, 'underwriter_profile'):
            return self.staff_profile.underwriter_profile
        return None

    @property
    def claims_handler_profile(self):
        """Direct accessor to specialized ClaimsHandlerProfile via staff_profile."""
        if hasattr(self, 'staff_profile') and hasattr(self.staff_profile, 'claims_handler_profile'):
            return self.staff_profile.claims_handler_profile
        return None


class EmailOtpToken(models.Model):
    """
    Secure One-Time Passcode (OTP) token entity for passwordless authentication.
    Stores cryptographically hashed tokens, expiry limits, and attempt tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    attempts_count = models.PositiveIntegerField(default=0)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='otp_tokens',
    )

    class Meta:
        verbose_name = 'Email OTP Token'
        verbose_name_plural = 'Email OTP Tokens'
        ordering = ['-created_at']

    def __str__(self):
        status = 'USED' if self.is_used else 'VALID'
        return f"OTP for {self.email} ({status}) expires {self.expires_at:%H:%M:%S}"
