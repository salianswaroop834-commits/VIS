from datetime import timedelta
from pathlib import Path
import pytest
from django.urls import reverse
from django.utils import timezone
from django.core import mail
from django.contrib.auth import get_user_model
from apps.accounts.models import EmailOtpToken, UserRole
from apps.accounts.services.otp_service import OtpService
from apps.customers.models import CustomerProfile

User = get_user_model()


@pytest.mark.django_db
class TestPhase2AuthenticationAndRBAC:
    """
    Automated verification of Phase 2 requirements:
    1. Email OTP generation, dispatch, verification, expiration, and replay prevention.
    2. Role-Based Access Control (RBAC) across customer, underwriter, handler, and admin portals.
    3. Customer registration and profile linkage.
    4. Supabase SQL DDL and RLS policy file integrity.
    """

    def test_otp_dispatch_and_verification_flow(self):
        email = "test.applicant@example.com"
        # 1. Request OTP
        success, message, raw_code = OtpService.request_otp(email)
        assert success is True
        assert raw_code is not None
        assert len(raw_code) == 6
        assert raw_code.isdigit()

        # Verify email was dispatched
        assert len(mail.outbox) >= 1
        assert raw_code in mail.outbox[-1].subject or raw_code in mail.outbox[-1].body

        # Verify token in DB
        token = EmailOtpToken.objects.filter(email=email, is_used=False).first()
        assert token is not None
        assert token.is_used is False
        assert token.attempts_count == 0

        # 2. Verify with invalid code
        fail_success, fail_msg, fail_user = OtpService.verify_otp(email, "000000")
        assert fail_success is False
        assert fail_user is None
        token.refresh_from_db()
        assert token.attempts_count == 1

        # 3. Verify with valid code
        verify_success, verify_msg, verified_user = OtpService.verify_otp(email, raw_code)
        assert verify_success is True
        assert verified_user is not None
        assert verified_user.email == email
        assert verified_user.email_verified is True
        token.refresh_from_db()
        assert token.is_used is True

        # 4. Replay attack: reusing the same OTP must fail
        replay_success, replay_msg, replay_user = OtpService.verify_otp(email, raw_code)
        assert replay_success is False
        assert replay_user is None

    def test_otp_expired_token_rejected(self):
        email = "expired.test@example.com"
        success, _, code = OtpService.request_otp(email)
        assert success is True

        # Manually expire the token in the database
        token = EmailOtpToken.objects.get(email=email, is_used=False)
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save()

        # Attempt verification on expired token
        verify_success, msg, user = OtpService.verify_otp(email, code)
        assert verify_success is False
        assert "No valid, unexpired OTP found" in msg
        assert user is None

    def test_otp_max_attempts_lockout(self):
        email = "lockout.test@example.com"
        success, _, valid_code = OtpService.request_otp(email)
        assert success is True

        # Exhaust 5 attempts with wrong codes
        for _ in range(5):
            OtpService.verify_otp(email, "999999")

        # 6th attempt with the correct code must now fail due to attempt limit
        verify_success, msg, user = OtpService.verify_otp(email, valid_code)
        assert verify_success is False
        assert "Maximum verification attempts exceeded" in msg

    def test_customer_registration_creates_profile(self, client):
        response = client.post(reverse('accounts:register'), {
            'email': 'new.driver@example.com',
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone_number': '+15550198822',
            'password': 'SecurePassword123!',
        })
        assert response.status_code == 302
        assert response.url == reverse('customers:dashboard')

        user = User.objects.filter(email='new.driver@example.com').first()
        assert user is not None
        assert user.role == UserRole.CUSTOMER
        assert user.first_name == 'Jane'
        assert hasattr(user, 'customer_profile')
        assert user.customer_profile.customer_code.startswith('CUST-')

    def test_unauthenticated_user_redirected_from_protected_views(self, client):
        protected_urls = [
            reverse('customers:dashboard'),
            reverse('customers:policies'),
            reverse('customers:claims'),
            reverse('staff:underwriter-dashboard'),
            reverse('staff:claims-handler-dashboard'),
            reverse('staff:admin-dashboard'),
            reverse('staff:staff-list'),
        ]
        for url in protected_urls:
            resp = client.get(url)
            assert resp.status_code == 302
            assert '/auth/login/' in resp.url

    def test_role_based_access_denial(self, client):
        # Create user accounts for each role
        customer_user = User.objects.create_user(
            username='cust_alex',
            email='alex@example.com',
            password='Password123!',
            role=UserRole.CUSTOMER,
        )
        handler_user = User.objects.create_user(
            username='ch_sarah',
            email='sarah@example.com',
            password='Password123!',
            role=UserRole.CLAIMS_HANDLER,
        )
        underwriter_user = User.objects.create_user(
            username='uw_mark',
            email='mark@example.com',
            password='Password123!',
            role=UserRole.UNDERWRITER,
        )

        # 1. Customer accessing Claims Handler dashboard -> 403 Forbidden
        client.force_login(customer_user)
        resp = client.get(reverse('staff:claims-handler-dashboard'))
        assert resp.status_code == 403

        # 2. Customer accessing Underwriter dashboard -> 403 Forbidden
        resp = client.get(reverse('staff:underwriter-dashboard'))
        assert resp.status_code == 403

        # 3. Customer accessing Admin dashboard -> 403 Forbidden
        resp = client.get(reverse('staff:admin-dashboard'))
        assert resp.status_code == 403

        # 4. Claims Handler accessing Underwriter dashboard -> 403 Forbidden
        client.force_login(handler_user)
        resp = client.get(reverse('staff:underwriter-dashboard'))
        assert resp.status_code == 403

        # 5. Claims Handler accessing own dashboard -> 200 OK
        resp = client.get(reverse('staff:claims-handler-dashboard'))
        assert resp.status_code == 200

        # 6. Underwriter accessing own dashboard -> 200 OK
        client.force_login(underwriter_user)
        resp = client.get(reverse('staff:underwriter-dashboard'))
        assert resp.status_code == 200

    def test_supabase_sql_migration_script_integrity(self):
        sql_path = Path(r"d:\VIS\supabase\migrations\01_schema_and_rls.sql")
        assert sql_path.exists(), "Supabase migration script does not exist."
        sql_content = sql_path.read_text(encoding='utf-8')

        # Check required PostgreSQL extensions
        assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in sql_content
        assert 'CREATE EXTENSION IF NOT EXISTS "vector"' in sql_content
        assert 'CREATE EXTENSION IF NOT EXISTS "pgcrypto"' in sql_content

        # Check RLS activation statements
        required_rls_tables = [
            'customer_profiles',
            'staff_profiles',
            'vehicles',
            'quotation_drafts',
            'policies',
            'claims',
            'claim_documents',
            'claim_events',
            'service_requests',
            'notifications',
            'audit_logs',
        ]
        for table in required_rls_tables:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql_content, (
                f"Missing RLS enablement for table {table}"
            )

        # Check key RLS policies
        assert "CREATE POLICY customer_read_own_profile" in sql_content
        assert "CREATE POLICY customer_vehicles_select" in sql_content
        assert "CREATE POLICY policies_select" in sql_content
        assert "CREATE POLICY claims_select_customer" in sql_content
        assert "CREATE POLICY claims_select_handler" in sql_content
        assert "handler_id IS NULL" in sql_content # Shared unassigned pending queue policy
