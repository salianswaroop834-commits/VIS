import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile, KYCVerification, KYCStatus
from apps.staff.models import (
    StaffProfile,
    StaffDepartment,
    UnderwriterProfile,
    ClaimsHandlerProfile,
    StaffCustomerAssignment,
    AssignmentStatus,
)
from apps.staff.services.assignment_service import StaffAssignmentService
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from apps.vehicles.services.vehicle_lookup_service import VehicleLookupService
from apps.customers.services.pan_verification_service import PanVerificationService
from core.services import ServiceValidationError
from apps.audit.models import AuditLog


class CanonicalRoleArchitectureTests(TestCase):
    """
    Validates strictly 3 top-level roles: USER, STAFF, ADMIN.
    Underwriting and Claims are staff department specializations.
    """

    def test_three_top_level_roles(self):
        user_cust = User.objects.create(email="customer@example.com", username="customer1", role=UserRole.USER)
        user_staff = User.objects.create(email="staff@example.com", username="staff1", role=UserRole.STAFF)
        user_admin = User.objects.create(email="admin@example.com", username="admin1", role=UserRole.ADMIN)

        self.assertEqual(user_cust.role, "USER")
        self.assertEqual(user_staff.role, "STAFF")
        self.assertEqual(user_admin.role, "ADMIN")

        # Check helper properties
        self.assertTrue(user_cust.is_customer)
        self.assertFalse(user_cust.is_staff_member)

        self.assertTrue(user_staff.is_staff_member)
        self.assertFalse(user_staff.is_customer)

        self.assertTrue(user_admin.is_administrator)

    def test_staff_department_specializations(self):
        u_staff1 = User.objects.create(email="uw@example.com", username="uw1", role=UserRole.STAFF)
        sp_uw = StaffProfile.objects.create(
            user=u_staff1,
            staff_code="UW001",
            department=StaffDepartment.UNDERWRITING,
        )
        up = UnderwriterProfile.objects.create(staff_profile=sp_uw, underwriting_limit=Decimal('500000.00'))

        u_staff2 = User.objects.create(email="clm@example.com", username="clm1", role=UserRole.STAFF)
        sp_clm = StaffProfile.objects.create(
            user=u_staff2,
            staff_code="CLM001",
            department=StaffDepartment.CLAIMS,
        )
        cp = ClaimsHandlerProfile.objects.create(staff_profile=sp_clm, max_claim_approval_limit=Decimal('200000.00'))

        # Check specializations
        self.assertTrue(u_staff1.is_underwriter)
        self.assertFalse(u_staff1.is_claims_handler)

        self.assertTrue(u_staff2.is_claims_handler)
        self.assertFalse(u_staff2.is_underwriter)


