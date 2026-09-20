from typing import Dict, Any, Optional


def mask_pan(pan: str) -> str:
    """
    Masks a 10-character Indian PAN number for safe storage and presentation.
    Example: ABCDE1234F -> ABCDE****F
    """
    clean = pan.strip().upper()
    if len(clean) == 10:
        return f"{clean[:5]}****{clean[-1]}"
    return clean[:4] + "****" if len(clean) > 4 else "****"


def mask_phone(phone: str) -> str:
    """
    Masks a phone number for safe storage and presentation.
    Example: 9876543210 -> ******3210
    """
    clean = "".join(c for c in phone if c.isdigit())
    if len(clean) >= 4:
        return f"{'*' * (len(clean) - 4)}{clean[-4:]}"
    return "******"


def normalize_pan_response(raw: Dict[str, Any], requested_pan: str) -> Dict[str, Any]:
    """
    Normalizes a third-party PAN API response into an internal identity structure.
    Never exposes unnecessary raw provider payloads.
    """
    full_name = raw.get('name') or raw.get('full_name') or raw.get('registered_name') or ''
    dob = raw.get('dob') or raw.get('date_of_birth') or ''
    phone = raw.get('phone') or raw.get('mobile_number') or raw.get('contact') or ''
    reference = raw.get('reference_id') or raw.get('transaction_id') or raw.get('request_id') or ''

    phone_clean = "".join(c for c in str(phone) if c.isdigit())
    phone_last_four = phone_clean[-4:] if len(phone_clean) >= 4 else ""

    return {
        'document_number_masked': mask_pan(requested_pan),
        'full_name': full_name.strip(),
        'date_of_birth': dob.strip(),
        'phone_last_four': phone_last_four,
        'verified_phone_masked': mask_phone(phone_clean) if phone_clean else "",
        'provider_reference': str(reference),
        'raw_provider_phone': phone_clean,
    }
