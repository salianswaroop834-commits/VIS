from django.db import models
from django.conf import settings
from core.models import AuditableModel


class GenderChoices(models.TextChoices):
    MALE = 'MALE', 'Male'
    FEMALE = 'FEMALE', 'Female'
    OTHER = 'OTHER', 'Other'
    PREFER_NOT_TO_SAY = 'PREFER_NOT_TO_SAY', 'Prefer Not To Say'


class CustomerProfile(AuditableModel):
    """
    Profile entity storing customer-specific vehicle insurance details.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='customer_profile',
    )
    customer_code = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        help_text='Unique identifier e.g., CUST-100234',
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=20,
        choices=GenderChoices.choices,
        blank=True,
    )
    driving_license_number = models.CharField(max_length=50, blank=True)
    driving_license_expiry = models.DateField(null=True, blank=True)
    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    is_identity_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Customer Profile'
        verbose_name_plural = 'Customer Profiles'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer_code} - {self.user.email}"

    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.user.get_full_name() or self.user.email

    @property
    def active_staff_assignment(self):
        """Returns active StaffCustomerAssignment if one exists."""
        return self.staff_assignments.filter(status='ACTIVE').first()


class KYCStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PHONE_OTP_REQUIRED = 'PHONE_OTP_REQUIRED', 'Phone OTP Required'
    VERIFIED = 'VERIFIED', 'Verified'
    FAILED = 'FAILED', 'Failed'
    EXPIRED = 'EXPIRED', 'Expired'


class KYCVerification(AuditableModel):
    """
    Dedicated KYC & identity verification record for PAN/Aadhaar workflows.
    Protects user privacy by storing only masked identifiers.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kyc_verifications',
    )
    verification_type = models.CharField(
        max_length=30,
        default='PAN',
        choices=[('PAN', 'Permanent Account Number (PAN)')],
    )
    document_number_masked = models.CharField(
        max_length=30,
        help_text='Masked document identifier e.g. ABCDE****F',
    )
    provider = models.CharField(max_length=50, default='RAPIDAPI')
    provider_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=30,
        choices=KYCStatus.choices,
        default=KYCStatus.PENDING,
        db_index=True,
    )
    name_match = models.BooleanField(null=True, blank=True)
    dob_match = models.BooleanField(null=True, blank=True)
    phone_match = models.BooleanField(null=True, blank=True)
    verified_phone_masked = models.CharField(
        max_length=20,
        blank=True,
        help_text='Masked mobile number e.g. ******1234',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'KYC Verification'
        verbose_name_plural = 'KYC Verifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"KYC ({self.verification_type}) {self.document_number_masked} - {self.status}"


class CustomerFeedback(AuditableModel):
    """
    Customer feedback and Net Promoter Score (NPS) recording.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedbacks',
    )
    nps_score = models.PositiveSmallIntegerField(help_text='NPS Score 0-10')
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Customer Feedback'
        verbose_name_plural = 'Customer Feedbacks'
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Feedback by {self.user.email} (NPS: {self.nps_score})"