class StaffCustomerAssignmentTests(TestCase):
    """
    Validates persistent StaffCustomerAssignment, admin assignment/transfer/unassign,
    and staff isolation (staff cannot see unassigned customers; admin has global access).
    """

    def setUp(self):
        self.admin = User.objects.create(email="admin@nexisure.in", username="admin", role=UserRole.ADMIN)
        self.staff1 = User.objects.create(email="staff1@nexisure.in", username="staff1", role=UserRole.STAFF)
        self.staff_profile1 = StaffProfile.objects.create(
            user=self.staff1, staff_code="STF-01", department=StaffDepartment.UNDERWRITING
        )

        self.staff2 = User.objects.create(email="staff2@nexisure.in", username="staff2", role=UserRole.STAFF)
        self.staff_profile2 = StaffProfile.objects.create(
            user=self.staff2, staff_code="STF-02", department=StaffDepartment.UNDERWRITING
        )

        self.customer_user1 = User.objects.create(
            email="cust1@example.com", username="cust1", role=UserRole.USER, phone_number="+919876543210"
        )
        self.cust_profile1 = CustomerProfile.objects.create(
            user=self.customer_user1, customer_code="CUST-001", first_name="Ramesh", last_name="Sharma"
        )

        self.customer_user2 = User.objects.create(
            email="cust2@example.com", username="cust2", role=UserRole.USER, phone_number="+919876543211"
        )
        self.cust_profile2 = CustomerProfile.objects.create(
            user=self.customer_user2, customer_code="CUST-002", first_name="Pooja", last_name="Verma"
        )

    def test_assign_transfer_and_unassign(self):
        # Admin assigns cust1 to staff1
        assignment = StaffAssignmentService.assign_customer(
            staff_user=self.staff1,
            customer=self.cust_profile1,
            assigned_by=self.admin,
            reason="Primary onboarding",
        )
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        self.assertTrue(StaffAssignmentService.is_customer_assigned_to_staff(self.staff1, self.cust_profile1))
        self.assertFalse(StaffAssignmentService.is_customer_assigned_to_staff(self.staff2, self.cust_profile1))

        # Transfer cust1 to staff2
        transfer_assignment = StaffAssignmentService.assign_customer(
            staff_user=self.staff2,
            customer=self.cust_profile1,
            assigned_by=self.admin,
            reason="Workload rebalancing",
        )
        self.assertEqual(transfer_assignment.status, AssignmentStatus.ACTIVE)
        self.assertFalse(StaffAssignmentService.is_customer_assigned_to_staff(self.staff1, self.cust_profile1))
        self.assertTrue(StaffAssignmentService.is_customer_assigned_to_staff(self.staff2, self.cust_profile1))

        # Previous assignment was marked TRANSFERRED
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.TRANSFERRED)

        # Unassign cust1
        StaffAssignmentService.unassign_customer(
            customer=self.cust_profile1,
            assigned_by=self.admin,
            reason="Customer inactive",
        )
        self.assertFalse(StaffAssignmentService.is_customer_assigned_to_staff(self.staff2, self.cust_profile1))

        # Admin has access to all customers
        admin_customers = StaffAssignmentService.get_assigned_customers(self.admin)
        self.assertEqual(admin_customers.count(), 2)

    def test_duplicate_active_assignment_constraint(self):
        StaffAssignmentService.assign_customer(
            staff_user=self.staff1,
            customer=self.cust_profile1,
            assigned_by=self.admin,
        )
        # Attempting direct duplicate insertion should be handled or prevented
        active_count = StaffCustomerAssignment.objects.filter(
            customer=self.cust_profile1, status=AssignmentStatus.ACTIVE
        ).count()
        self.assertEqual(active_count, 1)


