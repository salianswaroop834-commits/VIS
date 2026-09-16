from decimal import Decimal
from typing import Dict, Any, Optional
from quotations.models import CoveragePlan, CoveragePlanCode
from customers.models import CustomerProfile
from vehicles.models import Vehicle
from recommendations.models import CoverageRecommendation
from ml.inference.predictor import InsurancePredictor
from quotations.services.quotation_service import QuotationService


class RecommendationService:
    """
    Responsible AI Coverage Recommendation Engine.
    Combines rule-based actuarial policies with ML risk scoring
    to provide explainable, customer-centric insurance plan guidance.
    """

    @classmethod
    def generate_recommendation(
        cls,
        vehicle_age: int,
        vehicle_value: float,
        usage_type: str = 'PERSONAL',
        driver_age: int = 35,
        annual_mileage: int = 12000,
        customer: Optional[CustomerProfile] = None,
        vehicle: Optional[Vehicle] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes ML risk indicators with vehicle characteristics
        to generate an explainable coverage recommendation.
        """
        QuotationService.seed_default_plans()

        # Run ML risk prediction
        risk_profile = InsurancePredictor.predict_risk({
            'vehicle_age': vehicle_age,
            'vehicle_value': vehicle_value,
            'usage_type': usage_type,
            'driver_age': driver_age,
            'annual_mileage': annual_mileage,
        }, record_log=False)

        # Actuarial Rule Decision Trees & Supporting Factors
        supporting_factors = [
            f"Vehicle Age: {vehicle_age} years",
            f"Insured Declared Value (IDV): ₹{vehicle_value:,.0f}",
            f"Duty Cycle / Usage: {usage_type.title()}",
            f"Estimated Claim Risk Tier: {risk_profile.get('risk_tier', 'LOW')}",
        ]

        if vehicle_age <= 3 or vehicle_value >= 1500000.0:
            primary_code = CoveragePlanCode.ZERO_DEP_PREMIUM
            alt_code = CoveragePlanCode.COMPREHENSIVE
            confidence = 94.50
            rationale = (
                f"For a newer or premium vehicle ({vehicle_age} yrs old, ₹{vehicle_value:,.0f} IDV), "
                "Zero Depreciation Comprehensive is optimal. It prevents out-of-pocket deductions on "
                "costly fiber glass, paint, and electronic sensor replacements following collision incidents."
            )
            assumptions = (
                "Assumes manufacturer genuine replacement parts are preferred and vehicle is in regular daily use."
            )
        elif 4 <= vehicle_age <= 8:
            primary_code = CoveragePlanCode.COMPREHENSIVE
            alt_code = CoveragePlanCode.ZERO_DEP_PREMIUM if vehicle_value >= 800000.0 else CoveragePlanCode.THIRD_PARTY
            confidence = 88.00
            rationale = (
                f"For a mid-aged vehicle ({vehicle_age} yrs old, ₹{vehicle_value:,.0f} IDV), standard Comprehensive "
                "coverage strikes the ideal equilibrium between affordable annual premiums and robust Own Damage "
                "+ Third-Party liability indemnity."
            )
            assumptions = (
                "Assumes vehicle is driven under standard personal or commute conditions with moderate annual mileage."
            )
        else:
            primary_code = CoveragePlanCode.THIRD_PARTY if vehicle_value < 300000.0 else CoveragePlanCode.COMPREHENSIVE
            alt_code = CoveragePlanCode.THIRD_PARTY
            confidence = 82.50
            rationale = (
                f"For an older vehicle ({vehicle_age} yrs old, ₹{vehicle_value:,.0f} IDV), depreciated asset valuation "
                "diminishes total loss indemnity. Third-Party liability fulfills legal compliance at the lowest cost, "
                "or Comprehensive if you still prefer partial collision coverage."
            )
            assumptions = (
                "Assumes asset replacement cost is low and customer prioritizes cost efficiency over collision payout."
            )

        primary_plan = CoveragePlan.objects.filter(plan_code=primary_code).first()
        alt_plan = CoveragePlan.objects.filter(plan_code=alt_code).first()

        # Deductible advice based on risk
        recommended_deductible = risk_profile['recommended_deductible']

        rec_obj = None
        if customer and vehicle and primary_plan:
            rec_obj = CoverageRecommendation.objects.create(
                customer=customer,
                vehicle=vehicle,
                recommended_plan=primary_plan,
                alternative_plan=alt_plan,
                confidence_score=Decimal(str(confidence)),
                rationale=rationale,
                assumptions=assumptions,
            )

        return {
            'primary_plan': primary_plan,
            'alternative_plan': alt_plan,
            'primary_code': primary_code,
            'alternative_code': alt_code,
            'confidence_score': confidence,
            'rationale': rationale,
            'assumptions': assumptions,
            'supporting_factors': supporting_factors,
            'recommended_deductible': recommended_deductible,
            'currency_symbol': '₹',
            'decision_support_only': True,
            'risk_profile': risk_profile,
            'recommendation_instance': rec_obj,
            'disclaimer': (
                "EDUCATIONAL GUIDANCE NOTICE: This coverage recommendation is generated "
                "as an explainable algorithmic decision-support aid. It does NOT constitute legally "
                "binding financial or insurance policy advice."
            )
        }
