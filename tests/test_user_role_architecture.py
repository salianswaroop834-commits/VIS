import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib import admin
from accounts.models import UserRole, EmailOtpToken
from customers.models import CustomerProfile
from staff.models import StaffProfile, UnderwriterProfile, ClaimsHandlerProfile, StaffStatus
from staff.services.staff_service import StaffService

User = get_user_model()


@pytest.mark.django_db
class TestUserRoleArchitecture:
    """
    Tests validating the single User model and hierarchical role/profile architecture:
    1. Single central User model with UUID primary key.
    2. CustomerProfile 1-to-1 linkage and data ownership.
    3. StaffProfile 1-to-1 linkage and organizational data.
    4. Specialized UnderwriterProfile auto-provisioning and limits.
    5. Specialized ClaimsHandlerProfile auto-provisioning and settlement limits.
    6. Role access matrix and helper properties (is_customer, is_underwriter, etc.).
    7. Django Admin registrations and credential protection.
    """

    def test_single_user_model_attributes(self):
        user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="SecurePassword123!",
            role=UserRole.CUSTOMER,
        )
        assert user.pk is not None
        assert len(str(user.pk)) == 36  # UUID format
        assert user.email == "testuser@example.com"
        assert user.role == UserRole.CUSTOMER
        assert user.is_customer is True
        assert user.is_underwriter is False
        assert user.is_claims_handler is False
        assert user.is_administrator is False

    def test_customer_profile_association(self):
        user = User.objects.create_user(
            username="cust_alex",
            email="alex.customer@example.com",
            role=UserRole.CUSTOMER,
        )
        cust_profile = CustomerProfile.objects.create(
            user=user,
            customer_code="CUST-ALEX001",
            city="Metropolis",
            state="NY",
        )
        assert hasattr(user, "customer_profile")
        assert user.customer_profile.customer_code == "CUST-ALEX001"
        assert str(cust_profile) == "CUST-ALEX001 - alex.customer@example.com"

    def test_underwriter_hierarchy_and_profile(self):
        uw_user = User.objects.create_user(
            username="uw_sarah",
            email="sarah.uw@example.com",
            role=UserRole.UNDERWRITER,
        )
        staff_prof = StaffService.create_staff_profile(
            user=uw_user,
            staff_code="UW-901",
            department="Commercial Underwriting",
            assigned_region="Northeast",
        )

        # Verify StaffProfile created
        assert staff_prof.user == uw_user
        assert staff_prof.staff_code == "UW-901"
        assert staff_prof.status == StaffStatus.ACTIVE
        assert staff_prof.is_active_staff is True

        # Verify UnderwriterProfile auto-provisioned
        assert hasattr(staff_prof, "underwriter_profile")
        uw_prof = staff_prof.underwriter_profile
        assert uw_prof.underwriting_limit == Decimal("2500000.00")
        assert uw_prof.specialization == "Commercial Fleets"
        assert "Underwriter UW-901" in str(uw_prof)

        # Verify User convenience accessor
        assert uw_user.underwriter_profile == uw_prof
        assert uw_user.claims_handler_profile is None
        assert uw_user.is_underwriter is True

    def test_claims_handler_hierarchy_and_profile(self):
        ch_user = User.objects.create_user(
            username="ch_david",
            email="david.ch@example.com",
            role=UserRole.CLAIMS_HANDLER,
        )
        staff_prof = StaffService.create_staff_profile(
            user=ch_user,
            staff_code="CH-502",
            department="Rapid Claims Settlement",
            max_claim_approval_limit=Decimal("75000.00"),
            assigned_region="Midwest",
        )

        # Verify StaffProfile created
        assert staff_prof.user == ch_user
        assert staff_prof.staff_code == "CH-502"

        # Verify ClaimsHandlerProfile auto-provisioned
        assert hasattr(staff_prof, "claims_handler_profile")
        ch_prof = staff_prof.claims_handler_profile
        assert ch_prof.max_claim_approval_limit == Decimal("75000.00")
        assert ch_prof.active_claim_capacity == 25
        assert "Handler CH-502" in str(ch_prof)

        # Verify User convenience accessor
        assert ch_user.claims_handler_profile == ch_prof
        assert ch_user.underwriter_profile is None
        assert ch_user.is_claims_handler is True

    def test_administrator_role_permissions(self):
        admin_user = User.objects.create_user(
            username="admin_rachel",
            email="rachel.admin@example.com",
            role=UserRole.ADMINISTRATOR,
            is_staff=True,
        )
        assert admin_user.is_administrator is True
        assert admin_user.is_staff is True
        assert admin_user.is_superuser is False  # Least privilege: not automatically superuser

        # Superuser also satisfies is_administrator
        superuser = User.objects.create_superuser(
            username="super_root",
            email="root@example.com",
            password="RootPassword123!",
        )
        assert superuser.is_administrator is True

    def test_django_admin_registration(self):
        # Verify all key models are registered in Django admin site
        assert User in admin.site._registry
        assert CustomerProfile in admin.site._registry
        assert StaffProfile in admin.site._registry
        assert UnderwriterProfile in admin.site._registry
        assert ClaimsHandlerProfile in admin.site._registry

        # Verify UserAdmin protects sensitive fields
        user_admin = admin.site._registry[User]
        assert "password" not in user_admin.list_display
        assert "supabase_uid" in user_admin.readonly_fields

        # Verify EmailOtpTokenAdmin has add disabled
        otp_admin = admin.site._registry[EmailOtpToken]
        assert otp_admin.has_add_permission(None) is False
