import os
import pytest
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()
