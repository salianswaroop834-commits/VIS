import uuid
from typing import Optional, List, Dict, Any
from django.utils import timezone
from apps.service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
from apps.customers.models import CustomerProfile
from apps.policies.models import Policy
from apps.accounts.models import User
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService
from core.services import ServiceValidationError, DataNormalizer


class ServiceRequestService:
    """
    Manages customer policy servicing requests:
    - Renewal submissions, endorsement requests, contact updates
    - Status transitions and resolution workflows
    - Enforces financial immutability and state machine validity
    """

    IMMUTABLE_FINANCIAL_FIELDS = {
        'premium_amount',
        'deductible_amount',
        'idv',
        'vehicle_value',
        'base_rate',
        'base_premium',
        'total_premium',
        'calculated_premium',
    }

    VALID_TRANSITIONS = {
        ServiceRequestStatus.SUBMITTED: [
            ServiceRequestStatus.IN_PROGRESS,
            ServiceRequestStatus.RESOLVED,
            ServiceRequestStatus.REJECTED,
        ],
        ServiceRequestStatus.IN_PROGRESS: [
            ServiceRequestStatus.RESOLVED,
            ServiceRequestStatus.REJECTED,
        ],
        ServiceRequestStatus.RESOLVED: [],  # Terminal
        ServiceRequestStatus.REJECTED: [],  # Terminal
    }

    @classmethod
    def create_service_request(
        cls,
        customer: CustomerProfile,
        request_type: str,
        title: str,
        description: str,
        policy: Optional[Policy] = None,
        change_payload: Optional[Dict[str, Any]] = None,
    ) -> ServiceRequest:
        """
        Creates a new customer service request.
        Validates ownership, request type, and enforces financial field immutability.
        """
        if request_type not in ServiceRequestType.values:
            raise ServiceValidationError(f"Invalid service request type: '{request_type}'.")

        clean_title = DataNormalizer.normalize_text(title)
        clean_desc = DataNormalizer.normalize_text(description)
        if not clean_title or not clean_desc:
            raise ServiceValidationError("Title and description are required for a service request.")

        if policy and policy.customer != customer:
            raise ServiceValidationError("You may only file service requests against your own policies.")

        # Guard: Financial immutability check on change_payload
        payload = change_payload or {}
        if isinstance(payload, dict):
            for field in payload.keys():
                if field.lower() in cls.IMMUTABLE_FINANCIAL_FIELDS:
                    raise ServiceValidationError(
                        f"Cannot modify immutable financial policy field '{field}' through service request."
                    )

        year = timezone.now().year
        req_num = f"SRV-{year}-{uuid.uuid4().hex[:8].upper()}"

        srv = ServiceRequest.objects.create(
            request_number=req_num,
            customer=customer,
            policy=policy,
            request_type=request_type,
            title=clean_title,
            description=clean_desc,
            change_payload=payload,
            status=ServiceRequestStatus.SUBMITTED,
        )

        AuditService.log(
            action=AuditAction.SERVICE_REQUEST_CREATED,
            target_entity='ServiceRequest',
            target_id=str(srv.pk),
            actor=customer.user,
            details={
                'request_number': srv.request_number,
                'request_type': srv.request_type,
                'title': srv.title,
                'has_payload': bool(payload),
            }
        )

        return srv

    @classmethod
    def update_status(
        cls,
        service_request: ServiceRequest,
        staff_user: User,
        new_status: str,
        resolution_notes: str = "",
    ) -> ServiceRequest:
        """
        Staff updates the state of a service request.
        Enforces state machine transitions and audit trails.
        """
        if new_status not in ServiceRequestStatus.values:
            raise ServiceValidationError(f"Invalid status: '{new_status}'.")

        current_status = service_request.status

        # Terminal state protection
        if current_status in (ServiceRequestStatus.RESOLVED, ServiceRequestStatus.REJECTED):
            raise ServiceValidationError(
                f"Cannot update service request in terminal state '{current_status}'."
            )

        # Transition validation
        allowed_next = cls.VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed_next:
            raise ServiceValidationError(
                f"Invalid state transition from '{current_status}' to '{new_status}'."
            )

        service_request.status = new_status
        service_request.assigned_staff = staff_user
        if resolution_notes:
            service_request.resolution_notes = DataNormalizer.normalize_text(resolution_notes)

        if new_status in (ServiceRequestStatus.RESOLVED, ServiceRequestStatus.REJECTED):
            service_request.resolved_at = timezone.now()

        service_request.save()

        # Audit action mapping
        if new_status == ServiceRequestStatus.RESOLVED:
            audit_action = AuditAction.SERVICE_REQUEST_RESOLVED
        elif new_status == ServiceRequestStatus.REJECTED:
            audit_action = AuditAction.SERVICE_REQUEST_REJECTED
        else:
            audit_action = AuditAction.SERVICE_REQUEST_UPDATED

        AuditService.log(
            action=audit_action,
            target_entity='ServiceRequest',
            target_id=str(service_request.pk),
            actor=staff_user,
            details={
                'request_number': service_request.request_number,
                'previous_status': current_status,
                'new_status': new_status,
                'resolution_notes': resolution_notes,
            }
        )

        return service_request

