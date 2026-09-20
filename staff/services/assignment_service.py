from typing import Optional
from django.db import transaction
from django.utils import timezone
from accounts.models import User, UserRole
from customers.models import CustomerProfile
from staff.models import StaffCustomerAssignment, AssignmentStatus
from audit.models import AuditAction
from audit.services.audit_service import AuditService
from core.services import ServiceValidationError


class StaffAssignmentService:
    """
    Manages persistent assignments between Staff members and Customers:
    - Initial customer assignment
    - Reassignment / transfer preserving lineage
    - Revocation / unassignment
    - Access authorization verification
    """

    @classmethod
    @transaction.atomic
    def assign_customer(
        cls,
        staff_user: User,
        customer: CustomerProfile,
        assigned_by: Optional[User] = None,
        reason: str = '',
        notes: str = '',
    ) -> StaffCustomerAssignment:
        """
        Assigns a customer to a staff member. Enforces single active assignment per customer.
        """
        if not staff_user.is_staff_member or not staff_user.is_active:
            raise ServiceValidationError("Target user must be an active staff member.")

        existing = StaffCustomerAssignment.objects.filter(customer=customer, status=AssignmentStatus.ACTIVE).first()
        if existing:
            if existing.staff == staff_user:
                return existing
            # Transfer existing assignment
            return cls.transfer_customer(
                customer=customer,
                new_staff_user=staff_user,
                assigned_by=assigned_by,
                reason=reason or "Reassigned by administrator",
                notes=notes,
            )

        assignment = StaffCustomerAssignment.objects.create(
            staff=staff_user,
            customer=customer,
            assigned_by=assigned_by,
            assigned_at=timezone.now(),
            status=AssignmentStatus.ACTIVE,
            assignment_reason=reason,
            notes=notes,
        )

        AuditService.log(
            action=AuditAction.CUSTOMER_ASSIGNED,
            target_entity='CustomerProfile',
            target_id=str(customer.pk),
            actor=assigned_by or staff_user,
            details={
                'customer_code': customer.customer_code,
                'staff_email': staff_user.email,
                'assigned_by': assigned_by.email if assigned_by else 'System',
                'reason': reason,
            }
        )
        return assignment

    @classmethod
    @transaction.atomic
    def transfer_customer(
        cls,
        customer: CustomerProfile,
        new_staff_user: User,
        assigned_by: Optional[User] = None,
        reason: str = '',
        notes: str = '',
    ) -> StaffCustomerAssignment:
        """
        Transfers customer assignment to a new staff member while preserving historical assignment record.
        """
        if not new_staff_user.is_staff_member or not new_staff_user.is_active:
            raise ServiceValidationError("Target user must be an active staff member.")

        existing = StaffCustomerAssignment.objects.filter(customer=customer, status=AssignmentStatus.ACTIVE).first()
        now = timezone.now()

        old_staff_email = None
        if existing:
            if existing.staff == new_staff_user:
                return existing
            old_staff_email = existing.staff.email
            existing.status = AssignmentStatus.TRANSFERRED
            existing.unassigned_at = now
            existing.save(update_fields=['status', 'unassigned_at', 'updated_at'])

        new_assignment = StaffCustomerAssignment.objects.create(
            staff=new_staff_user,
            customer=customer,
            assigned_by=assigned_by,
            assigned_at=now,
            status=AssignmentStatus.ACTIVE,
            assignment_reason=reason or f"Transferred from {old_staff_email or 'unassigned'}",
            notes=notes,
        )

        AuditService.log(
            action=AuditAction.CUSTOMER_TRANSFERRED,
            target_entity='CustomerProfile',
            target_id=str(customer.pk),
            actor=assigned_by or new_staff_user,
            details={
                'customer_code': customer.customer_code,
                'previous_staff': old_staff_email,
                'new_staff': new_staff_user.email,
                'assigned_by': assigned_by.email if assigned_by else 'System',
                'reason': reason,
            }
        )
        return new_assignment

    @classmethod
    @transaction.atomic
    def unassign_customer(
        cls,
        customer: CustomerProfile,
        assigned_by: Optional[User] = None,
        reason: str = '',
    ) -> bool:
        """
        Removes active assignment from a customer.
        """
        existing = StaffCustomerAssignment.objects.filter(customer=customer, status=AssignmentStatus.ACTIVE).first()
        if not existing:
            return False

        existing.status = AssignmentStatus.INACTIVE
        existing.unassigned_at = timezone.now()
        existing.save(update_fields=['status', 'unassigned_at', 'updated_at'])

        AuditService.log(
            action=AuditAction.CUSTOMER_UNASSIGNED,
            target_entity='CustomerProfile',
            target_id=str(customer.pk),
            actor=assigned_by or existing.staff,
            details={
                'customer_code': customer.customer_code,
                'unassigned_from': existing.staff.email,
                'assigned_by': assigned_by.email if assigned_by else 'System',
                'reason': reason,
            }
        )
        return True

    @classmethod
    def is_customer_assigned_to_staff(cls, staff_user: User, customer: CustomerProfile) -> bool:
        """
        Checks if a customer is actively assigned to a specific staff member.
        """
        if not staff_user.is_authenticated:
            return False
        if staff_user.is_administrator or staff_user.is_superuser:
            return True
        return StaffCustomerAssignment.objects.filter(
            staff=staff_user,
            customer=customer,
            status=AssignmentStatus.ACTIVE
        ).exists()

    @classmethod
    def get_assigned_customers(cls, staff_user: User):
        """
        Returns QuerySet of customers actively assigned to this staff member.
        """
        if staff_user.is_administrator or staff_user.is_superuser:
            return CustomerProfile.objects.all().select_related('user')
        return CustomerProfile.objects.filter(
            staff_assignments__staff=staff_user,
            staff_assignments__status=AssignmentStatus.ACTIVE
        ).select_related('user').distinct()

    @classmethod
    def get_assignment_history(cls, customer: CustomerProfile):
        """
        Returns full historical audit trail of staff assignments for this customer.
        """
        return customer.staff_assignments.select_related('staff', 'assigned_by').order_by('-assigned_at')
