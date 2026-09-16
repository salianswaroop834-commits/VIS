import os
import numpy as np
import pandas as pd
from pathlib import Path


def generate_synthetic_dataset(n_samples: int = 6000, random_state: int = 42) -> pd.DataFrame:
    """
    Generates a realistic, statistically coherent vehicle insurance historical dataset.
    Features:
    - vehicle_age: int (0 to 15 years)
    - vehicle_type: category ('SEDAN', 'SUV', 'HATCHBACK', 'TRUCK', 'COMMERCIAL_VAN')
    - fuel_type: category ('PETROL', 'DIESEL', 'ELECTRIC', 'HYBRID', 'CNG')
    - usage_type: category ('PERSONAL', 'COMMERCIAL', 'RIDESHARE')
    - vehicle_value: float ($5,000 to $85,000)
    - driver_age: int (18 to 78)
    - annual_mileage: int (3,000 to 35,000 miles)
    - credit_score_tier: category ('EXCELLENT', 'GOOD', 'FAIR', 'POOR')
    - previous_claims_count: int (0 to 5)
    - coverage_tier: category ('THIRD_PARTY', 'COMPREHENSIVE', 'ZERO_DEP_PREMIUM')
    - deductible_amount: float ($250, $500, $1000, $2000)
    - annual_premium: float
    - claim_filed: binary (0 or 1, ~17% positive rate)
    - claim_amount: float (0.0 if claim_filed=0, else log-normally distributed loss <= vehicle_value)
    """
    rng = np.random.RandomState(random_state)

    # 1. Core Vehicle Features
    vehicle_types = ['SEDAN', 'SUV', 'HATCHBACK', 'TRUCK', 'COMMERCIAL_VAN']
    p_veh = [0.38, 0.32, 0.15, 0.10, 0.05]
    v_types = rng.choice(vehicle_types, size=n_samples, p=p_veh)

    fuel_types = ['PETROL', 'DIESEL', 'ELECTRIC', 'HYBRID', 'CNG']
    p_fuel = [0.45, 0.25, 0.15, 0.10, 0.05]
    f_types = rng.choice(fuel_types, size=n_samples, p=p_fuel)

    usage_types = ['PERSONAL', 'COMMERCIAL', 'RIDESHARE']
    p_usage = [0.72, 0.18, 0.10]
    u_types = rng.choice(usage_types, size=n_samples, p=p_usage)

    v_ages = rng.randint(0, 16, size=n_samples)

    # Vehicle value depends on vehicle type and age
    base_values = {
        'HATCHBACK': 16000,
        'SEDAN': 26000,
        'SUV': 36000,
        'TRUCK': 44000,
        'COMMERCIAL_VAN': 38000,
    }
    v_values = []
    for vt, va in zip(v_types, v_ages):
        base = base_values[vt] * rng.uniform(0.7, 1.4)
        depreciation = (0.91 ** va)
        v_values.append(max(4500.0, round(base * depreciation, 2)))
    v_values = np.array(v_values)

    # 2. Driver Demographics & Habits
    driver_ages = rng.randint(18, 79, size=n_samples)
    annual_mileage = rng.normal(12500, 4500, size=n_samples).clip(3000, 40000).astype(int)

    credit_tiers = ['EXCELLENT', 'GOOD', 'FAIR', 'POOR']
    p_credit = [0.28, 0.42, 0.20, 0.10]
    c_tiers = rng.choice(credit_tiers, size=n_samples, p=p_credit)

    # Previous claims Poisson
    prev_claims = rng.poisson(lam=0.35, size=n_samples).clip(0, 5)

    # 3. Policy Coverage Terms
    coverage_tiers = ['THIRD_PARTY', 'COMPREHENSIVE', 'ZERO_DEP_PREMIUM']
    p_cov = [0.25, 0.50, 0.25]
    cov_tiers = rng.choice(coverage_tiers, size=n_samples, p=p_cov)

    deductibles = rng.choice([250.0, 500.0, 1000.0, 2000.0], size=n_samples, p=[0.15, 0.40, 0.35, 0.10])

    # 4. Premium Calculation (Actuarial rule formula)
    rate_factors = {'THIRD_PARTY': 0.0125, 'COMPREHENSIVE': 0.0285, 'ZERO_DEP_PREMIUM': 0.0350}
    premiums = []
    for val, tier, usage, age in zip(v_values, cov_tiers, u_types, driver_ages):
        rate = rate_factors[tier]
        usage_mult = 1.35 if usage == 'COMMERCIAL' else (1.50 if usage == 'RIDESHARE' else 1.0)
        age_mult = 1.25 if age < 25 else (1.15 if age > 68 else 1.0)
        prem = round(val * rate * usage_mult * age_mult, 2)
        premiums.append(max(250.0, prem))
    premiums = np.array(premiums)

    # 5. Realistic Risk Scoring for Claim Probability (Logit)
    # Log-odds of a claim
    logit = -2.25  # Base rate ~10%
    # Young/elderly risk
    logit += np.where(driver_ages < 25, 0.55, 0.0)
    logit += np.where(driver_ages > 70, 0.35, 0.0)
    # Usage risk
    logit += np.where(u_types == 'RIDESHARE', 0.65, 0.0)
    logit += np.where(u_types == 'COMMERCIAL', 0.40, 0.0)
    # Mileage risk
    logit += (annual_mileage - 12000) / 25000.0 * 0.45
    # Previous claims risk
    logit += prev_claims * 0.35
    # Credit score proxy
    credit_penalties = {'POOR': 0.35, 'FAIR': 0.15, 'GOOD': 0.0, 'EXCELLENT': -0.15}
    logit += np.array([credit_penalties[c] for c in c_tiers])
    # Coverage tier moral hazard / reporting likelihood
    cov_effects = {'THIRD_PARTY': -0.40, 'COMPREHENSIVE': 0.10, 'ZERO_DEP_PREMIUM': 0.25}
    logit += np.array([cov_effects[cv] for cv in cov_tiers])

    # Convert logit to probability
    probs = 1.0 / (1.0 + np.exp(-logit))
    # Sample binary claim_filed
    claim_filed = (rng.uniform(0, 1, size=n_samples) < probs).astype(int)

    # 6. Severity (Claim Loss Amount)
    # Log-normal distribution scaled by vehicle value
    claim_amounts = np.zeros(n_samples, dtype=float)
    for i in range(n_samples):
        if claim_filed[i] == 1:
            # Scale severity: median claim is ~12-18% of vehicle value with long tail
            mu = np.log(v_values[i] * 0.15)
            sigma = 0.70
            loss = rng.lognormal(mean=mu, sigma=sigma)
            # Cannot exceed vehicle declared value
            claim_amounts[i] = round(float(min(v_values[i], max(100.0, loss))), 2)

    df = pd.DataFrame({
        'vehicle_age': v_ages,
        'vehicle_type': v_types,
        'fuel_type': f_types,
        'usage_type': u_types,
        'vehicle_value': v_values,
        'driver_age': driver_ages,
        'annual_mileage': annual_mileage,
        'credit_score_tier': c_tiers,
        'previous_claims_count': prev_claims,
        'coverage_tier': cov_tiers,
        'deductible_amount': deductibles,
        'annual_premium': premiums,
        'claim_filed': claim_filed,
        'claim_amount': claim_amounts,
    })

    return df


if __name__ == '__main__':
    data_dir = Path(__file__).resolve().parent
    data_dir.mkdir(parents=True, exist_ok=True)
    out_csv = data_dir / 'synthetic_vehicle_insurance_dataset.csv'

    print(f"Generating synthetic insurance dataset at {out_csv}...")
    df = generate_synthetic_dataset(n_samples=7500, random_state=42)
    df.to_csv(out_csv, index=False)
    print(f"Done! Dataset saved: {len(df)} records. Claim rate: {df['claim_filed'].mean():.2%}. Mean positive loss: ${df[df['claim_filed'] == 1]['claim_amount'].mean():.2f}")
