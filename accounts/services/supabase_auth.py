import logging
from typing import Optional, Dict, Any
from django.conf import settings
from accounts.models import User, UserRole
from accounts.services.otp_service import OtpService

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None


class SupabaseAuthService:
    """
    Manages identity synchronization and authentication with Supabase Auth (GoTrue).
    Provides seamless dual-mode operation:
    - Calls live Supabase Auth API when SUPABASE_URL and SUPABASE_ANON_KEY are valid.
    - Bridges to local OtpService when running offline or in local CI environments.
    """

    @classmethod
    def get_client(cls) -> Optional[Any]:
        """Instantiates Supabase Python Client if credentials are provided."""
        url = getattr(settings, 'SUPABASE_URL', '').strip()
        key = getattr(settings, 'SUPABASE_ANON_KEY', '').strip()

        if not url or not key or 'placeholder' in url:
            return None

        if create_client is None:
            logger.warning("Supabase Python SDK not installed.")
            return None

        try:
            return create_client(url, key)
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None

    @classmethod
    def is_supabase_enabled(cls) -> bool:
        return cls.get_client() is not None

    @classmethod
    def send_otp(cls, email: str) -> Dict[str, Any]:
        """
        Sends an email OTP via Supabase Auth or falls back to local OtpService.
        """
        from core.services import DataNormalizer
        normalized_email = DataNormalizer.normalize_email(email)
        if not normalized_email:
            return {
                "success": False,
                "provider": "validation",
                "message": "Please enter a valid email address.",
            }

        client = cls.get_client()
        if client:
            try:
                # Calls Supabase native sign_in_with_otp with passwordless email
                res = client.auth.sign_in_with_otp({"email": normalized_email})
                return {
                    "success": True,
                    "provider": "supabase",
                    "data": res,
                    "message": "A 6-digit verification code has been dispatched to your email address by Supabase. Please check your inbox (and spam folder).",
                }
            except Exception as e:
                err_str = str(e)
                logger.error(f"Supabase Auth OTP dispatch failed: {err_str}")
                status = getattr(e, 'status', None)
                if status == 429 or "rate limit" in err_str.lower():
                    return {
                        "success": False,
                        "provider": "supabase",
                        "message": "For security purposes, you can only request a verification code once every 60 seconds. Please wait.",
                    }
                elif "invalid format" in err_str.lower():
                    return {
                        "success": False,
                        "provider": "supabase",
                        "message": "Unable to send verification code. Please check your email address format.",
                    }
                return {
                    "success": False,
                    "provider": "supabase",
                    "message": "Authentication service was unable to send your verification code. Please try again shortly.",
                }

        # Local fallback execution for offline testing or unconfigured Supabase
        success, message, _ = OtpService.request_otp(normalized_email)
        return {
            "success": success,
            "provider": "local_django",
            "message": message,
        }

    @classmethod
    def verify_otp(cls, email: str, code: str) -> Dict[str, Any]:
        """
        Verifies 6-digit OTP with Supabase Auth or local OtpService.
        """
        from core.services import DataNormalizer
        normalized_email = DataNormalizer.normalize_email(email)
        cleaned_code = str(code).strip() if code else ""

        if not normalized_email:
            return {
                "success": False,
                "provider": "validation",
                "message": "Email address is required.",
                "user": None,
            }

        # Security check: OTP must be exactly 6 numeric digits
        if not cleaned_code or not cleaned_code.isdigit() or len(cleaned_code) != 6:
            return {
                "success": False,
                "provider": "validation",
                "message": "Please enter a valid 6-digit verification passcode.",
                "user": None,
            }

        client = cls.get_client()
        if client:
            try:
                # Direct Supabase email OTP verification (type: 'email')
                res = client.auth.verify_otp({
                    "email": normalized_email,
                    "token": cleaned_code,
                    "type": "email"
                })
                if res and res.user:
                    user = cls.sync_supabase_user(res.user)
                    session = getattr(res, 'session', None)
                    return {
                        "success": True,
                        "provider": "supabase",
                        "user": user,
                        "session": session,
                        "access_token": getattr(session, 'access_token', None) if session else None,
                        "refresh_token": getattr(session, 'refresh_token', None) if session else None,
                        "message": "Verification successful.",
                    }
                return {
                    "success": False,
                    "provider": "supabase",
                    "user": None,
                    "message": "Authentication service did not return a valid user profile.",
                }
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Supabase verify_otp failed: {err_str}")
                status = getattr(e, 'status', None)
                if status == 429 or "rate limit" in err_str.lower():
                    msg = "Too many verification attempts. Please wait a few minutes before trying again."
                elif "expired" in err_str.lower() or "invalid" in err_str.lower() or status == 400:
                    msg = "Invalid or expired verification passcode. Please check the code or request a new one."
                else:
                    msg = "Authentication service verification failed. Please try again."

                return {
                    "success": False,
                    "provider": "supabase",
                    "user": None,
                    "message": msg,
                }

        # Local fallback verification for offline testing or unconfigured Supabase
        success, message, user = OtpService.verify_otp(normalized_email, cleaned_code)
        return {
            "success": success,
            "provider": "local_django",
            "message": message,
            "user": user,
        }

    @classmethod
    def sync_supabase_user(cls, supabase_user: Any, role: str = 'CUSTOMER') -> User:
        """
        Maps a verified Supabase Auth User object to a Django accounts.User record.
        Enforces strict role governance:
        - Never downgrades existing STAFF/ADMINISTRATOR roles to CUSTOMER.
        - Preserves existing Django roles as the single source of truth.
        - First-time self-authenticating users default to CUSTOMER.
        - Privileged roles (UNDERWRITER, CLAIMS_HANDLER, ADMINISTRATOR) must be provisioned in Django.
        """
        import secrets
        uid = str(getattr(supabase_user, 'id', ''))
        email = getattr(supabase_user, 'email', '')

        # Look up existing user by email
        user = User.objects.filter(email=email).first()

        if user:
            # Existing user: PRESERVE existing role (Django is authority)
            # Never downgrade privileged roles based on Supabase metadata
            fields_to_update = []
            if not user.supabase_uid and uid:
                user.supabase_uid = uid
                fields_to_update.append('supabase_uid')
            if not user.email_verified:
                user.email_verified = True
                fields_to_update.append('email_verified')
            if fields_to_update:
                user.save(update_fields=fields_to_update)
        else:
            # New user: Always default to CUSTOMER for self-authentication
            # Never trust arbitrary role claims from untrusted external payloads
            username_base = email.split('@')[0] if email else f"user_{secrets.token_hex(4)}"
            user = User.objects.create(
                username=username_base,
                email=email,
                role=UserRole.USER,
                supabase_uid=uid,
                email_verified=True,
                is_staff=False,
                is_superuser=False,
            )

        if user.is_customer and not hasattr(user, 'customer_profile'):
            from customers.models import CustomerProfile
            CustomerProfile.objects.get_or_create(
                user=user,
                defaults={'customer_code': f"CUST-{secrets.token_hex(4).upper()}"}
            )

        return user
