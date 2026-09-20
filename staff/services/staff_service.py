from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import transaction
from staff.models import StaffProfile, UnderwriterProfile, ClaimsHandlerProfile
from accounts.models import User, UserRole
from policies.models import Policy, PolicyStatus
from claims.models import Claim, ClaimStatus, ClaimEvent, ClaimEventType
from audit.models import AuditAction
from audit.services.audit_service import AuditService
from core.services import ServiceValidationError, DataNormalizer


class StaffService:
    """
    Manages operational staff lifecycles and governance rules:
    - Creation, profile maintenance, and limits
    - Underwriter and claims-handler workload reassignment
    - Protected staff deactivation preventing orphaned policies or claims
    """

    @classmethod
    @transaction.atomic
    def create_staff_profile(
        cls,
        user: User,
        staff_code: str,
        department: str = 'Underwriting',
        max_claim_approval_limit: Decimal = Decimal('50000.00'),
        assigned_region: str = 'National',
        actor: Optional[User] = None,
    ) -> StaffProfile:
        """
        Creates and registers a new staff profile along with role-specialized child profile.
        """
        code = DataNormalizer.normalize_text(staff_code).upper()
        if not code:
            raise ServiceValidationError("Staff code is mandatory.")

        if StaffProfile.objects.filter(staff_code=code).exists():
            raise ServiceValidationError(f"Staff code '{code}' is already registered.")

        profile = StaffProfile.objects.create(
            user=user,
            staff_code=code,
            department=department,
            max_claim_approval_limit=max_claim_approval_limit,
            assigned_region=assigned_region,
        )

        # Automatically provision department-specialized domain profile
        dept_upper = (department or '').upper()
        if 'CLAIM' in dept_upper:
            if not hasattr(profile, 'claims_handler_profile'):
                ClaimsHandlerProfile.objects.create(
                    staff_profile=profile,
                    max_claim_approval_limit=max_claim_approval_limit,
                    specialization_team=department or 'General Claims',
                )
        else:
            if not hasattr(profile, 'underwriter_profile'):
                UnderwriterProfile.objects.create(
                    staff_profile=profile,
                    specialization='Commercial Fleets' if 'commercial' in department.lower() else 'General Motor',
                )

        AuditService.log(
            action=AuditAction.STAFF_CREATED,
            target_entity='StaffProfile',
            target_id=str(profile.pk),
            actor=actor or user,
            details={
                'staff_code': code,
                'email': user.email,
                'role': user.role,
                'department': department,
                'max_claim_approval_limit': float(max_claim_approval_limit),
            }
        )
        return profile

    @classmethod
    @transaction.atomic
    def reassign_underwriter_workload(
        cls,
        from_staff: StaffProfile,
        to_staff: StaffProfile,
        actor: Optional[User] = None,
    ) -> int:
        """
        Reassigns all active policies underwritten by from_staff to to_staff.
        Prevents orphaned policies during staff transfer or departure.
        """
        if from_staff == to_staff:
            raise ServiceValidationError("Cannot reassign workload to the same underwriter.")

        if not to_staff.is_active or not to_staff.user.is_active:
            raise ServiceValidationError("Target underwriter must be active.")

        if not (to_staff.user.is_underwriter or to_staff.user.is_administrator):
            raise ServiceValidationError("Target staff member must have Underwriter or Administrator permissions.")

        active_policies = list(Policy.objects.filter(underwriter=from_staff, status=PolicyStatus.ACTIVE))
        count = len(active_policies)

        for p in active_policies:
            p.underwriter = to_staff
            p.save(update_fields=['underwriter', 'updated_at'])

            AuditService.log(
                action=AuditAction.POLICY_REASSIGNED,
                target_entity='Policy',
                target_id=str(p.pk),
                actor=actor,
                details={
                    'policy_number': p.policy_number,
                    'from_underwriter': from_staff.staff_code,
                    'to_underwriter': to_staff.staff_code,
                }
            )

        AuditService.log(
            action=AuditAction.STAFF_REASSIGNED,
            target_entity='StaffProfile',
            target_id=str(from_staff.pk),
            actor=actor,
            details={
                'workload_type': 'POLICIES',
                'policies_reassigned': count,
                'from_underwriter': from_staff.staff_code,
                'to_underwriter': to_staff.staff_code,
            }
        )
        return count

    @classmethod
    @transaction.atomic
    def reassign_handler_workload(
        cls,
        from_staff: StaffProfile,
        to_staff: Optional[StaffProfile] = None,
        return_to_queue: bool = False,
        actor: Optional[User] = None,
    ) -> int:
        """
        Reassigns in-review claims from from_staff:
        - to another authorized claims handler, OR
        - returns them to the unassigned shared queue (PENDING, handler=None).
        """
        if not to_staff and not return_to_queue:
            raise ServiceValidationError("Must specify a successor claims handler or return claims to queue.")

        if to_staff:
            if from_staff == to_staff:
                raise ServiceValidationError("Cannot reassign workload to the same claims handler.")
            if not to_staff.is_active or not to_staff.user.is_active:
                raise ServiceValidationError("Target claims handler must be active.")
            if not (to_staff.user.is_claims_handler or to_staff.user.is_administrator):
                raise ServiceValidationError("Target staff must have Claims Handler or Administrator permissions.")

        in_review_claims = list(Claim.objects.filter(handler=from_staff, status=ClaimStatus.IN_REVIEW))
        count = len(in_review_claims)

        for c in in_review_claims:
            if return_to_queue:
                c.handler = None
                c.status = ClaimStatus.PENDING
                c.save(update_fields=['handler', 'status', 'updated_at'])

                ClaimEvent.objects.create(
                    claim=c,
                    event_type=ClaimEventType.CLAIM_ASSIGNED,
                    actor=actor if actor else from_staff.user,
                    actor_role=actor.role if actor else from_staff.user.role,
                    notes=f"Returned to shared queue due to departure/reassignment of {from_staff.staff_code}",
                )
            else:
                c.handler = to_staff
                c.save(update_fields=['handler', 'updated_at'])

                ClaimEvent.objects.create(
                    claim=c,
                    event_type=ClaimEventType.CLAIM_ASSIGNED,
                    actor=actor if actor else to_staff.user,
                    actor_role=actor.role if actor else to_staff.user.role,
                    notes=f"Workload reassigned from {from_staff.staff_code} to {to_staff.staff_code}",
                )

            AuditService.log(
                action=AuditAction.CLAIM_ASSIGNED,
                target_entity='Claim',
                target_id=str(c.pk),
                actor=actor,
                details={
                    'claim_number': c.claim_number,
                    'from_handler': from_staff.staff_code,
                    'to_handler': to_staff.staff_code if to_staff else 'UNASSIGNED_QUEUE',
                    'new_status': c.status,
                }
            )

        AuditService.log(
            action=AuditAction.STAFF_REASSIGNED,
            target_entity='StaffProfile',
            target_id=str(from_staff.pk),
            actor=actor,
            details={
                'workload_type': 'CLAIMS',
                'claims_reassigned': count,
                'from_handler': from_staff.staff_code,
                'target': to_staff.staff_code if to_staff else 'UNASSIGNED_QUEUE',
            }
        )
        return count

    @classmethod
    @transaction.atomic
    def deactivate_staff(
        cls,
        staff: StaffProfile,
        actor: Optional[User] = None,
        force: bool = False,
    ) -> StaffProfile:
        """
        Deactivates staff member with governance integrity checks.
        Prevents deactivation if the underwriter has active policies or the
        claims handler has in-review claims, unless force=True or reassignment occurred.
        """
        if not force:
            if staff.user.is_underwriter:
                active_pol_count = Policy.objects.filter(underwriter=staff, status=PolicyStatus.ACTIVE).count()
                if active_pol_count > 0:
                    raise ServiceValidationError(
                        f"Cannot deactivate underwriter '{staff.staff_code}': "
                        f"{active_pol_count} active policy/policies currently assigned. "
                        f"Please reassign workload to another underwriter first."
                    )

            elif staff.user.is_claims_handler:
                active_claim_count = Claim.objects.filter(handler=staff, status=ClaimStatus.IN_REVIEW).count()
                if active_claim_count > 0:
                    raise ServiceValidationError(
                        f"Cannot deactivate claims handler '{staff.staff_code}': "
                        f"{active_claim_count} claim(s) currently in review. "
                        f"Please reassign workload or return claims to queue first."
                    )

        staff.is_active = False
        staff.save(update_fields=['is_active', 'updated_at'])

        staff.user.is_active = False
        staff.user.save(update_fields=['is_active', 'updated_at'])

        AuditService.log(
            action=AuditAction.STAFF_DELETED,
            target_entity='StaffProfile',
            target_id=str(staff.pk),
            actor=actor,
            details={
                'staff_code': staff.staff_code,
                'email': staff.user.email,
                'role': staff.user.role,
                'deactivated': True,
                'force': force,
            }
        )
        return staff
