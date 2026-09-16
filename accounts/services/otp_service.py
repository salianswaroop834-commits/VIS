import secrets
import hashlib
from datetime import timedelta
from typing import Tuple, Optional
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from accounts.models import User, EmailOtpToken
from core.services import DataNormalizer


class OtpService:
    """
    Manages generation, secure hashing, email dispatch, and verification
    of One-Time Passcodes (OTP) for passwordless authentication.
    """
    OTP_VALIDITY_MINUTES = 10
    MAX_VERIFICATION_ATTEMPTS = 5

    @classmethod
    def _hash_otp(cls, email: str, code: str) -> str:
        """Hash OTP salted with email and secret key."""
        salt = settings.SECRET_KEY[:16]
        payload = f"{salt}:{email}:{code}".encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def request_otp(cls, email: str) -> Tuple[bool, str, Optional[str]]:
        """
        Generates and delivers a 6-digit OTP code to the requested email.
        Returns: (success, message, raw_code_for_testing)
        """
        normalized_email = DataNormalizer.normalize_email(email)
        if not normalized_email:
            return False, "Please enter a valid email address.", None

        # Check if user exists or can register
        user = User.objects.filter(email=normalized_email).first()

        # Invalidate any existing unused tokens for this email
        EmailOtpToken.objects.filter(email=normalized_email, is_used=False).update(is_used=True)

        # Generate cryptographically secure 6-digit number (100000 - 999999)
        code = str(secrets.randbelow(900000) + 100000)
        otp_hash = cls._hash_otp(normalized_email, code)
        expires_at = timezone.now() + timedelta(minutes=cls.OTP_VALIDITY_MINUTES)

        # Persist hashed token
        EmailOtpToken.objects.create(
            email=normalized_email,
            otp_hash=otp_hash,
            expires_at=expires_at,
            user=user,
        )

        # Send OTP email
        subject = f"[{settings.PLATFORM_NAME}] Your One-Time Security Passcode: {code}"
        message = (
            f"Hello,\n\n"
            f"Your one-time security passcode (OTP) for Nexisure Vehicle Insurance is:\n\n"
            f"   ===============================\n"
            f"               {code}\n"
            f"   ===============================\n\n"
            f"This passcode will expire in {cls.OTP_VALIDITY_MINUTES} minutes.\n\n"
            f"Please enter this code on the authentication screen to verify your identity.\n\n"
            f"SECURITY NOTICE: For your protection, never share this passcode with anyone. "
            f"Nexisure personnel will never ask you for this verification code. "
            f"If you did not initiate this request, please disregard this email.\n\n"
            f"Regards,\n"
            f"Nexisure Identity & Security Operations\n"
            f"https://nexisure.internal\n"
        )

        html_message = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Your One-Time Security Passcode</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 32px 16px;">
  <div style="max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); padding: 36px 32px; box-shadow: 0 20px 40px rgba(0,0,0,0.4);">
    <div style="margin-bottom: 24px; display: flex; align-items: center;">
      <span style="font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">Nexi<span style="color: #00f2fe;">sure</span></span>
      <span style="margin-left: 12px; padding: 3px 10px; background: rgba(0,242,254,0.12); color: #00f2fe; font-size: 11px; font-weight: 700; border-radius: 9999px; border: 1px solid rgba(0,242,254,0.3); text-transform: uppercase; letter-spacing: 0.5px;">Security Verification</span>
    </div>
    
    <h2 style="font-size: 20px; font-weight: 700; color: #ffffff; margin: 0 0 12px 0;">One-Time Security Passcode</h2>
    <p style="font-size: 14px; line-height: 1.6; color: #94a3b8; margin: 0 0 24px 0;">
      Hello,<br>
      You requested a single-use verification code to securely access your <strong>Nexisure Vehicle Insurance</strong> workspace. Use the 6-digit passcode below to proceed:
    </p>

    <div style="background: rgba(15, 23, 42, 0.8); border: 2px dashed rgba(0,242,254,0.4); border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 2px; color: #94a3b8; margin-bottom: 8px;">Single-Use Security Code</div>
      <div style="font-family: 'Courier New', Courier, monospace; font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #00f2fe; text-shadow: 0 0 20px rgba(0,242,254,0.3);">{code}</div>
      <div style="font-size: 12px; color: #64748b; margin-top: 10px;">Valid for <strong>{cls.OTP_VALIDITY_MINUTES} minutes</strong> &bull; Maximum 5 attempts</div>
    </div>

    <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 12px 16px; margin: 24px 0;">
      <p style="font-size: 12px; color: #fbbf24; margin: 0; line-height: 1.5;">
        <strong>Security Advisory:</strong> For your protection, never share this passcode with anyone. Nexisure staff will never call or message asking for this code.
      </p>
    </div>

    <p style="font-size: 13px; color: #64748b; margin: 0 0 20px 0;">
      If you did not initiate this authentication request, you can safely ignore this email; no access has been granted.
    </p>

    <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 24px 0;">

    <div style="font-size: 11px; color: #64748b; text-align: center; line-height: 1.5;">
      Nexisure Vehicle Insurance &bull; Enterprise Risk & Underwriting Platform<br>
      Automated Security Notification &bull; Delivered directly to inbox
    </div>
  </div>
</body>
</html>"""

        try:
            send_mail(
                subject=subject,
                message=message,
                html_message=html_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'security@nexisure.internal'),
                recipient_list=[normalized_email],
                fail_silently=False,
            )
        except Exception as e:
            return False, f"Failed to deliver verification email: {str(e)}", None

        return True, "A 6-digit verification code has been dispatched to your email address. Please check your inbox.", code

    @classmethod
    def verify_otp(cls, email: str, code: str) -> Tuple[bool, str, Optional[User]]:
        """
        Verifies the candidate OTP against active, non-expired tokens.
        Returns: (success, message, authenticated_user)
        """
        normalized_email = DataNormalizer.normalize_email(email)
        cleaned_code = code.strip() if code else ""

        if not normalized_email or not cleaned_code:
            return False, "Email and 6-digit code are required.", None

        # Look up the latest active token
        now = timezone.now()
        token = EmailOtpToken.objects.filter(
            email=normalized_email,
            is_used=False,
            expires_at__gte=now,
        ).order_by('-created_at').first()

        if not token:
            return False, "No valid, unexpired OTP found. Please request a new code.", None

        # Guardrail against brute-force replay
        if token.attempts_count >= cls.MAX_VERIFICATION_ATTEMPTS:
            token.is_used = True
            token.save()
            return False, "Maximum verification attempts exceeded. Please request a new code.", None

        # Increment attempt counter
        token.attempts_count += 1
        token.save()

        expected_hash = cls._hash_otp(normalized_email, cleaned_code)
        if not secrets.compare_digest(token.otp_hash, expected_hash):
            remaining = cls.MAX_VERIFICATION_ATTEMPTS - token.attempts_count
            return False, f"Invalid verification code. {remaining} attempt(s) remaining.", None

        # Code is valid - mark used
        token.is_used = True
        token.save()

        # Retrieve or create authenticated user
        user = token.user or User.objects.filter(email=normalized_email).first()
        if not user:
            # First-time OTP registration for new customer
            username_part = normalized_email.split('@')[0]
            user = User.objects.create_user(
                username=f"{username_part}_{secrets.token_hex(3)}",
                email=normalized_email,
                role='CUSTOMER',
                email_verified=True,
            )
            token.user = user
            token.save()
        else:
            user.email_verified = True
            user.save(update_fields=['email_verified'])

        return True, "One-Time Passcode verified successfully.", user
