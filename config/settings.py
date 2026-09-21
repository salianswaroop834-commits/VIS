"""
Django settings for Nexisure Vehicle Insurance Platform.
Designed for high security, Supabase PostgreSQL / pgvector compatibility,
and full-stack modularity.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Automated test execution flag
TESTING = 'pytest' in sys.modules or (len(sys.argv) > 1 and sys.argv[1] == 'test')

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-nexisure-fallback-secret-key-2026')

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0,.localhost,customer.localhost,staff.localhost,admin.localhost').split(',') if h.strip()]
for host in ('.localhost', 'customer.localhost', 'staff.localhost', 'admin.localhost', 'testserver'):
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

CSRF_TRUSTED_ORIGINS = [
    orig.strip() for orig in os.getenv(
        'DJANGO_CSRF_TRUSTED_ORIGINS',
        'http://localhost:8000,http://127.0.0.1:8000,http://0.0.0.0:8000,http://*.localhost:8000,http://customer.localhost:8000,http://staff.localhost:8000,http://admin.localhost:8000'
    ).split(',') if orig.strip()
]
for origin in (
    'http://*.localhost:8000',
    'http://customer.localhost:8000',
    'http://staff.localhost:8000',
    'http://admin.localhost:8000',
):
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
]

DOMAIN_APPS = [
    'core.apps.CoreConfig',
    'apps.accounts.apps.AccountsConfig',
    'apps.customers.apps.CustomersConfig',
    'apps.staff.apps.StaffConfig',
    'apps.vehicles.apps.VehiclesConfig',
    'apps.quotations.apps.QuotationsConfig',
    'apps.policies.apps.PoliciesConfig',
    'apps.claims.apps.ClaimsConfig',
    'apps.service_requests.apps.ServiceRequestsConfig',
    'apps.recommendations.apps.RecommendationsConfig',
    'apps.predictions.apps.PredictionsConfig',
    'apps.analytics.apps.AnalyticsConfig',
    'apps.audit.apps.AuditConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.rag.apps.RagConfig',
    'apps.chatbot.apps.ChatbotConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + DOMAIN_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.platform_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database Configuration
# Primary: Supabase PostgreSQL (via DATABASE_URL).
# Fallback: SQLite for local offline testing and CI workflows.
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Custom User Model definition
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/customer/dashboard/'
LOGOUT_REDIRECT_URL = '/'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (User uploads, documents)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# Platform Branding & Prototype Disclaimers
PLATFORM_NAME = 'Nexisure Vehicle Insurance'
PROTOTYPE_DISCLAIMER = (
    'Educational prototype platform: All data is synthetic, payments are simulated, '
    'and ML/AI outputs are responsible decision-support aids rather than binding insurance advice.'
)

# Supabase Credentials
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

# RapidAPI Integrations (PAN & Vehicle Lookup)
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY', 'mock_key')
RAPIDAPI_PAN_KEY = os.getenv('RAPIDAPI_PAN_KEY', '')
RAPIDAPI_VEHICLE_KEY = os.getenv('RAPIDAPI_VEHICLE_KEY', RAPIDAPI_KEY)
RAPIDAPI_PAN_HOST = os.getenv('RAPIDAPI_PAN_HOST', 'pan-verification.p.rapidapi.com')
RAPIDAPI_VEHICLE_HOST = os.getenv('RAPIDAPI_VEHICLE_HOST', 'vehicle-rc-information-v2.p.rapidapi.com')

# Firebase Phone Verification & 2FA
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', 'nexisure-dev')
FIREBASE_CLIENT_EMAIL = os.getenv('FIREBASE_CLIENT_EMAIL', '')
FIREBASE_PRIVATE_KEY = os.getenv('FIREBASE_PRIVATE_KEY', '')

# MLOps & MLflow Tracking
MLFLOW_TRACKING_URI = os.getenv('MLFLOW_TRACKING_URI', str(BASE_DIR / 'mlruns'))
MLFLOW_EXPERIMENT_NAME = os.getenv('MLFLOW_EXPERIMENT_NAME', 'nexisure_claim_prediction')

# Email Delivery Configuration (SMTP for production or console for local dev)
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.smtp.EmailBackend' if os.getenv('EMAIL_HOST_USER') else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 't')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Nexisure Security <no-reply@nexisure.internal>')

# Production Static Storage (Compressed Manifest via Whitenoise)
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Production Security Hardening
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 't')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

