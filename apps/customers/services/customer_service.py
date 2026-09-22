import uuid
import secrets
from typing import Dict, Any, List, Optional
from django.db.models import Q
from django.db import transaction
from apps.customers.models import CustomerProfile
from apps.accounts.models import User, UserRole
from apps.staff.models import StaffProfile
from core.services import DataNormalizer, ServiceValidationError


class CustomerService:
    """
    Handles customer identity lookups, profile creation, and underwriting search.
    """

    @classmethod
    def search_customers_by_identifier(cls, query: str) -> List[CustomerProfile]:
        """
        Searches customer profiles by customer code, email, or normalized phone number.
        """
        cleaned = query.strip() if query else ""
        if not cleaned:
            return CustomerProfile.objects.select_related('user').all()[:50]

        normalized_phone = DataNormalizer.normalize_phone(cleaned)

        qs = CustomerProfile.objects.filter(
            Q(customer_code__icontains=cleaned) |
            Q(user__email__icontains=cleaned) |
            Q(user__first_name__icontains=cleaned) |
            Q(user__last_name__icontains=cleaned) |
            (Q(user__phone_number__icontains=normalized_phone) if normalized_phone else Q())
        ).select_related('user')

        return qs[:50]

    @classmethod
    @transaction.atomic
    def register_customer_for_underwriting(
        cls,
        data: Dict[str, Any],
        underwriter: Optional[StaffProfile] = None,
    ) -> CustomerProfile:
        """
        Allows an underwriter to register a new customer in the underwriting workflow.
        """
        raw_email = data.get('email', '')
        email = DataNormalizer.normalize_email(raw_email)
        if not email:
            raise ServiceValidationError("Customer email is required.")

        if User.objects.filter(email=email).exists():
            raise ServiceValidationError(f"A user with email '{email}' already exists.")

        first_name = DataNormalizer.normalize_text(data.get('first_name', ''))
        last_name = DataNormalizer.normalize_text(data.get('last_name', ''))
        phone = DataNormalizer.normalize_phone(data.get('phone_number', ''))
        license_num = DataNormalizer.normalize_text(data.get('driving_license_number', ''))

        username = f"{email.split('@')[0]}_{secrets.token_hex(3)}"
        # Set a temporary secure random password
        temp_password = secrets.token_urlsafe(16)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=temp_password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            role=UserRole.CUSTOMER,
            email_verified=True,
        )

        customer_code = f"CUST-{uuid.uuid4().hex[:8].upper()}"
        profile = CustomerProfile.objects.create(
            user=user,
            customer_code=customer_code,
            driving_license_number=license_num,
            address_line=DataNormalizer.normalize_text(data.get('address_line', '')),
            city=DataNormalizer.normalize_text(data.get('city', '')),
            state=DataNormalizer.normalize_text(data.get('state', '')),
            postal_code=DataNormalizer.normalize_text(data.get('postal_code', '')),
            is_identity_verified=True,
        )

        return profile
