from django.db import models
from core.models import AuditableModel
from customers.models import CustomerProfile
from vehicles.models import Vehicle
from quotations.models import CoveragePlan


class CoverageRecommendation(AuditableModel):
    """
    Transparent, explainable vehicle insurance coverage recommendation.
    Enforces responsible AI standards:
    - Provides plain-language rationale
    - Clarifies underlying assumptions
    - Highlights alternative options
    - Marked strictly as educational decision-support guidance
    """
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recommendations',
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recommendations',
    )
    recommended_plan = models.ForeignKey(
        CoveragePlan,
        on_delete=models.PROTECT,
        related_name='primary_recommendations',
    )
    alternative_plan = models.ForeignKey(
        CoveragePlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alternative_recommendations',
    )
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Suitability score (0.00 to 100.00)',
    )
    rationale = models.TextField(help_text='Why this coverage is suited to the vehicle age, valuation, and usage')
    assumptions = models.TextField(help_text='Key assumptions used to produce this recommendation')
    disclaimer = models.TextField(
        default='Educational decision support only. Not guaranteed financial or statutory insurance advice.'
    )

    class Meta:
        verbose_name = 'Coverage Recommendation'
        verbose_name_plural = 'Coverage Recommendations'
        ordering = ['-created_at']

    def __str__(self):
        return f"Recommendation: {self.recommended_plan.name} (Score: {self.confidence_score}%)"
