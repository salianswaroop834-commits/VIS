import pytest
from unittest.mock import MagicMock, patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.services.supabase_auth import SupabaseAuthService

User = get_user_model()


@pytest.mark.django_db
class TestSupabaseEmailOtpFlow:
    """
    Validates complete Supabase Email OTP authentication flow requirements:
    1. 6-digit numeric passcode validation.
    2. Rate limiting cooldown on resend/request.
    3. Brute force / max attempts lockout.
    4. Proper invocation of client.auth.verify_otp with type='email'.
    5. Session management and Supabase token persistence.
    6. Friendly error messaging without leaking internals.
    """

    def test_verify_otp_rejects_invalid_digit_length(self):
        # Invalid lengths and non-digit tokens must be rejected prior to Supabase dispatch
        for bad_code in ["", "12345", "1234567", "abcdef", "12a456", "   "]:
            res = SupabaseAuthService.verify_otp("test@example.com", bad_code)
            assert res["success"] is False
            assert res["provider"] == "validation"
            assert "6-digit" in res["message"]

    def test_verify_otp_calls_supabase_with_type_email(self):
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "supa-uid-12345"
        mock_user.email = "verified@example.com"
        mock_user.user_metadata = {"role": "CUSTOMER"}

        mock_session = MagicMock()
        mock_session.access_token = "mock-access-token-xyz"
        mock_session.refresh_token = "mock-refresh-token-abc"

        mock_auth_res = MagicMock()
        mock_auth_res.user = mock_user
        mock_auth_res.session = mock_session

        mock_client.auth.verify_otp.return_value = mock_auth_res

        with patch.object(SupabaseAuthService, "get_client", return_value=mock_client):
            result = SupabaseAuthService.verify_otp("verified@example.com", "654321")

            assert result["success"] is True
            assert result["provider"] == "supabase"
            assert result["access_token"] == "mock-access-token-xyz"
            assert result["refresh_token"] == "mock-refresh-token-abc"
            assert result["user"].email == "verified@example.com"
            assert result["user"].supabase_uid == "supa-uid-12345"

            # Verify client was called with exact params: type='email'
            mock_client.auth.verify_otp.assert_called_once_with({
                "email": "verified@example.com",
                "token": "654321",
                "type": "email",
            })

    def test_send_otp_calls_supabase_sign_in_with_otp(self):
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_otp.return_value = {"message_id": "msg-123"}

        with patch.object(SupabaseAuthService, "get_client", return_value=mock_client):
            result = SupabaseAuthService.send_otp("driver@example.com")
            assert result["success"] is True
            assert result["provider"] == "supabase"
            mock_client.auth.sign_in_with_otp.assert_called_once_with({"email": "driver@example.com"})

    def test_resend_cooldown_rate_limiting_in_view(self, client):
        email = "applicant@example.com"

        # Mock SupabaseAuthService.send_otp
        with patch.object(SupabaseAuthService, "send_otp", return_value={"success": True, "message": "Dispatched"}):
            # 1. Initial request succeeds
            resp1 = client.post(reverse("accounts:otp-request"), {"email": email}, follow=True)
            assert resp1.status_code == 200
            assert client.session.get("pending_otp_email") == email
            assert "last_otp_request_at" in client.session

            # 2. Immediate resend within 30 seconds is blocked by cooldown
            resp2 = client.post(reverse("accounts:otp-request"), {"email": email}, follow=True)
            assert resp2.status_code == 200
            content = resp2.content.decode("utf-8")
            assert "Please wait" in content and "seconds before requesting" in content

    def test_otp_verify_view_brute_force_lockout(self, client):
        email = "lockout@example.com"
        session = client.session
        session["pending_otp_email"] = email
        session["otp_attempts"] = 0
        session.save()

        # Mock verify_otp to fail
        with patch.object(SupabaseAuthService, "verify_otp", return_value={"success": False, "message": "Invalid code"}):
            # Send 5 incorrect attempts
            for i in range(5):
                resp = client.post(reverse("accounts:verify-otp"), {"email": email, "otp_code": "111111"})
                assert resp.status_code == 200

            # Check attempt count reached 5
            assert client.session.get("otp_attempts") == 5

            # 6th attempt must be locked out
            resp_locked = client.post(reverse("accounts:verify-otp"), {"email": email, "otp_code": "111111"})
            assert resp_locked.status_code == 200
            content = resp_locked.content.decode("utf-8")
            assert "Maximum verification attempts exceeded" in content

    def test_otp_verify_view_success_establishes_session(self, client):
        email = "authuser@example.com"
        user = User.objects.create_user(
            username="authuser",
            email=email,
            role="CUSTOMER",
        )

        mock_result = {
            "success": True,
            "provider": "supabase",
            "user": user,
            "access_token": "supabase-jwt-access-token-sample",
            "refresh_token": "supabase-jwt-refresh-token-sample",
        }

        with patch.object(SupabaseAuthService, "verify_otp", return_value=mock_result):
            resp = client.post(reverse("accounts:verify-otp"), {
                "email": email,
                "otp_code": "789012",
            }, follow=True)

            assert resp.status_code == 200
            # Check user is logged into Django
            assert resp.context["user"].is_authenticated
            assert resp.context["user"].email == email
            # Check Supabase tokens are persisted in session
            assert client.session.get("supabase_access_token") == "supabase-jwt-access-token-sample"
            assert client.session.get("supabase_refresh_token") == "supabase-jwt-refresh-token-sample"