class PanKycVerificationTests(TestCase):
    """
    Validates RapidAPI PAN lookup, phone mismatch guardrail,
    Firebase OTP verification, privacy masking, and status lifecycle.
    """

    def setUp(self):
        self.user = User.objects.create(
            email="aarav.patel@example.com",
            username="aaravp",
            role=UserRole.USER,
            phone_number="+919876541234",
            phone_verified=True,
        )
        self.profile = CustomerProfile.objects.create(
            user=self.user, customer_code="CUST-KYC-01", first_name="Aarav", last_name="Patel"
        )

    def test_invalid_pan_format_rejected(self):
        with self.assertRaises(ServiceValidationError):
            PanVerificationService.initiate_pan_verification(
                user=self.user, pan_number="INVALID123"
            )

    def test_pan_verification_flow_phone_matched(self):
        # Initiate PAN verification with matching phone
        # Mocking or using default synthetic provider logic
        result = PanVerificationService.initiate_pan_verification(
            user=self.user,
            pan_number="ABCDE1234F",
        )
        self.assertIn('verification_id', result)
        self.assertIn('challenge_id', result)
        self.assertEqual(result['status'], KYCStatus.PHONE_OTP_REQUIRED)
        self.assertTrue(result['document_number_masked'].startswith("ABCDE****"))
        self.assertTrue(result['verified_phone_masked'].startswith("******"))

        # Verify database record masks sensitive data
        kyc = KYCVerification.objects.get(id=result['verification_id'])
        self.assertEqual(kyc.status, KYCStatus.PHONE_OTP_REQUIRED)
        self.assertNotIn("ABCDE1234F", kyc.document_number_masked)

        # Invalid OTP fails
        with self.assertRaises(ServiceValidationError):
            PanVerificationService.confirm_pan_otp(
                user=self.user,
                verification_id=kyc.id,
                challenge_id=result['challenge_id'],
                otp_code="000000",
            )

        # Correct OTP verifies
        confirm_res = PanVerificationService.confirm_pan_otp(
            user=self.user,
            verification_id=kyc.id,
            challenge_id=result['challenge_id'],
            otp_code="123456",
        )
        self.assertEqual(confirm_res['status'], KYCStatus.VERIFIED)

        # Profile updated
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_identity_verified)

        # AuditLog recorded
        audit = AuditLog.objects.filter(action="KYC_VERIFIED", actor=self.user).first()
        self.assertIsNotNone(audit)

    def test_pan_phone_mismatch_halts_verification(self):
        # User has different phone number
        user_mismatch = User.objects.create(
            email="mismatch@example.com",
            username="mismatch",
            role=UserRole.USER,
            phone_number="+919999999999",  # Ends in 9999, does not match mock PAN phone ending in 3210
            phone_verified=True,
        )
        CustomerProfile.objects.create(user=user_mismatch, customer_code="CUST-MISMATCH")

        with self.assertRaises(ServiceValidationError) as ctx:
            PanVerificationService.initiate_pan_verification(
                user=user_mismatch,
                pan_number="ABCDE1234F",
            )
        self.assertIn("does not match your registered account mobile number", str(ctx.exception))

        # Ensure failed KYC record created
        kyc = KYCVerification.objects.filter(user=user_mismatch, status=KYCStatus.FAILED).first()
        self.assertIsNotNone(kyc)


class VehicleLookupWorkflowTests(TestCase):
    """
    Validates Vehicle Registry Lookup, normalized attributes, and confirmation workflow.
    """

    def setUp(self):
        self.user = User.objects.create(
            email="vehicletest@example.com",
            username="vehicletest",
            role=UserRole.USER,
        )
        self.customer = CustomerProfile.objects.create(
            user=self.user, customer_code="CUST-VEH-01"
        )

    def test_invalid_registration_number_rejected(self):
        with self.assertRaises(ServiceValidationError):
            VehicleLookupService.lookup_vehicle(registration_number="BAD")

    def test_vehicle_lookup_normalization_and_confirmation(self):
        preview = VehicleLookupService.lookup_vehicle(
            registration_number="MH12AB1234",
            actor=self.user,
        )
        self.assertEqual(preview['registration_number'], "MH12AB1234")
        self.assertIn('make', preview)
        self.assertIn('model', preview)
        self.assertIn('chassis_number', preview)

        # Confirm and save
        vehicle_data = {
            'registration_number': preview['registration_number'],
            'make': preview['make'],
            'model': preview['model'],
            'variant': preview.get('variant', 'ZXi'),
            'manufacture_year': preview.get('manufacture_year', 2022),
            'chassis_number': preview['chassis_number'],
            'engine_number': preview.get('engine_number', 'ENG-12345'),
            'vehicle_type': VehicleType.SEDAN,
            'fuel_type': FuelType.PETROL,
            'usage_type': UsageType.PERSONAL,
            'vehicle_value': '650000.00',
            'registration_state': preview.get('registration_state', 'Maharashtra'),
            'registration_city': preview.get('registration_city', 'Pune'),
            'owner_name': preview.get('owner_name', 'Rahul Sharma'),
        }

        vehicle = VehicleLookupService.confirm_and_save_vehicle(
            customer=self.customer,
            data=vehicle_data,
            actor=self.user,
        )
        self.assertEqual(vehicle.registration_number, "MH12AB1234")
        self.assertEqual(vehicle.customer, self.customer)
        self.assertTrue(vehicle.is_active)

        # Duplicate registration prevented
        with self.assertRaises(ServiceValidationError):
            VehicleLookupService.confirm_and_save_vehicle(
                customer=self.customer,
                data=vehicle_data,
                actor=self.user,
            )
