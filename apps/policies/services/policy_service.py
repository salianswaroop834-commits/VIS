import uuid
from decimal import Decimal
from datetime import date, timedelta
from typing import Optional, List
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from apps.policies.models import Policy, PolicyStatus
from apps.quotations.models import QuotationDraft
from apps.staff.models import StaffProfile
from apps.customers.models import CustomerProfile
from apps.accounts.models import User
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService
from core.services import ServiceValidationError, DataNormalizer, NotificationService



def add_years_to_date(start: date, years: int) -> date:
    """Calculates calendar expiration date taking into account leap year boundaries."""
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        # Leap year handling: Feb 29 becomes Feb 28 in non-leap year
        return start.replace(year=start.year + years, day=28)


class PolicyService:
    """
    Encapsulates core vehicle insurance policy lifecycle operations:
    - Policy issuance from accepted quotations
    - Automatic duration and end-date arithmetic
    - Strict financial locking (immutable premiums post-issuance)
    - Non-mutating policy renewal with historical lineage tracking
    - Operational searching by policy or vehicle registration number
    """

    @classmethod
    def calculate_end_date(cls, start_date: date, duration_years: int) -> date:
        if duration_years not in (1, 2, 3):
            raise ServiceValidationError("Duration must be 1, 2, or 3 years.")
        return add_years_to_date(start_date, duration_years)

    @classmethod
    @transaction.atomic
    def issue_policy_from_quotation(
        cls,
        quotation: QuotationDraft,
        underwriter: Optional[StaffProfile] = None,
        start_date: Optional[date] = None,
    ) -> Policy:
        """
        Converts an approved quotation into an active vehicle insurance policy.
        Locks premium, duration, and sets status to ACTIVE.
        """
        if quotation.status == QuotationDraft.QuotationStatus.CONVERTED:
            raise ServiceValidationError("This quotation has already been converted into an active policy.")

        if quotation.valid_until < timezone.now():
            quotation.status = QuotationDraft.QuotationStatus.EXPIRED
            quotation.save(update_fields=['status'])
            raise ServiceValidationError("This quotation has expired. Please calculate a new quote.")

        if not quotation.customer:
            raise ServiceValidationError("Quotation must be linked to an authenticated customer profile before policy issuance.")

        if not quotation.vehicle:
            raise ServiceValidationError("Quotation must be linked to a registered vehicle before policy issuance.")

        eff_start = start_date or timezone.now().date()
        eff_end = cls.calculate_end_date(eff_start, quotation.duration_years)

        year = eff_start.year
        policy_num = f"POL-{year}-{uuid.uuid4().hex[:8].upper()}"

        policy = Policy.objects.create(
            policy_number=policy_num,
            customer=quotation.customer,
            vehicle=quotation.vehicle,
            coverage_plan=quotation.coverage_plan,
            underwriter=underwriter,
            premium_amount=quotation.calculated_premium,
            deductible_amount=quotation.deductible_amount,
            duration_years=quotation.duration_years,
            start_date=eff_start,
            end_date=eff_end,
            status=PolicyStatus.ACTIVE,
        )

        # Mark quotation converted
        quotation.status = QuotationDraft.QuotationStatus.CONVERTED
        quotation.save(update_fields=['status'])

        AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(policy.pk),
            actor=underwriter.user if underwriter else quotation.customer.user,
            details={
                'policy_number': policy.policy_number,
                'customer_code': quotation.customer.customer_code,
                'vehicle_plate': quotation.vehicle.registration_number,
                'premium_amount': float(policy.premium_amount),
                'duration_years': policy.duration_years,
            }
        )

        NotificationService.notify(
            recipient=policy.customer.user,
            title="Insurance Policy Issued",
            message=f"Your policy {policy.policy_number} is active for {policy.vehicle.registration_number}. Term: {policy.start_date} to {policy.end_date}.",
            notification_type='GENERAL',
            action_url=f"/policies/{policy.id}/",
        )

        return policy


    @classmethod
    @transaction.atomic
    def renew_policy(
        cls,
        existing_policy: Policy,
        duration_years: int = 1,
        new_premium: Optional[Decimal] = None,
        underwriter: Optional[StaffProfile] = None,
    ) -> Policy:
        """
        Renews an existing policy by issuing a NEW policy record and linking
        back to the previous policy ID, preserving historical immutable records.
        """
        if existing_policy.status not in (PolicyStatus.ACTIVE, PolicyStatus.EXPIRED):
            raise ServiceValidationError(
                f"Cannot renew policy with status '{existing_policy.status}'. Only Active or Expired policies may be renewed."
            )

        # Duplicate renewal prevention
        if existing_policy.renewal_history.filter(status__in=[PolicyStatus.ACTIVE, PolicyStatus.RENEWED]).exists():
            raise ServiceValidationError("This policy has already been renewed.")

        today = timezone.now().date()
        # New policy starts the day after current policy ends, or today if already lapsed
        new_start = existing_policy.end_date + timedelta(days=1) if existing_policy.end_date >= today else today
        new_end = cls.calculate_end_date(new_start, duration_years)

        # Calculate renewal premium if not explicitly supplied by underwriter
        if new_premium is None:
            # 5% No-Claim Bonus (NCB) discount simulation on renewal
            plan_rate = existing_policy.coverage_plan.base_rate_percentage
            base_prem = (existing_policy.vehicle.vehicle_value * plan_rate) / Decimal('100.00')
            renewal_prem = round(base_prem * Decimal(duration_years) * Decimal('0.95'), 2)
        else:
            renewal_prem = new_premium

        year = new_start.year
        new_policy_num = f"POL-{year}-{uuid.uuid4().hex[:8].upper()}"

        new_policy = Policy.objects.create(
            policy_number=new_policy_num,
            customer=existing_policy.customer,
            vehicle=existing_policy.vehicle,
            coverage_plan=existing_policy.coverage_plan,
            underwriter=underwriter or existing_policy.underwriter,
            premium_amount=renewal_prem,
            deductible_amount=existing_policy.deductible_amount,
            duration_years=duration_years,
            start_date=new_start,
            end_date=new_end,
            status=PolicyStatus.ACTIVE,
            previous_policy=existing_policy,
        )

        # Update historical policy status to RENEWED
        existing_policy.status = PolicyStatus.RENEWED
        existing_policy.save(update_fields=['status'])

        AuditService.log(
            action=AuditAction.POLICY_RENEWED,
            target_entity='Policy',
            target_id=str(new_policy.pk),
            actor=underwriter.user if underwriter else existing_policy.customer.user,
            details={
                'new_policy_number': new_policy.policy_number,
                'previous_policy_number': existing_policy.policy_number,
                'renewal_premium': float(new_policy.premium_amount),
                'duration_years': new_policy.duration_years,
            }
        )

        NotificationService.notify(
            recipient=new_policy.customer.user,
            title="Insurance Policy Renewed",
            message=f"Policy renewed under new Policy Number {new_policy.policy_number}. Continuous coverage active until {new_policy.end_date}.",
            notification_type='RENEWAL_REMINDER',
            action_url=f"/policies/{new_policy.id}/",
        )

        return new_policy


    @classmethod
    def generate_policy_certificate(
        cls,
        policy: Policy,
        actor: Optional[any] = None,
    ) -> bytes:
        """
        Generates binary PDF certificate and logs compliance audit event.
        """
        from apps.policies.services.certificate_service import PolicyCertificateService
        pdf_bytes = PolicyCertificateService.generate_certificate_pdf(policy)

        effective_actor = actor or policy.customer.user
        AuditService.log(
            action=AuditAction.POLICY_CERTIFICATE_GENERATED,
            target_entity='Policy',
            target_id=str(policy.pk),
            actor=effective_actor,
            details={
                'policy_number': policy.policy_number,
                'customer_code': policy.customer.customer_code,
                'status': policy.status,
                'format': 'PDF',
            }
        )

        return pdf_bytes

    @classmethod
    @transaction.atomic
    def cancel_policy(
        cls,
        policy: Policy,
        actor: any,
        reason: str = "",
    ) -> Policy:
        """
        Formally terminates an ACTIVE policy contract, preserving historical data.
        Transitions state to CANCELLED and calculates simulated pro-rata refund.
        """
        if policy.status != PolicyStatus.ACTIVE:
            raise ServiceValidationError(
                f"Cannot cancel policy with status '{policy.status}'. Only ACTIVE policies may be cancelled."
            )

        # Ownership / authorization check
        if getattr(actor, 'is_customer', False):
            if policy.customer.user != actor:
                raise ServiceValidationError("Unauthorized: You may only cancel your own policy.")
        elif not (getattr(actor, 'is_underwriter', False) or getattr(actor, 'is_administrator', False)):
            raise ServiceValidationError("Unauthorized: Insufficient privileges to cancel policy.")

        # Pro-rata simulated refund calculation
        today = timezone.now().date()
        total_term_days = (policy.end_date - policy.start_date).days
        remaining_days = max(0, (policy.end_date - today).days)
        if total_term_days > 0 and remaining_days > 0:
            simulated_refund = round(
                Decimal(str(policy.premium_amount)) * (Decimal(remaining_days) / Decimal(total_term_days)),
                2
            )
        else:
            simulated_refund = Decimal('0.00')

        policy.status = PolicyStatus.CANCELLED
        policy.save(update_fields=['status'])

        clean_reason = DataNormalizer.normalize_text(reason) or "Customer requested policy cancellation"

        AuditService.log(
            action=AuditAction.POLICY_CANCELLED,
            target_entity='Policy',
            target_id=str(policy.pk),
            actor=actor,
            details={
                'policy_number': policy.policy_number,
                'previous_status': 'ACTIVE',
                'cancellation_reason': clean_reason,
                'simulated_refund_inr': float(simulated_refund),
                'is_simulated': True,
            }
        )

        NotificationService.notify(
            recipient=policy.customer.user,
            title="Insurance Policy Cancelled",
            message=f"Policy {policy.policy_number} has been cancelled. Calculated simulated refund: ₹{simulated_refund:,.2f}.",
            notification_type='GENERAL',
            action_url=f"/policies/{policy.id}/",
        )

        return policy


    @classmethod
    def request_policy_endorsement(
        cls,
        policy: Policy,
        customer: CustomerProfile,
        endorsement_type: str,
        requested_changes: dict,
        title: str,
        description: str,
        actor: any,
    ):
        """
        Submits a mid-term policy endorsement change request via ServiceRequest.
        Strictly prevents direct mutation of immutable financial and identity fields.
        """
        from apps.service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
        from apps.vehicles.models import UsageType

        if policy.status != PolicyStatus.ACTIVE:
            raise ServiceValidationError("Endorsements can only be requested on ACTIVE policies.")

        if policy.customer != customer:
            raise ServiceValidationError("You may only request endorsements on your own policies.")

        # Financial & identity immutability guard
        IMMUTABLE_FIELDS = {
            'premium_amount', 'deductible_amount', 'policy_number',
            'start_date', 'end_date', 'status', 'vehicle_value',
            'idv', 'coverage_plan', 'customer', 'vehicle'
        }
        for field in requested_changes.keys():
            if field.lower() in IMMUTABLE_FIELDS:
                raise ServiceValidationError(
                    f"Direct mutation of policy financial or contract identity field '{field}' is strictly prohibited. "
                    "Coverage and financial modifications require a formal underwriting recalculation."
                )

        if endorsement_type not in (ServiceRequestType.ADDRESS_UPDATE, ServiceRequestType.VEHICLE_UPDATE, ServiceRequestType.OTHER):
            raise ServiceValidationError(f"Unsupported endorsement type: '{endorsement_type}'.")

        # Specific payload validation
        if endorsement_type == ServiceRequestType.ADDRESS_UPDATE:
            valid_keys = {'address', 'address_line', 'city', 'state', 'postal_code'}
            if not any(k in requested_changes for k in valid_keys):
                raise ServiceValidationError("Address endorsement must contain at least one of: address, address_line, city, state, postal_code.")

        if endorsement_type == ServiceRequestType.VEHICLE_UPDATE:
            if 'usage_type' in requested_changes and requested_changes['usage_type'] not in UsageType.values:
                raise ServiceValidationError(f"Invalid vehicle usage classification: '{requested_changes['usage_type']}'.")

        year = timezone.now().year
        req_num = f"SRV-{year}-{uuid.uuid4().hex[:8].upper()}"
        clean_title = DataNormalizer.normalize_text(title) or f"Policy Endorsement Request: {policy.policy_number}"
        clean_desc = DataNormalizer.normalize_text(description)

        srv = ServiceRequest.objects.create(
            request_number=req_num,
            customer=customer,
            policy=policy,
            request_type=endorsement_type,
            title=clean_title,
            description=clean_desc,
            change_payload=requested_changes,
            status=ServiceRequestStatus.SUBMITTED,
        )

        AuditService.log(
            action=AuditAction.POLICY_ENDORSEMENT_REQUESTED,
            target_entity='Policy',
            target_id=str(policy.pk),
            actor=actor,
            details={
                'policy_number': policy.policy_number,
                'request_number': srv.request_number,
                'endorsement_type': endorsement_type,
                'requested_changes': requested_changes,
            }
        )

        return srv

    @classmethod
    @transaction.atomic
    def adjudicate_endorsement(
        cls,
        service_request,
        reviewer: any,
        decision: str,
        notes: str = "",
    ):
        """
        Adjudicates a pending policy endorsement request (APPROVE or REJECT).
        Enforces RBAC: Underwriter or Administrator only.
        Customers cannot approve their own endorsement.
        Applies approved non-destructive changes and logs compliance audit.
        """
        from apps.service_requests.models import ServiceRequestStatus, ServiceRequestType

        if decision not in ('APPROVE', 'REJECT'):
            raise ServiceValidationError("Decision must be either 'APPROVE' or 'REJECT'.")

        # RBAC Check
        is_uw = getattr(reviewer, 'is_underwriter', False)
        is_admin = getattr(reviewer, 'is_administrator', False)
        if not (is_uw or is_admin):
            raise ServiceValidationError("Unauthorized: Only Underwriters or Administrators can adjudicate policy endorsements.")

        # Self-approval guard
        if service_request.customer.user == reviewer:
            raise ServiceValidationError("Unauthorized: Customers cannot approve their own endorsement requests.")

        if service_request.status in (ServiceRequestStatus.RESOLVED, ServiceRequestStatus.REJECTED):
            raise ServiceValidationError(f"This endorsement request has already been finalized ({service_request.status}).")

        policy = service_request.policy
        if not policy:
            raise ServiceValidationError("No policy linked to this service request.")

        if policy.status != PolicyStatus.ACTIVE:
            raise ServiceValidationError("Cannot adjudicate endorsement on an inactive or terminated policy.")

        clean_notes = DataNormalizer.normalize_text(notes)

        if decision == 'APPROVE':
            changes = service_request.change_payload or {}

            # Double-check financial immutability
            IMMUTABLE_FIELDS = {
                'premium_amount', 'deductible_amount', 'policy_number',
                'start_date', 'end_date', 'status', 'vehicle_value',
                'idv', 'coverage_plan', 'customer', 'vehicle'
            }
            if any(k.lower() in IMMUTABLE_FIELDS for k in changes.keys()):
                raise ServiceValidationError("Direct mutation of policy financial or identity fields is prohibited.")

            # Apply permitted changes
            if service_request.request_type == ServiceRequestType.ADDRESS_UPDATE:
                cust = policy.customer
                if 'address_line' in changes:
                    cust.address_line = changes['address_line']
                elif 'address' in changes:
                    cust.address_line = changes['address']
                if 'city' in changes:
                    cust.city = changes['city']
                if 'state' in changes:
                    cust.state = changes['state']
                if 'postal_code' in changes:
                    cust.postal_code = changes['postal_code']
                cust.save()

            elif service_request.request_type == ServiceRequestType.VEHICLE_UPDATE:
                veh = policy.vehicle
                if 'usage_type' in changes:
                    veh.usage_type = changes['usage_type']
                if 'color' in changes:
                    veh.color = changes['color']
                veh.save()

            service_request.status = ServiceRequestStatus.RESOLVED
            service_request.assigned_staff = reviewer
            service_request.resolved_at = timezone.now()
            service_request.resolution_notes = clean_notes or "Endorsement approved and changes applied to policy record."
            service_request.save()

            AuditService.log(
                action=AuditAction.POLICY_ENDORSEMENT_APPROVED,
                target_entity='Policy',
                target_id=str(policy.pk),
                actor=reviewer,
                details={
                    'policy_number': policy.policy_number,
                    'request_number': service_request.request_number,
                    'applied_changes': changes,
                    'reviewer': reviewer.email,
                    'notes': clean_notes,
                }
            )

        else:  # REJECT
            service_request.status = ServiceRequestStatus.REJECTED
            service_request.assigned_staff = reviewer
            service_request.resolved_at = timezone.now()
            service_request.resolution_notes = clean_notes or "Endorsement request rejected by underwriting."
            service_request.save()

            AuditService.log(
                action=AuditAction.POLICY_ENDORSEMENT_REJECTED,
                target_entity='Policy',
                target_id=str(policy.pk),
                actor=reviewer,
                details={
                    'policy_number': policy.policy_number,
                    'request_number': service_request.request_number,
                    'rejection_reason': clean_notes,
                    'reviewer': reviewer.email,
                }
            )

        return service_request

    @classmethod
    def approve_endorsement_request(cls, service_request, underwriter_user, notes=""):
        return cls.adjudicate_endorsement(service_request, reviewer=underwriter_user, decision='APPROVE', notes=notes)

    @classmethod
    def reject_endorsement_request(cls, service_request, underwriter_user, notes=""):
        return cls.adjudicate_endorsement(service_request, reviewer=underwriter_user, decision='REJECT', notes=notes)

    @classmethod
    def search_policies(
        cls,
        query: str,
        underwriter: Optional[StaffProfile] = None,
    ) -> List[Policy]:
        """
        Searches policies by policy number or vehicle registration plate.
        Optionally scopes to an underwriter's portfolio.
        """
        cleaned_query = query.strip() if query else ""
        if not cleaned_query:
            qs = Policy.objects.all()
        else:
            normalized_plate = DataNormalizer.normalize_registration_number(cleaned_query)
            qs = Policy.objects.filter(
                Q(policy_number__icontains=cleaned_query) |
                Q(vehicle__registration_number__icontains=normalized_plate or cleaned_query)
            )

        if underwriter and not underwriter.user.is_administrator:
            qs = qs.filter(underwriter=underwriter)

        return qs.select_related('customer__user', 'vehicle', 'coverage_plan', 'underwriter')
