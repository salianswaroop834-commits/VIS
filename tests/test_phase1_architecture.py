import pytest
from django.conf import settings
from django.apps import apps
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.services import DataNormalizer

@pytest.mark.django_db
class TestPhase1Architecture:
    """
    Automated verification of Phase 1 architectural requirements:
    1. Clean modular app registry
    2. Custom User model with UUID primary key
    3. Input normalization utilities
    4. HTTP 200 responses across public, auth, and preview portal endpoints
    5. Health check and robots.txt SEO directives
    6. Educational disclaimers in rendered output
    """

    def test_installed_apps_registered(self):
        expected_apps = [
            'core',
            'accounts',
            'customers',
            'staff',
            'vehicles',
            'quotations',
            'policies',
            'claims',
            'service_requests',
            'recommendations',
            'predictions',
            'analytics',
            'audit',
            'payments',
            'rag',
            'chatbot',
        ]
        registered_apps = [app_config.name for app_config in apps.get_app_configs()]
        for app_name in expected_apps:
            assert app_name in registered_apps, f"App '{app_name}' missing from registered apps."

    def test_custom_user_model_active(self):
        User = get_user_model()
        assert settings.AUTH_USER_MODEL == 'accounts.User'
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!',
            role='CUSTOMER',
        )
        assert user.pk is not None
        # Verify primary key is a valid UUID
        assert len(str(user.pk)) == 36
        assert user.is_customer is True
        assert user.is_underwriter is False
        assert user.is_claims_handler is False
        assert user.is_administrator is False

    def test_data_normalizer_rules(self):
        # Registration normalization: Uppercase, strip punctuation & spaces
        assert DataNormalizer.normalize_registration_number(" dl-01-ab 1234 ") == "DL01AB1234"
        assert DataNormalizer.normalize_registration_number("mh 02 cq 9999") == "MH02CQ9999"

        # Email normalization: lowercase and trim
        assert DataNormalizer.normalize_email("  Customer.Name@Domain.COM  ") == "customer.name@domain.com"

        # Phone normalization: keep digits and plus
        assert DataNormalizer.normalize_phone("+1 (555) 019-2834") == "+15550192834"

        # VIN normalization
        assert DataNormalizer.normalize_vin_or_chassis("  1hg-cv1f32na 012984  ") == "1HGCV1F32NA012984"

    @pytest.mark.parametrize('url_name,expected_code', [
        ('home', 200),
        ('about', 200),
        ('coverage', 200),
        ('how-it-works', 200),
        ('faq', 200),
        ('contact', 200),
        ('terms', 200),
        ('privacy', 200),
        ('health-check', 200),
        ('robots-txt', 200),
        ('accounts:login', 200),
        ('accounts:register', 200),
        ('accounts:verify-otp', 200),
        ('quotations:estimator', 200),
        ('quotations:compare', 200),
        ('chatbot:chat', 200),
        ('analytics:dashboard', 200),
    ])
    def test_public_and_portal_endpoints_return_200(self, client, url_name, expected_code):
        url = reverse(url_name)
        response = client.get(url)
        assert response.status_code == expected_code, f"URL {url} returned status {response.status_code}"

    def test_health_check_json_structure(self, client):
        response = client.get(reverse('health-check'))
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['database'] == 'connected'
        assert data['service'] == 'nexisure-vehicle-insurance'

    def test_robots_txt_disallows_private_portals(self, client):
        response = client.get(reverse('robots-txt'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "Disallow: /customer/" in content
        assert "Disallow: /staff/" in content
        assert "Disallow: /django-admin/" in content

    def test_prototype_disclaimer_rendered(self, client):
        response = client.get(reverse('home'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "CAPSTONE PROTOTYPE" in content
        assert "Nexisure" in content
