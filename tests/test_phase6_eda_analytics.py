import pytest
from django.urls import reverse
from analytics.services.eda_service import EdaService


@pytest.mark.django_db
class TestPhase6EdaAndAnalytics:

    def test_synthetic_dataset_integrity(self):
        df = EdaService.load_dataset()
        assert len(df) >= 1000, f"Expected at least 1,000 records, got {len(df)}"

        # Check required columns
        required_cols = [
            'vehicle_age', 'vehicle_type', 'fuel_type', 'usage_type',
            'vehicle_value', 'driver_age', 'annual_mileage', 'credit_score_tier',
            'previous_claims_count', 'coverage_tier', 'deductible_amount',
            'annual_premium', 'claim_filed', 'claim_amount'
        ]
        for col in required_cols:
            assert col in df.columns, f"Column '{col}' missing from synthetic dataset."
            assert df[col].isnull().sum() == 0, f"Column '{col}' has null values."

        # Statistical sanity checks
        claim_rate = df['claim_filed'].mean()
        assert 0.08 <= claim_rate <= 0.25, f"Claim rate {claim_rate:.2%} is outside realistic 8-25% bounds."

        positive_claims = df[df['claim_filed'] == 1]
        assert len(positive_claims) > 0
        assert (positive_claims['claim_amount'] > 0).all()

        # Severity should not exceed vehicle declared value
        exceeding = df[df['claim_amount'] > df['vehicle_value']]
        assert len(exceeding) == 0, "Claim amounts found exceeding vehicle declared value."

    def test_eda_service_kpis(self):
        df = EdaService.load_dataset()
        kpis = EdaService.get_kpis(df)

        assert kpis['total_policies'] == len(df)
        assert kpis['total_premium'] > 0
        assert kpis['claims_filed'] > 0
        assert 5.0 <= kpis['claim_frequency_pct'] <= 25.0
        assert kpis['total_incurred_loss'] > 0
        assert kpis['loss_ratio_pct'] > 0
        assert kpis['avg_claim_severity'] > 0
        assert kpis['avg_vehicle_idv'] > 0
        assert 'fraud_claims_count' in kpis
        assert 'fraud_rate_pct' in kpis
        assert 'avg_settlement_days' in kpis

    def test_plotly_chart_generation(self):
        df = EdaService.load_dataset()

        chart1 = EdaService.generate_chart_vehicle_portfolio(df)
        assert 'plotly-graph-div' in chart1 or 'plotly' in chart1.lower()

        chart2 = EdaService.generate_chart_loss_ratio_by_tier(df)
        assert 'plotly-graph-div' in chart2 or 'plotly' in chart2.lower()

        chart3 = EdaService.generate_chart_claim_severity_distribution(df)
        assert 'plotly-graph-div' in chart3 or 'plotly' in chart3.lower()

        chart4 = EdaService.generate_chart_risk_by_usage_and_age(df)
        assert 'plotly-graph-div' in chart4 or 'plotly' in chart4.lower()

        chart5 = EdaService.generate_chart_geographic_risk(df)
        assert 'plotly-graph-div' in chart5 or 'plotly' in chart5.lower()

        chart6 = EdaService.generate_chart_security_and_parking(df)
        assert 'plotly-graph-div' in chart6 or 'plotly' in chart6.lower()

    def test_analytics_dashboard_view_renders_200(self, client):
        url = reverse('analytics:dashboard')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Portfolio Analytics' in content
        assert 'Gross Premium Written' in content
        assert 'Net Loss Ratio' in content
        assert 'chart-container' in content
