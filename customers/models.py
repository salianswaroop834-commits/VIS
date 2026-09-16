from django.db import models
from django.conf import settings
from core.models import AuditableModel


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
    date_of_birth = models.DateField(null=True, blank=True)
    driving_license_number = models.CharField(max_length=50, blank=True)
    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    is_identity_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Customer Profile'
        verbose_name_plural = 'Customer Profiles'

    def __str__(self):
        return f"{self.customer_code} - {self.user.email}"
