from typing import Dict, Any, Optional
from decimal import Decimal


def normalize_vehicle_response(raw: Dict[str, Any], requested_reg: str) -> Dict[str, Any]:
    """
    Normalizes third-party Vehicle / RC registry response into canonical internal structure.
    Compatible with RapidAPI 'Vehicle RC Information V2' payload schemas and standard VAHAN attributes.
    If the provider does not supply a field, returns None. Never fabricates missing fields.
    """
    # Unpack nested payload wrapper if present (e.g. {'data': {...}} or {'result': {...}})
    payload = raw
    if isinstance(raw.get('data'), dict):
        payload = raw['data']
    elif isinstance(raw.get('result'), dict):
        payload = raw['result']
    elif isinstance(raw.get('vehicle_details'), dict):
        payload = raw['vehicle_details']

    reg_number = payload.get('registration_number') or payload.get('vehicle_number') or payload.get('reg_no') or requested_reg
    clean_reg = "".join(c for c in str(reg_number).upper() if c.isalnum())

    # Make / Manufacturer
    make = (
        payload.get('make') or
        payload.get('maker_description') or
        payload.get('manufacturer') or
        payload.get('brand') or
        None
    )

    # Model / Variant
    model = (
        payload.get('model') or
        payload.get('maker_model') or
        payload.get('model_name') or
        None
    )
    # If model contains maker prefix (e.g., 'HYUNDAI CRETA'), parse cleanly
    if make and model and model.upper().startswith(make.upper()):
        model = model[len(make):].strip(" -_")

    variant = (
        payload.get('variant') or
        payload.get('sub_model') or
        payload.get('vehicle_class') or
        None
    )

    vehicle_type = (
        payload.get('vehicle_type') or
        payload.get('vehicle_category') or
        payload.get('body_type') or
        payload.get('category') or
        None
    )

    fuel_type = (
        payload.get('fuel_type') or
        payload.get('fuel_descr') or
        payload.get('fuel_description') or
        payload.get('fuel') or
        None
    )
    if fuel_type:
        fuel_type = fuel_type.strip().upper()

    try:
        manufacture_year = int(payload.get('manufacture_year') or payload.get('year') or payload.get('manufacturing_year') or 0) or None
    except (ValueError, TypeError):
        manufacture_year = None

    registration_date = (
        payload.get('registration_date') or
        payload.get('reg_date') or
        payload.get('rc_reg_date') or
        None
    )

    registration_state = (
        payload.get('registration_state') or
        payload.get('state') or
        payload.get('state_name') or
        None
    )

    registration_city = (
        payload.get('registration_city') or
        payload.get('city') or
        payload.get('registered_at') or
        payload.get('rto') or
        payload.get('rto_name') or
        None
    )

    engine_number = (
        payload.get('engine_number') or
        payload.get('engine_no') or
        None
    )

    chassis_number = (
        payload.get('chassis_number') or
        payload.get('chassis_no') or
        payload.get('vin') or
        None
    )

    owner_name = (
        payload.get('owner_name') or
        payload.get('owner') or
        payload.get('owner_name_masked') or
        None
    )

    fitness_upto = (
        payload.get('fitness_upto') or
        payload.get('fit_up_to') or
        payload.get('fitness_valid_upto') or
        payload.get('fitness_validity') or
        None
    )

    insurance_upto = (
        payload.get('insurance_upto') or
        payload.get('insurance_valid_upto') or
        payload.get('insurance_validity') or
        payload.get('insurance_policy_validity') or
        None
    )

    vehicle_value = None
    raw_val = payload.get('vehicle_value') or payload.get('idv') or payload.get('insured_declared_value')
    if raw_val:
        try:
            vehicle_value = Decimal(str(raw_val))
        except Exception:
            vehicle_value = None

    return {
        'registration_number': clean_reg,
        'owner_name': owner_name,
        'make': make,
        'model': model,
        'variant': variant,
        'vehicle_type': vehicle_type,
        'fuel_type': fuel_type,
        'manufacture_year': manufacture_year,
        'registration_date': registration_date,
        'registration_state': registration_state,
        'registration_city': registration_city,
        'engine_number': engine_number,
        'chassis_number': chassis_number,
        'fitness_upto': fitness_upto,
        'insurance_upto': insurance_upto,
        'vehicle_value': vehicle_value,
    }
