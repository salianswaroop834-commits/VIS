import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    USER = 'USER', 'Customer'
    STAFF = 'STAFF', 'Staff'
    ADMIN = 'ADMIN', 'Administrator'


class RoleValue(str):
    def __new__(cls, val, specialization=None):
        instance = super().__new__(cls, val)
        instance.specialization = specialization
        return instance

    def __eq__(self, other):
        if super().__eq__(other):
            return True
        if self.specialization and other == self.specialization:
            return True
        return False

    def __hash__(self):
        return super().__hash__()


# Backward compatibility aliases for existing tests and call sites
UserRole.CUSTOMER = RoleValue('USER', 'CUSTOMER')
UserRole.UNDERWRITER = RoleValue('STAFF', 'UNDERWRITER')
UserRole.CLAIMS_HANDLER = RoleValue('STAFF', 'CLAIMS_HANDLER')
UserRole.ADMINISTRATOR = RoleValue('ADMIN', 'ADMINISTRATOR')


class User(AbstractUser):
    """
    Custom user model for Nexisure platform.
    Key features:
    - UUID primary key for Supabase alignment
    - Email as primary unique identifier
    - Explicit 3-role access control (USER, STAFF, ADMIN)
    - Direct hook for Supabase auth synchronization
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField('Email Address', unique=True, db_index=True)
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.USER,
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
    phone_verified = models.BooleanField(default=False)
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

    def save(self, *args, **kwargs):
        spec = getattr(self.role, 'specialization', None)
        auto_dept = None
        if spec == 'CLAIMS_HANDLER' or self.role == 'CLAIMS_HANDLER':
            self.role = UserRole.STAFF
            self._specialization = 'CLAIMS'
            auto_dept = 'CLAIMS'
            self.is_staff = True
        elif spec == 'UNDERWRITER' or self.role == 'UNDERWRITER':
            self.role = UserRole.STAFF
            self._specialization = 'UNDERWRITING'
            auto_dept = 'UNDERWRITING'
            self.is_staff = True
        elif spec == 'CUSTOMER' or self.role == 'CUSTOMER':
            self.role = UserRole.USER
        elif spec == 'ADMINISTRATOR' or self.role == 'ADMINISTRATOR':
            self.role = UserRole.ADMIN
            self.is_staff = True
        elif self.role == UserRole.STAFF:
            self.is_staff = True
        elif self.role == UserRole.ADMIN:
            self.is_staff = True

        super().save(*args, **kwargs)

        if auto_dept:
            from apps.staff.models import StaffProfile
            if not StaffProfile.objects.filter(user=self).exists():
                code_suffix = self.pk.hex[:6].upper() if hasattr(self.pk, 'hex') else str(self.pk)[:6].upper()
                prefix = 'CLM' if auto_dept == 'CLAIMS' else 'UW'
                StaffProfile.objects.create(
                    user=self,
                    staff_code=f"{prefix}-{code_suffix}",
                    department=auto_dept,
                )

    @property
    def is_customer(self) -> bool:
        return self.role in (UserRole.USER, 'CUSTOMER')

    @property
    def is_staff_member(self) -> bool:
        return self.role in (UserRole.STAFF, 'UNDERWRITER', 'CLAIMS_HANDLER')

    @property
    def is_underwriter(self) -> bool:
        if self.role == 'UNDERWRITER' or getattr(self.role, 'specialization', None) == 'UNDERWRITER':
            return True
        if getattr(self, '_specialization', None) == 'UNDERWRITING':
            return True
        if self.role == UserRole.STAFF:
            if hasattr(self, 'staff_profile'):
                dept = getattr(self.staff_profile, 'department', '').upper()
                if 'UNDERWRIT' in dept:
                    return True
                if hasattr(self.staff_profile, 'underwriter_profile'):
                    return True
                if not hasattr(self.staff_profile, 'claims_handler_profile') and not ('CLAIM' in dept):
                    return True
        return False

    @property
    def is_claims_handler(self) -> bool:
        if self.role == 'CLAIMS_HANDLER' or getattr(self.role, 'specialization', None) == 'CLAIMS_HANDLER':
            return True
        if getattr(self, '_specialization', None) == 'CLAIMS':
            return True
        if self.role == UserRole.STAFF:
            if hasattr(self, 'staff_profile'):
                dept = getattr(self.staff_profile, 'department', '').upper()
                if 'CLAIM' in dept:
                    return True
                if hasattr(self.staff_profile, 'claims_handler_profile'):
                    return True
        return False

    @property
    def is_administrator(self) -> bool:
        return self.role in (UserRole.ADMIN, 'ADMINISTRATOR') or self.is_superuser

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
    purpose = models.CharField(max_length=30, default='LOGIN')
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

