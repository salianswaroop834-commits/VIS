from django.db import models
from django.conf import settings
from core.models import AuditableModel
from customers.models import CustomerProfile
from policies.models import Policy


class ServiceRequestType(models.TextChoices):
    POLICY_RENEWAL = 'POLICY_RENEWAL', 'Policy Renewal Request'
    ADDRESS_UPDATE = 'ADDRESS_UPDATE', 'Address / Contact Update'
    VEHICLE_UPDATE = 'VEHICLE_UPDATE', 'Vehicle Information Update'
    DOCUMENT_REQUEST = 'DOCUMENT_REQUEST', 'Policy Document / Certificate Request'
    COVERAGE_CHANGE = 'COVERAGE_CHANGE', 'Coverage / Endorsement Modification'
    POLICY_SERVICE = 'POLICY_SERVICE', 'Policy Service Query'
    VEHICLE_SERVICE = 'VEHICLE_SERVICE', 'Vehicle Service Query'
    ENDORSEMENT = 'ENDORSEMENT', 'Endorsement / Modification'
    OTHER = 'OTHER', 'General Servicing Query'


class ServiceRequestStatus(models.TextChoices):
    SUBMITTED = 'SUBMITTED', 'Submitted'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    RESOLVED = 'RESOLVED', 'Resolved / Completed'
    REJECTED = 'REJECTED', 'Rejected'


class ServiceRequest(AuditableModel):
    """
    Policy service request entity.
    Allows customers to initiate servicing requests that underwriters
    or operations staff can review, action, and complete.
    """
    request_number = models.CharField(max_length=40, unique=True, db_index=True)
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name='service_requests',
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_requests',
    )
    request_type = models.CharField(
        max_length=30,
        choices=ServiceRequestType.choices,
        default=ServiceRequestType.POLICY_RENEWAL,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=ServiceRequestStatus.choices,
        default=ServiceRequestStatus.SUBMITTED,
        db_index=True,
    )
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_service_requests',
    )
    change_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured parameter changes for policy endorsement adjudication',
    )
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Service Request'
        verbose_name_plural = 'Service Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.request_number} - {self.get_request_type_display()} ({self.status})"
