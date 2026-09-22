import pytest
from unittest.mock import MagicMock
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.accounts.models import UserRole
from apps.accounts.services.supabase_auth import SupabaseAuthService

User = get_user_model()


@pytest.mark.django_db
class TestRoleGovernanceAndAdminSync:
    """
    Validates:
    1. sync_supabase_user never downgrades existing privileged staff/admin roles.
    2. sync_supabase_user defaults new self-registered users to CUSTOMER and rejects client role tampering.
    3. Django is the single source of truth for application roles.
    4. Django Admin login page renders guidance banner for passwordless staff.
    5. OTP-authenticated staff session grants direct access to /django-admin/ without password prompt.
    """

    def test_sync_never_downgrades_existing_underwriter(self):
        uw_user = User.objects.create_user(
            username="existing_uw",
            email="existing_uw@example.com",
            role=UserRole.UNDERWRITER,
            is_staff=True,
        )

        mock_supa_user = MagicMock()
        mock_supa_user.id = "supa-uw-uuid-111"
        mock_supa_user.email = "existing_uw@example.com"
        # Even if Supabase metadata claims it is a customer or empty
        mock_supa_user.user_metadata = {"role": "CUSTOMER"}

        synced_user = SupabaseAuthService.sync_supabase_user(mock_supa_user)

        assert synced_user.pk == uw_user.pk
        assert synced_user.role == UserRole.UNDERWRITER  # Must NOT be downgraded
        assert synced_user.is_staff is True
        assert synced_user.supabase_uid == "supa-uw-uuid-111"
        assert synced_user.email_verified is True

    def test_sync_never_downgrades_existing_administrator(self):
        admin_user = User.objects.create_user(
            username="existing_admin",
            email="existing_admin@example.com",
            role=UserRole.ADMINISTRATOR,
            is_staff=True,
        )

        mock_supa_user = MagicMock()
        mock_supa_user.id = "supa-admin-uuid-222"
        mock_supa_user.email = "existing_admin@example.com"
        mock_supa_user.user_metadata = {}  # Empty metadata

        synced_user = SupabaseAuthService.sync_supabase_user(mock_supa_user)

        assert synced_user.pk == admin_user.pk
        assert synced_user.role == UserRole.ADMINISTRATOR  # Preserved
        assert synced_user.is_staff is True
        assert synced_user.supabase_uid == "supa-admin-uuid-222"

    def test_sync_never_downgrades_existing_claims_handler(self):
        ch_user = User.objects.create_user(
            username="existing_ch",
            email="existing_ch@example.com",
            role=UserRole.CLAIMS_HANDLER,
            is_staff=True,
        )

        mock_supa_user = MagicMock()
        mock_supa_user.id = "supa-ch-uuid-333"
        mock_supa_user.email = "existing_ch@example.com"
        mock_supa_user.user_metadata = {"role": "arbitrary_external_role"}

        synced_user = SupabaseAuthService.sync_supabase_user(mock_supa_user)

        assert synced_user.pk == ch_user.pk
        assert synced_user.role == UserRole.CLAIMS_HANDLER  # Preserved

    def test_new_self_registering_user_always_defaults_to_customer(self):
        mock_supa_user = MagicMock()
        mock_supa_user.id = "supa-new-uuid-444"
        mock_supa_user.email = "new_attacker@example.com"
        # Malicious client attempting to inject privileged role during registration
        mock_supa_user.user_metadata = {"role": "ADMINISTRATOR"}

        synced_user = SupabaseAuthService.sync_supabase_user(mock_supa_user)

        assert synced_user.role == UserRole.CUSTOMER  # Must be CUSTOMER
        assert synced_user.is_staff is False
        assert synced_user.is_superuser is False
        assert hasattr(synced_user, "customer_profile")

    def test_django_admin_login_page_renders_otp_guidance(self, client):
        resp = client.get("/django-admin/login/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Passwordless Staff / Administrator Login" in content
        assert "Nexisure OTP Authentication Portal" in content
        assert reverse("accounts:verify-otp") in content

    def test_authenticated_staff_session_grants_django_admin_access(self, client):
        staff_admin = User.objects.create_user(
            username="admin_sso",
            email="admin.sso@example.com",
            role=UserRole.ADMINISTRATOR,
            is_staff=True,
        )
        # Simulate session created via OTP verification login(request, user)
        client.force_login(staff_admin)

        resp = client.get("/django-admin/")
        assert resp.status_code == 200  # Admitted directly via Django session SSO
