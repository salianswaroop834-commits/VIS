import os
import re
from abc import ABC, abstractmethod
from typing import Dict, Any
from django.conf import settings
from integrations.rapidapi.exceptions import (
    InvalidPanError,
    PanNotFoundError,
    RateLimitError,
    ProviderUnavailableError,
)
from .normalizer import normalize_pan_response

PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')


class PANProvider(ABC):
    """Abstract interface for PAN verification providers."""

    @abstractmethod
    def verify_pan(self, pan_number: str) -> Dict[str, Any]:
        """Queries provider and returns normalized PAN identity dictionary."""
        pass


class RapidApiPANProvider(PANProvider):
    """
    RapidAPI PAN Verification Provider Adapter.
    Communicates with RapidAPI PAN lookup endpoints with timeout and error resilience,
    supporting educational/testing mock fallback when live credentials are not set.
    """

    def __init__(self):
        self.api_key = getattr(settings, 'RAPIDAPI_PAN_KEY', '') or os.environ.get('RAPIDAPI_PAN_KEY', '')
        self.api_host = getattr(settings, 'RAPIDAPI_PAN_HOST', '') or os.environ.get('RAPIDAPI_PAN_HOST', 'pan-verification.p.rapidapi.com')

    def verify_pan(self, pan_number: str) -> Dict[str, Any]:
        pan = pan_number.strip().upper()
        if not PAN_REGEX.match(pan):
            raise InvalidPanError("Invalid PAN format. PAN must consist of 5 uppercase letters, 4 digits, and 1 uppercase letter.")

        # If live credentials exist and live mode is active, make HTTP request
        if self.api_key and self.api_key != 'mock_key' and not getattr(settings, 'TESTING', False):
            import requests
            url = f"https://{self.api_host}/pan/verify"
            headers = {
                'x-rapidapi-key': self.api_key,
                'x-rapidapi-host': self.api_host,
                'Content-Type': 'application/json',
            }
            try:
                response = requests.post(url, json={'pan_number': pan}, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return normalize_pan_response(data, pan)
                elif response.status_code == 404:
                    raise PanNotFoundError(f"PAN record '{pan}' not found in registry.")
                elif response.status_code == 429:
                    raise RateLimitError("RapidAPI PAN verification rate limit exceeded. Please try again later.")
                else:
                    raise ProviderUnavailableError(f"PAN provider returned status {response.status_code}.")
            except requests.Timeout:
                raise ProviderUnavailableError("RapidAPI PAN provider request timed out.")
            except requests.RequestException as e:
                raise ProviderUnavailableError(f"Failed to connect to RapidAPI PAN service: {str(e)}")

        # Deterministic simulation / academic fallback mode
        return self._simulate_pan_response(pan)

    def _simulate_pan_response(self, pan: str) -> Dict[str, Any]:
        """Provides realistic deterministic PAN registry data for development and test scenarios."""
        if pan.startswith('ZZZZZ') or pan.startswith('NOTFD'):
            raise PanNotFoundError(f"PAN record '{pan}' does not exist in national income tax registry.")
        if pan.startswith('LIMIT'):
            raise RateLimitError("Provider rate limit reached for simulated test.")
        if pan.startswith('ERROR'):
            raise ProviderUnavailableError("Provider internal service unavailable.")

        # Check canonical 15 synthetic users first
        try:
            from apps.vehicles.data.synthetic_dataset import get_user_by_pan
            matched_user = get_user_by_pan(pan)
            if matched_user:
                raw_data = {
                    'name': f"{matched_user['first_name']} {matched_user['last_name']}",
                    'full_name': f"{matched_user['first_name']} {matched_user['last_name']}",
                    'dob': '1992-06-15',
                    'phone': matched_user['phone_number'],
                    'reference_id': f"RAPID-PAN-{pan}",
                    'status': 'VALID',
                }
                return normalize_pan_response(raw_data, pan)
        except Exception:
            pass

        # Default simulated PAN identity (last digits map to deterministic phone numbers)
        # e.g. ABCDE1234F -> phone: 9876541234
        digits = "".join(c for c in pan if c.isdigit())
        simulated_phone = f"987654{digits}"

        raw_data = {
            'name': 'Rohan Sharma',
            'full_name': 'Rohan Sharma',
            'dob': '1995-04-12',
            'phone': simulated_phone,
            'reference_id': f"RAPID-PAN-{pan}",
            'status': 'VALID',
        }
        return normalize_pan_response(raw_data, pan)
