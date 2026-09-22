import uuid
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.db import transaction
from apps.quotations.models import CoveragePlan, CoveragePlanCode, CoverageFeature, QuotationDraft
from apps.customers.models import CustomerProfile
from apps.vehicles.models import Vehicle
from apps.staff.models import StaffProfile
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService
from core.services import ServiceValidationError, NotificationService



class QuotationService:
    """
    Manages coverage plan definitions, simulated pricing formulas,
    multi-year discounts, and quotation draft lifecycles.
    """

    @classmethod
    def seed_default_plans(cls):
        """Ensures the 3 core vehicle insurance plans and their features exist in the database."""
        plans_data = [
            {
                'plan_code': CoveragePlanCode.THIRD_PARTY,
                'name': 'Third-Party Liability Only',
                'tagline': 'Statutory legal protection covering injury and third-party property damage.',
                'description': 'Baseline statutory protection covering third-party bodily injury and property liabilities. Excludes own vehicle collision damage.',
                'base_rate_percentage': Decimal('1.250'),
                'standard_deductible': Decimal('500.00'),
                'includes_own_damage': False,
                'includes_third_party': True,
                'includes_roadside_assistance': False,
                'includes_engine_protection': False,
            },
            {
                'plan_code': CoveragePlanCode.COMPREHENSIVE,
                'name': 'Comprehensive / Full Insurance',
                'tagline': 'Full-spectrum protection covering own vehicle damage, theft, collision, and third-party liabilities.',
                'description': 'Complete peace-of-mind coverage protecting against own damage, collision, theft, natural hazards, plus 24/7 roadside emergency dispatch.',
                'base_rate_percentage': Decimal('2.850'),
                'standard_deductible': Decimal('1000.00'),
                'includes_own_damage': True,
                'includes_third_party': True,
                'includes_roadside_assistance': True,
                'includes_engine_protection': False,
            },
            {
                'plan_code': CoveragePlanCode.ZERO_DEP_PREMIUM,
                'name': 'Zero Depreciation Comprehensive',
                'tagline': 'Maximum tier coverage with 0% depreciation deductions on vehicle repair parts.',
                'description': 'Elite comprehensive protection with a zero-depreciation waiver on parts, engine water-ingress protection, and priority claim processing.',
                'base_rate_percentage': Decimal('3.500'),
                'standard_deductible': Decimal('1500.00'),
                'includes_own_damage': True,
                'includes_third_party': True,
                'includes_roadside_assistance': True,
                'includes_engine_protection': True,
            }
        ]

        created_or_updated = []
        for p in plans_data:
            obj, _ = CoveragePlan.objects.update_or_create(
                plan_code=p['plan_code'],
                defaults=p,
            )
            created_or_updated.append(obj)

        # Seed standard and rider features for plans
        features_map = {
            CoveragePlanCode.THIRD_PARTY: [
                ('TP_BODILY_INJURY', 'Third-Party Bodily Injury Liability', 'Statutory mandatory cover for bodily injuries to third parties', True, Decimal('0.00')),
                ('TP_PROPERTY_DAMAGE', 'Third-Party Property Damage', 'Protection against liability for damages caused to third-party property', True, Decimal('0.00')),
                ('LEGAL_DEFENSE', 'Legal Defense Assistance', 'Legal counsel representation support for statutory third-party dispute claims', True, Decimal('0.00')),
            ],
            CoveragePlanCode.COMPREHENSIVE: [
                ('OWN_DAMAGE_COLLISION', 'Own Damage Collision Protection', 'Full repair coverage for damage sustained in road vehicular collisions', True, Decimal('0.00')),
                ('THEFT_AND_FIRE', 'Theft & Fire Total Protection', 'Reimbursement up to Insured Declared Value in the event of theft or fire', True, Decimal('0.00')),
                ('NATURAL_DISASTERS', 'Natural Disaster & Flood Cover', 'Covers environmental flood, lightning, storm, and earthquake damages', True, Decimal('0.00')),
                ('ROADSIDE_ASSISTANCE', '24/7 Roadside Emergency Assistance', 'Towing, battery jumpstart, flat-tire change, and fuel dispatch services', True, Decimal('0.00')),
                ('ZERO_DEP_ADDON', 'Zero Depreciation Add-on Rider', 'Eliminates depreciation deduction on replacement parts', False, Decimal('45.00')),
            ],
            CoveragePlanCode.ZERO_DEP_PREMIUM: [
                ('ZERO_DEP_INCLUDED', 'Zero Depreciation Guarantee', 'Zero deduction on all repairs and OEM parts replacement across the policy term', True, Decimal('0.00')),
                ('ENGINE_PROTECTION', 'Engine & Electronics Water-Ingress Protection', 'Specialized hydro-lock and electronic component safeguard against water damage', True, Decimal('0.00')),
                ('KEY_REPLACEMENT', 'Lost Key & Lockset Replacement', 'Reimbursement for high-security key replacements and reprogramming costs', True, Decimal('0.00')),
                ('PRIORITY_CONCIERGE', 'Priority Claims Concierge', 'Dedicated senior claims handler routing with 24-hour turnaround target', True, Decimal('0.00')),
                ('CONSUMABLES_COVER', 'Consumables Allowance', 'Full coverage for oils, lubricants, nuts, bolts, and AC gas during repair', True, Decimal('0.00')),
            ]
        }
        for plan_obj in created_or_updated:
            f_list = features_map.get(plan_obj.plan_code, [])
            for code, title, desc, is_std, add_on in f_list:
                CoverageFeature.objects.update_or_create(
                    plan=plan_obj,
                    feature_code=code,
                    defaults={
                        'title': title,
                        'description': desc,
                        'is_standard': is_std,
                        'add_on_premium': add_on,
                    }
                )

        return created_or_updated

    @classmethod
    def calculate_simulated_premium(
        cls,
        vehicle_value: Decimal,
        plan_code: str,
        duration_years: int = 1,
        selected_feature_ids: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Simulated premium calculation engine in INR (₹).
        Applies base rate percentage, multi-year term discounts, and optional rider premiums.
        """
        if vehicle_value <= Decimal('0'):
            raise ServiceValidationError("Vehicle value must be greater than zero.")

        if duration_years not in (1, 2, 3):
            raise ServiceValidationError("Policy duration must be 1, 2, or 3 years.")

        # Ensure plans are loaded
        cls.seed_default_plans()
        plan = CoveragePlan.objects.filter(plan_code=plan_code).first()
        if not plan:
            raise ServiceValidationError(f"Invalid coverage plan code: '{plan_code}'.")

        # Multi-year discounts: 1yr = 0%, 2yr = 5%, 3yr = 10%
        discount_rate = Decimal('0.00')
        if duration_years == 2:
            discount_rate = Decimal('0.05')
        elif duration_years == 3:
            discount_rate = Decimal('0.10')

        annual_base = (vehicle_value * plan.base_rate_percentage) / Decimal('100.00')
        total_undiscounted = annual_base * Decimal(duration_years)
        discount_amount = total_undiscounted * discount_rate
        base_premium = round(total_undiscounted - discount_amount, 2)

        # Optional rider calculation
        addon_premium = Decimal('0.00')
        valid_features = []
        if selected_feature_ids:
            # Match by ID or feature_code for flexibility
            str_ids = [str(fid) for fid in selected_feature_ids]
            features = plan.features.filter(is_active=True)
            for feat in features:
                if str(feat.id) in str_ids or feat.feature_code in str_ids:
                    valid_features.append(feat)
                    if not feat.is_standard:
                        addon_premium += feat.add_on_premium * Decimal(duration_years)

        final_premium = round(base_premium + addon_premium, 2)

        return {
            'plan': plan,
            'vehicle_value': vehicle_value,
            'duration_years': duration_years,
            'base_rate_percentage': plan.base_rate_percentage,
            'standard_deductible': plan.standard_deductible,
            'discount_percentage': discount_rate * Decimal('100'),
            'discount_amount': round(discount_amount, 2),
            'base_premium': base_premium,
            'addon_premium': round(addon_premium, 2),
            'calculated_premium': final_premium,
            'selected_features': valid_features,
        }

    @classmethod
    @transaction.atomic
    def create_quotation_draft(
        cls,
        vehicle_value: Decimal,
        plan_code: str,
        duration_years: int = 1,
        customer: Optional[CustomerProfile] = None,
        vehicle: Optional[Vehicle] = None,
        underwriter: Optional[StaffProfile] = None,
        selected_feature_ids: Optional[List[Any]] = None,
        actor: Optional[Any] = None,
    ) -> QuotationDraft:
        """
        Calculates rates and persists a unique QuotationDraft.
        Valid for 30 days. Logs QUOTATION_CREATED audit event.
        """
        # Server-side validation: if customer and vehicle are provided, ensure ownership
        if vehicle and customer and vehicle.customer != customer:
            raise ServiceValidationError("Unauthorized: Vehicle does not belong to the authenticated customer.")

        calc = cls.calculate_simulated_premium(
            vehicle_value=vehicle_value,
            plan_code=plan_code,
            duration_years=duration_years,
            selected_feature_ids=selected_feature_ids,
        )

        year = timezone.now().year
        quotation_num = f"QTE-{year}-{uuid.uuid4().hex[:8].upper()}"
        valid_until = timezone.now() + timedelta(days=30)

        draft = QuotationDraft.objects.create(
            quotation_number=quotation_num,
            customer=customer,
            vehicle=vehicle,
            coverage_plan=calc['plan'],
            underwriter=underwriter,
            vehicle_value=vehicle_value,
            duration_years=duration_years,
            base_premium=calc['base_premium'],
            addon_premium=calc['addon_premium'],
            calculated_premium=calc['calculated_premium'],
            deductible_amount=calc['standard_deductible'],
            valid_until=valid_until,
            status=QuotationDraft.QuotationStatus.DRAFT,
        )

        if calc['selected_features']:
            draft.selected_features.set(calc['selected_features'])

        AuditService.log(
            action=AuditAction.QUOTATION_CREATED,
            target_entity='QuotationDraft',
            target_id=str(draft.pk),
            actor=actor or (customer.user if customer else None),
            details={
                'quotation_number': draft.quotation_number,
                'plan_code': plan_code,
                'vehicle_value': float(vehicle_value),
                'duration_years': duration_years,
                'base_premium': float(draft.base_premium),
                'addon_premium': float(draft.addon_premium),
                'calculated_premium': float(draft.calculated_premium),
            }
        )

        if customer and customer.user:
            NotificationService.notify(
                recipient=customer.user,
                title="Quotation Generated",
                message=f"Quotation {draft.quotation_number} ({calc['plan'].name}) has been generated for ₹{draft.calculated_premium:,.2f}. Valid for 30 days.",
                notification_type='GENERAL',
                action_url=f"/quotations/{draft.id}/",
            )

        return draft


    @classmethod
    def accept_quotation(
        cls,
        quotation: QuotationDraft,
        actor: Any,
    ) -> QuotationDraft:
        """
        Accepts a quotation draft.
        Enforces customer ownership, expiry check, and lifecycle state.
        Transitions: DRAFT -> ACCEPTED
        """
        # Rule: Only DRAFT quotations can be accepted
        if quotation.status == QuotationDraft.QuotationStatus.ACCEPTED:
            raise ServiceValidationError("This quotation has already been accepted.")
        if quotation.status == QuotationDraft.QuotationStatus.CONVERTED:
            raise ServiceValidationError("This quotation has already been converted into an active policy.")
        if quotation.status == QuotationDraft.QuotationStatus.EXPIRED:
            raise ServiceValidationError("This quotation has expired. Please calculate a new quote.")
        if quotation.status != QuotationDraft.QuotationStatus.DRAFT:
            raise ServiceValidationError(f"Cannot accept quotation with status '{quotation.status}'.")

        # Rule: Expiry check
        if quotation.valid_until < timezone.now():
            quotation.status = QuotationDraft.QuotationStatus.EXPIRED
            quotation.save(update_fields=['status', 'updated_at'])
            raise ServiceValidationError("This quotation has expired. Please calculate a new quote.")

        # Rule: Customer ownership check
        if quotation.customer and actor:
            customer_profile = getattr(actor, 'customer_profile', None)
            is_admin = getattr(actor, 'is_administrator', False) or getattr(actor, 'is_superuser', False)
            if customer_profile and quotation.customer != customer_profile and not is_admin:
                raise ServiceValidationError("Unauthorized: You may only accept quotations issued to your account.")

        with transaction.atomic():
            # If quotation had no customer yet, attach actor's profile
            if not quotation.customer and actor:
                cust_prof = getattr(actor, 'customer_profile', None)
                if cust_prof:
                    quotation.customer = cust_prof

            quotation.status = QuotationDraft.QuotationStatus.ACCEPTED
            quotation.save(update_fields=['status', 'customer', 'updated_at'])

            AuditService.log(
                action=AuditAction.QUOTATION_ACCEPTED,
                target_entity='QuotationDraft',
                target_id=str(quotation.pk),
                actor=actor if getattr(actor, 'is_authenticated', False) else None,
                details={
                    'quotation_number': quotation.quotation_number,
                    'status': quotation.status,
                    'premium_amount': float(quotation.calculated_premium),
                }
            )

        return quotation

