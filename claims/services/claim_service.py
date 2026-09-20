import os
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction
from django.core.files.base import File
from claims.models import Claim, ClaimStatus, ClaimDocument, ClaimEvent, ClaimEventType
from customers.models import CustomerProfile
from policies.models import Policy, PolicyStatus
from staff.models import StaffProfile
from audit.models import AuditAction
from audit.services.audit_service import AuditService
from core.services import ServiceValidationError, DataNormalizer, NotificationService


class ClaimService:
    """
    Encapsulates the complete vehicle insurance claims lifecycle:
    1. Filing claims against active authorized policies only.
    2. Shared pending queue enforcement (handler_id = None).
    3. Handler self-assignment moving claims to IN_REVIEW.
    4. Human claims adjudication: Approval (with settlement) and Rejection (with reason).
    5. Academic/demo simulated claim settlement payout disbursement.
    6. Complete event audit trail (ClaimEvent and AuditService).
    """

    @classmethod
    @transaction.atomic
    def file_claim(
        cls,
        customer: CustomerProfile,
        policy: Policy,
        incident_date: datetime,
        incident_location: str,
        incident_description: str,
        estimated_loss_amount: Decimal,
    ) -> Claim:
        """
        Validates and registers a new claim into the unassigned shared queue.
        """
        # Rule: Customer ownership check
        if policy.customer != customer:
            raise ServiceValidationError("Unauthorized: You may only file a claim against your own policies.")

        # Rule: Vehicle ownership check
        if hasattr(policy, 'vehicle') and policy.vehicle.customer != customer:
            raise ServiceValidationError("Unauthorized: Vehicle does not belong to the policy customer.")

        # Rule: Policy must be ACTIVE
        if policy.status != PolicyStatus.ACTIVE:
            raise ServiceValidationError(
                f"Cannot file a claim against a policy with status '{policy.status}'. Policy must be ACTIVE."
            )

        # Rule: Incident date bounds validation
        now = timezone.now()
        if incident_date > now:
            raise ServiceValidationError("Incident date cannot be in the future.")

        inc_date = incident_date.date()
        if inc_date < policy.start_date or inc_date > policy.end_date:
            raise ServiceValidationError(
                f"Incident date ({inc_date}) falls outside policy active term ({policy.start_date} to {policy.end_date})."
            )

        if estimated_loss_amount <= Decimal('0'):
            raise ServiceValidationError("Estimated loss amount must be greater than zero.")

        # Rule: Prevent duplicate claim submissions for the same policy on the same incident date
        existing_claim = Claim.objects.filter(
            policy=policy,
            incident_date__date=inc_date,
        ).exclude(status=ClaimStatus.REJECTED).first()
        if existing_claim:
            raise ServiceValidationError(
                f"A claim ({existing_claim.claim_number}) has already been submitted for this policy on {inc_date}."
            )

        loc = DataNormalizer.normalize_text(incident_location)
        desc = DataNormalizer.normalize_text(incident_description)
        if not loc or not desc:
            raise ServiceValidationError("Incident location and description are mandatory.")

        year = incident_date.year
        claim_num = f"CLM-{year}-{uuid.uuid4().hex[:8].upper()}"

        claim = Claim.objects.create(
            claim_number=claim_num,
            policy=policy,
            customer=customer,
            handler=None,  # Customer can NEVER assign the handler
            incident_date=incident_date,
            incident_location=loc,
            incident_description=desc,
            estimated_loss_amount=estimated_loss_amount,
            status=ClaimStatus.PENDING,
        )

        # Create audit event
        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_CREATED,
            actor=customer.user,
            actor_role='CUSTOMER',
            notes=f"Claim filed for estimated loss ₹{estimated_loss_amount:.2f}",
        )

        AuditService.log(
            action=AuditAction.CLAIM_CREATED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=customer.user,
            details={
                'claim_number': claim.claim_number,
                'policy_number': policy.policy_number,
                'estimated_loss': float(estimated_loss_amount),
            }
        )

        NotificationService.notify(
            recipient=customer.user,
            title="Claim Registered",
            message=f"Claim {claim.claim_number} for policy {policy.policy_number} has been registered and placed in the shared adjudication queue.",
            notification_type='CLAIM_STATUS',
            action_url=f"/claims/{claim.id}/",
        )

        return claim


    @classmethod
    @transaction.atomic
    def self_assign_claim(
        cls,
        claim: Claim,
        handler: StaffProfile,
    ) -> Claim:
        """
        Claims handler self-assigns a claim from the shared queue,
        moving status from PENDING to IN_REVIEW.
        """
        if claim.status != ClaimStatus.PENDING:
            raise ServiceValidationError(
                f"Only PENDING claims can be self-assigned. Current status is '{claim.status}'."
            )

        if not (handler.user.is_claims_handler or handler.user.is_administrator):
            raise ServiceValidationError("Only authorized Claims Handlers or Administrators may self-assign claims.")

        claim.handler = handler
        claim.status = ClaimStatus.IN_REVIEW
        claim.save(update_fields=['handler', 'status', 'updated_at'])

        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_ASSIGNED,
            actor=handler.user,
            actor_role=handler.user.role,
            notes=f"Self-assigned by {handler.staff_code} ({handler.user.email}) and moved to IN_REVIEW",
        )

        AuditService.log(
            action=AuditAction.CLAIM_ASSIGNED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=handler.user,
            details={
                'claim_number': claim.claim_number,
                'handler_code': handler.staff_code,
                'status': claim.status,
            }
        )

        return claim

    @classmethod
    @transaction.atomic
    def review_claim(
        cls,
        claim: Claim,
        handler: StaffProfile,
        notes: str = "",
    ) -> Claim:
        """
        Explicitly logs the start of active claim review/investigation by an assigned handler or administrator.
        """
        if claim.status != ClaimStatus.IN_REVIEW:
            raise ServiceValidationError(f"Only claims in IN_REVIEW status can be reviewed. Current status: '{claim.status}'.")

        if not handler.user.is_administrator and claim.handler != handler:
            raise ServiceValidationError("Unauthorized: You may only review claims assigned to you.")

        review_notes = notes or f"Active investigation and damage verification begun by {handler.staff_code}."
        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_REVIEW_STARTED,
            actor=handler.user,
            actor_role=handler.user.role,
            notes=review_notes,
        )

        AuditService.log(
            action=AuditAction.CLAIM_REVIEW_STARTED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=handler.user,
            details={
                'claim_number': claim.claim_number,
                'handler_code': handler.staff_code,
            }
        )

        return claim

    @classmethod
    @transaction.atomic
    def approve_claim(
        cls,
        claim: Claim,
        handler: StaffProfile,
        settlement_amount: Decimal,
        notes: str = "",
    ) -> Claim:
        """
        Human claims handler approves a claim and authorizes a settlement amount.
        Enforces handler approval threshold limits.
        """
        if claim.status != ClaimStatus.IN_REVIEW:
            raise ServiceValidationError(f"Only claims in IN_REVIEW status can be approved. Current status: '{claim.status}'.")

        # Handler authorization check: must be assigned handler or admin
        if not handler.user.is_administrator and claim.handler != handler:
            raise ServiceValidationError("Unauthorized: You may only action claims assigned to you.")

        if settlement_amount <= Decimal('0'):
            raise ServiceValidationError("Settlement amount must be greater than zero.")

        # Enforce vehicle IDV upper bound
        vehicle_idv = claim.policy.vehicle.vehicle_value
        if settlement_amount > vehicle_idv:
            raise ServiceValidationError(f"Settlement amount (₹{settlement_amount}) cannot exceed policy IDV (₹{vehicle_idv}).")

        # Enforce handler maximum approval authority limit
        if not handler.user.is_administrator and settlement_amount > handler.max_claim_approval_limit:
            raise ServiceValidationError(
                f"Settlement amount (₹{settlement_amount}) exceeds your maximum approval limit (₹{handler.max_claim_approval_limit})."
            )

        claim.settlement_amount = settlement_amount
        claim.status = ClaimStatus.APPROVED
        claim.save(update_fields=['settlement_amount', 'status', 'updated_at'])

        event_notes = (
            f"Settlement payout ₹{settlement_amount:.2f} authorized. {notes}".strip()
            if notes
            else f"Claim approved by human handler. Settlement payout authorized: ₹{settlement_amount:.2f}"
        )
        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_APPROVED,
            actor=handler.user,
            actor_role=handler.user.role,
            notes=event_notes,
        )

        AuditService.log(
            action=AuditAction.CLAIM_APPROVED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=handler.user,
            details={
                'claim_number': claim.claim_number,
                'handler_code': handler.staff_code,
                'settlement_amount': float(settlement_amount),
            }
        )

        # Notify customer of claim approval
        NotificationService.notify_claim_status_change(
            recipient=claim.policy.customer.user,
            claim_number=claim.claim_number,
            new_status='APPROVED',
        )

        return claim

    @classmethod
    @transaction.atomic
    def reject_claim(
        cls,
        claim: Claim,
        handler: StaffProfile,
        rejection_reason: str,
        notes: str = "",
    ) -> Claim:
        """
        Human claims handler rejects a claim with a mandatory documented reason.
        """
        if claim.status != ClaimStatus.IN_REVIEW:
            raise ServiceValidationError(f"Only claims in IN_REVIEW status can be rejected. Current status: '{claim.status}'.")

        if not handler.user.is_administrator and claim.handler != handler:
            raise ServiceValidationError("Unauthorized: You may only action claims assigned to you.")

        reason = DataNormalizer.normalize_text(rejection_reason)
        if not reason:
            raise ServiceValidationError("A detailed rejection reason is mandatory when denying a claim.")

        claim.rejection_reason = reason
        claim.status = ClaimStatus.REJECTED
        claim.save(update_fields=['rejection_reason', 'status', 'updated_at'])

        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_REJECTED,
            actor=handler.user,
            actor_role=handler.user.role,
            notes=notes or f"Claim rejected by human handler. Reason: {reason}",
        )

        AuditService.log(
            action=AuditAction.CLAIM_REJECTED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=handler.user,
            details={
                'claim_number': claim.claim_number,
                'handler_code': handler.staff_code,
                'reason': reason,
            }
        )

        # Notify customer of claim rejection
        NotificationService.notify_claim_status_change(
            recipient=claim.policy.customer.user,
            claim_number=claim.claim_number,
            new_status='REJECTED',
        )

        return claim

    @classmethod
    @transaction.atomic
    def settle_claim(
        cls,
        claim: Claim,
        actor: Any,
        settlement_amount: Optional[Decimal] = None,
        notes: str = "",
    ) -> Claim:
        """
        Finalizes simulated payout disbursement for an approved claim.
        Ensures no duplicate settlements and enforces server-side amount constraints.
        """
        if claim.status == ClaimStatus.SETTLED:
            raise ServiceValidationError("Claim has already been settled. Duplicate settlement is prohibited.")
        if claim.status != ClaimStatus.APPROVED:
            raise ServiceValidationError(f"Only APPROVED claims can be settled. Current status is '{claim.status}'.")

        # Actor role authorization
        user = actor.user if hasattr(actor, 'user') else actor
        if not (getattr(user, 'is_claims_handler', False) or getattr(user, 'is_administrator', False) or getattr(user, 'is_superuser', False)):
            raise ServiceValidationError("Only authorized Claims Handlers or Administrators may execute claim settlements.")

        # Handler authorization check
        handler_profile = getattr(user, 'staff_profile', None)
        if not getattr(user, 'is_administrator', False) and claim.handler and handler_profile and claim.handler != handler_profile:
            raise ServiceValidationError("Unauthorized: You may only settle claims assigned to you.")

        # Validate settlement amount
        if settlement_amount is not None:
            if settlement_amount <= Decimal('0'):
                raise ServiceValidationError("Settlement payout amount must be greater than zero.")
            if claim.settlement_amount and settlement_amount > claim.settlement_amount:
                raise ServiceValidationError(
                    f"Settlement amount (₹{settlement_amount}) cannot exceed authorized approval amount (₹{claim.settlement_amount})."
                )
            claim.settlement_amount = settlement_amount

        if not claim.settlement_amount or claim.settlement_amount <= Decimal('0'):
            raise ServiceValidationError("A valid authorized settlement amount is required to disburse payment.")

        simulated_ref = f"SIM-SETTLE-{uuid.uuid4().hex[:8].upper()}"
        claim.status = ClaimStatus.SETTLED
        claim.settlement_reference = simulated_ref
        claim.settled_at = timezone.now()
        claim.save(update_fields=['status', 'settlement_amount', 'settlement_reference', 'settled_at', 'updated_at'])

        payout_notes = (
            f"Simulated settlement of ₹{claim.settlement_amount:.2f} disbursed. "
            f"Reference: {simulated_ref}. (Academic/Demo Simulated Financial Transaction). {notes}"
        ).strip()

        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_SETTLED,
            actor=user,
            actor_role=getattr(user, 'role', 'STAFF'),
            notes=payout_notes,
        )

        AuditService.log(
            action=AuditAction.CLAIM_SETTLED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=user,
            details={
                'claim_number': claim.claim_number,
                'settlement_amount': float(claim.settlement_amount),
                'reference': simulated_ref,
                'is_simulated': True,
            }
        )

        NotificationService.notify(
            recipient=claim.policy.customer.user,
            title="Claim Settled — Payment Disbursed",
            message=f"Your claim {claim.claim_number} has been settled. Payout amount of ₹{claim.settlement_amount:,.2f} disbursed (Ref: {simulated_ref}).",
            notification_type='CLAIM_STATUS',
            action_url=f"/claims/{claim.id}/",
        )

        return claim


    @classmethod
    @transaction.atomic
    def add_claim_document(
        cls,
        claim: Claim,
        uploaded_by: Any,
        document_type: str,
        title: str,
        file_obj: File,
    ) -> ClaimDocument:
        """
        Attaches damage photos, police reports, or garage estimates to a claim.
        Enforces ownership and role-based permissions.
        """
        user = uploaded_by if hasattr(uploaded_by, 'role') else getattr(uploaded_by, 'user', None)
        if user and getattr(user, 'is_customer', False):
            if claim.customer.user != user:
                raise ServiceValidationError("Unauthorized: You cannot attach documents to another customer's claim.")
        elif user and not (getattr(user, 'is_claims_handler', False) or getattr(user, 'is_administrator', False) or getattr(user, 'is_underwriter', False) or getattr(user, 'is_staff_member', False) or getattr(user, 'is_superuser', False)):
            raise ServiceValidationError("Unauthorized: Insufficient privileges to attach claim documents.")

        # Document Security & File Validation (Phase N)
        if not file_obj:
            raise ServiceValidationError("A document file is required for attachment.")

        file_name = getattr(file_obj, 'name', '') or ''
        # Sanitize filename against directory traversal
        sanitized_filename = os.path.basename(file_name)
        if '..' in file_name or '/' in file_name or '\\' in file_name:
            if not sanitized_filename:
                raise ServiceValidationError("Invalid file name: directory traversal sequence detected.")

        # Check extension
        ext = os.path.splitext(sanitized_filename)[1].lower()
        ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}
        if ext and ext not in ALLOWED_EXTENSIONS:
            raise ServiceValidationError(
                f"Unsupported document format '{ext}'. Only PDF and image formats (JPG, PNG) are permitted."
            )

        # Check file size (Max 10 MB)
        MAX_UPLOAD_SIZE = 10 * 1024 * 1024
        file_size = getattr(file_obj, 'size', 0)
        if file_size and file_size > MAX_UPLOAD_SIZE:
            raise ServiceValidationError("File size exceeds maximum permitted limit of 10 MB.")

        doc = ClaimDocument.objects.create(
            claim=claim,
            document_type=document_type,
            title=DataNormalizer.normalize_text(title) or "Claim Attachment",
            file=file_obj,
        )


        ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.DOCUMENT_ADDED,
            actor=user,
            actor_role=getattr(user, 'role', 'USER'),
            notes=f"Document '{doc.title}' ({doc.get_document_type_display()}) uploaded.",
        )

        AuditService.log(
            action=AuditAction.CLAIM_DOCUMENT_ADDED,
            target_entity='ClaimDocument',
            target_id=str(doc.pk),
            actor=user,
            details={
                'claim_number': claim.claim_number,
                'document_title': doc.title,
                'document_type': doc.document_type,
            }
        )

        return doc

    @classmethod
    @transaction.atomic
    def add_claim_note(
        cls,
        claim: Claim,
        actor: Any,
        note: str,
    ) -> ClaimEvent:
        """
        Appends an auditable investigation note to the claim timeline.
        """
        user = actor.user if hasattr(actor, 'user') else actor
        clean_note = DataNormalizer.normalize_text(note)
        if not clean_note:
            raise ServiceValidationError("Note content cannot be empty.")

        event = ClaimEvent.objects.create(
            claim=claim,
            event_type=ClaimEventType.CLAIM_NOTE_ADDED,
            actor=user,
            actor_role=getattr(user, 'role', 'STAFF'),
            notes=clean_note,
        )

        AuditService.log(
            action=AuditAction.CLAIM_NOTE_ADDED,
            target_entity='Claim',
            target_id=str(claim.pk),
            actor=user,
            details={
                'claim_number': claim.claim_number,
                'note_preview': clean_note[:120],
            }
        )

        return event

