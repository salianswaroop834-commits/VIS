import re
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction
from apps.accounts.models import User
from apps.customers.models import CustomerProfile, KYCVerification, KYCStatus
from integrations.rapidapi.pan.client import RapidApiPANProvider
from integrations.rapidapi.exceptions import (
    RapidApiError,
    InvalidPanError,
    PanNotFoundError,
    RateLimitError,
    ProviderUnavailableError,
)
from integrations.firebase.verification import FirebaseVerificationClient
from integrations.firebase.exceptions import (
    FirebaseOtpError,
    InvalidOtpError,
    OtpExpiredError,
    OtpAttemptsExceededError,
)
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService
from core.services import ServiceValidationError, NotificationService


PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')


class PanVerificationService:
    """
    Two-Factor PAN KYC Verification Service.
    Workflow:
    1. Validate format
    2. Query external PAN registry (RapidAPI adapter)
    3. Match provider-linked phone against user's registered account phone
    4. If mismatch -> Reject, audit failure, never expose provider phone
    5. If match -> Create short-lived Firebase OTP challenge
    6. Verify OTP code -> Mark KYC Verified & update CustomerProfile
    """

    @classmethod
    def initiate_pan_verification(
        cls,
        user: User,
        pan_number: str,
        actor_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiates Step 1 of PAN verification: validates PAN, checks phone match,
        and triggers Firebase phone OTP challenge if matched.
        """
        pan = pan_number.strip().upper()
        if not PAN_REGEX.match(pan):
            raise ServiceValidationError("Invalid PAN format. Standard format: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).")

        # Ensure user has a registered phone number
        user_phone = "".join(c for c in (user.phone_number or '') if c.isdigit())
        if not user_phone or len(user_phone) < 10:
            raise ServiceValidationError("You must have a registered mobile number on your profile before verifying PAN.")

        # Rate limiting: max 5 verification attempts per user per hour
        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        recent_attempts = KYCVerification.objects.filter(user=user, created_at__gte=one_hour_ago).count()
        if recent_attempts >= 5:
            raise ServiceValidationError("Verification attempt limit reached. Please wait before trying again.")

        # Check if user already has an active verified PAN
        existing_verified = KYCVerification.objects.filter(
            user=user,
            status=KYCStatus.VERIFIED,
            verification_type='PAN'
        ).first()
        if existing_verified:
            raise ServiceValidationError("Your account already has a verified PAN identity.")

        provider = RapidApiPANProvider()
        try:
            pan_data = provider.verify_pan(pan)
        except PanNotFoundError as e:
            cls._log_kyc_event(user, pan_data={'document_number_masked': pan[:5] + '****' + pan[-1]}, success=False, reason=str(e), ip=actor_ip)
            raise ServiceValidationError(str(e))
        except (RateLimitError, ProviderUnavailableError) as e:
            raise ServiceValidationError(str(e))
        except InvalidPanError as e:
            raise ServiceValidationError(str(e))

        # Check phone match (comparing last 4 digits)
        provider_raw_phone = pan_data.get('raw_provider_phone', '')
        user_phone_last_four = user_phone[-4:]
        provider_phone_last_four = pan_data.get('phone_last_four', '')

        phone_matched = bool(provider_phone_last_four and user_phone_last_four == provider_phone_last_four)

        if not phone_matched:
            # STOP verification, create failed record and audit
            KYCVerification.objects.create(
                user=user,
                verification_type='PAN',
                document_number_masked=pan_data['document_number_masked'],
                provider='RAPIDAPI',
                provider_reference=pan_data.get('provider_reference', ''),
                status=KYCStatus.FAILED,
                name_match=None,
                dob_match=None,
                phone_match=False,
                verified_phone_masked=pan_data.get('verified_phone_masked', ''),
                failure_reason="Phone number linked to PAN in registry does not match registered account phone.",
            )
            cls._log_kyc_event(
                user,
                pan_data=pan_data,
                success=False,
                reason="Phone mismatch with registered account",
                ip=actor_ip,
            )
            # Safe message: never expose the provider's phone number!
            raise ServiceValidationError(
                "Verification failed: The mobile number linked with this PAN in the official registry does not match your registered account mobile number."
            )

        # Phone matched! Create verification record with PHONE_OTP_REQUIRED
        kyc_record = KYCVerification.objects.create(
            user=user,
            verification_type='PAN',
            document_number_masked=pan_data['document_number_masked'],
            provider='RAPIDAPI',
            provider_reference=pan_data.get('provider_reference', ''),
            status=KYCStatus.PHONE_OTP_REQUIRED,
            name_match=True,
            dob_match=True,
            phone_match=True,
            verified_phone_masked=pan_data.get('verified_phone_masked', ''),
        )

        # Trigger Firebase OTP flow
        firebase_client = FirebaseVerificationClient()
        challenge = firebase_client.initiate_phone_otp_challenge(user_phone, str(user.id))

        AuditService.log(
            action=AuditAction.KYC_VERIFICATION_STARTED,
            target_entity='KYCVerification',
            target_id=str(kyc_record.pk),
            actor=user,
            details={
                'pan_masked': pan_data['document_number_masked'],
                'masked_phone': challenge['masked_phone'],
                'status': 'PHONE_OTP_REQUIRED',
            },
            ip_address=actor_ip,
        )

        return {
            'verification_id': str(kyc_record.pk),
            'challenge_id': challenge['challenge_id'],
            'status': 'PHONE_OTP_REQUIRED',
            'masked_pan': pan_data['document_number_masked'],
            'document_number_masked': pan_data['document_number_masked'],
            'registered_name': pan_data.get('full_name', ''),
            'date_of_birth': pan_data.get('date_of_birth', ''),
            'masked_phone': challenge['masked_phone'],
            'verified_phone_masked': challenge['masked_phone'],
            'message': f"PAN details found. Verification OTP sent to {challenge['masked_phone']}.",
        }

    @classmethod
    @transaction.atomic
    def confirm_pan_otp(
        cls,
        user: User,
        verification_id: str,
        challenge_id: str,
        otp_code: str,
        actor_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Step 2: Validates submitted OTP against Firebase challenge and finalizes KYC.
        """
        kyc_record = KYCVerification.objects.filter(
            pk=verification_id,
            user=user,
            status=KYCStatus.PHONE_OTP_REQUIRED,
        ).first()

        if not kyc_record:
            raise ServiceValidationError("No active OTP challenge found for this verification session.")

        firebase_client = FirebaseVerificationClient()
        try:
            firebase_client.verify_otp_challenge(
                challenge_id=challenge_id,
                submitted_otp=otp_code,
                user_id=str(user.id),
            )
        except (InvalidOtpError, OtpExpiredError, OtpAttemptsExceededError, FirebaseOtpError) as e:
            if isinstance(e, OtpAttemptsExceededError):
                kyc_record.status = KYCStatus.FAILED
                kyc_record.failure_reason = str(e)
                kyc_record.save(update_fields=['status', 'failure_reason', 'updated_at'])
            raise ServiceValidationError(str(e))

        # Successfully verified!
        now = timezone.now()
        kyc_record.status = KYCStatus.VERIFIED
        kyc_record.verified_at = now
        kyc_record.save(update_fields=['status', 'verified_at', 'updated_at'])

        # Update CustomerProfile
        customer = getattr(user, 'customer_profile', None)
        if customer:
            customer.is_identity_verified = True
            customer.save(update_fields=['is_identity_verified', 'updated_at'])

        # Update User phone_verified
        user.phone_verified = True
        user.save(update_fields=['phone_verified', 'updated_at'])

        AuditService.log(
            action=AuditAction.KYC_VERIFIED,
            target_entity='KYCVerification',
            target_id=str(kyc_record.pk),
            actor=user,
            details={
                'pan_masked': kyc_record.document_number_masked,
                'verified_phone': kyc_record.verified_phone_masked,
                'verified_at': now.isoformat(),
            },
            ip_address=actor_ip,
        )

        NotificationService.notify(
            recipient=user,
            title="KYC Verification Approved",
            message=f"Your PAN identity ({kyc_record.document_number_masked}) and registered phone number have been successfully verified.",
            notification_type='SECURITY_ALERT',
            action_url='/customer/kyc/',
        )

        return {

            'verification_id': str(kyc_record.pk),
            'status': 'VERIFIED',
            'masked_pan': kyc_record.document_number_masked,
            'is_identity_verified': True,
            'message': "✓ PAN and identity verified successfully.",
        }

    @classmethod
    def _log_kyc_event(cls, user: User, pan_data: Dict[str, Any], success: bool, reason: str, ip: Optional[str] = None):
        AuditService.log(
            action=AuditAction.KYC_FAILED if not success else AuditAction.KYC_VERIFIED,
            target_entity='KYCVerification',
            target_id=str(user.pk),
            actor=user,
            details={
                'pan_masked': pan_data.get('document_number_masked', '****'),
                'is_success': success,
                'reason': reason,
            },
            ip_address=ip,
            is_success=success,
        )
