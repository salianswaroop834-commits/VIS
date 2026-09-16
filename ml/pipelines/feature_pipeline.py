import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, mean_absolute_error, root_mean_squared_error, r2_score
)


class FeaturePipeline:
    """
    Reusable actuarial feature preparation and evaluation pipeline.
    Enforces clean separation:
    Raw Data -> Validation -> Normalization & Encoding -> Feature Engineering -> Split -> Evaluation.
    Guarantees zero data leakage by fitting transformers strictly on training sets.
    """

    NUMERIC_COLS = [
        'vehicle_age', 'vehicle_value', 'driver_age', 'annual_mileage',
        'previous_claims_count', 'deductible_amount'
    ]

    CATEGORICAL_COLS = [
        'vehicle_type', 'fuel_type', 'usage_type', 'credit_score_tier', 'coverage_tier'
    ]

    ALL_FEATURE_COLS = NUMERIC_COLS + CATEGORICAL_COLS

    VALID_CATEGORIES = {
        'vehicle_type': {'SEDAN', 'SUV', 'HATCHBACK', 'TRUCK', 'MOTORCYCLE', 'COMMERCIAL_VAN'},
        'fuel_type': {'PETROL', 'DIESEL', 'ELECTRIC', 'HYBRID', 'CNG'},
        'usage_type': {'PERSONAL', 'COMMERCIAL', 'RIDESHARE'},
        'credit_score_tier': {'EXCELLENT', 'GOOD', 'FAIR', 'POOR'},
        'coverage_tier': {'THIRD_PARTY', 'COMPREHENSIVE', 'ZERO_DEP_PREMIUM', 'STANDARD'},
    }

    @classmethod
    def validate_raw_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates raw payload fields, imputes sensible actuarial defaults,
        and sanitizes numeric ranges and categorical values.
        """
        sanitized = {}

        # Numeric bounds checking
        try:
            v_age = max(0, min(50, int(payload.get('vehicle_age', 3))))
        except (ValueError, TypeError):
            v_age = 3
        sanitized['vehicle_age'] = v_age

        try:
            v_val = max(1000.0, float(payload.get('vehicle_value', 500000.0)))
        except (ValueError, TypeError):
            v_val = 500000.0
        sanitized['vehicle_value'] = v_val

        try:
            d_age = max(18, min(100, int(payload.get('driver_age', 35))))
        except (ValueError, TypeError):
            d_age = 35
        sanitized['driver_age'] = d_age

        try:
            mileage = max(500, min(150000, int(payload.get('annual_mileage', 12000))))
        except (ValueError, TypeError):
            mileage = 12000
        sanitized['annual_mileage'] = mileage

        past_claims = payload.get('previous_claims_count', payload.get('past_claims_count', 0))
        try:
            p_claims = max(0, min(20, int(past_claims)))
        except (ValueError, TypeError):
            p_claims = 0
        sanitized['previous_claims_count'] = p_claims

        try:
            deductible = max(0.0, float(payload.get('deductible_amount', 1000.0)))
        except (ValueError, TypeError):
            deductible = 1000.0
        sanitized['deductible_amount'] = deductible

        # Categorical sanitization
        for cat_col, allowed in cls.VALID_CATEGORIES.items():
            val = str(payload.get(cat_col, next(iter(allowed)))).strip().upper()
            if val not in allowed:
                val = next(iter(allowed))
            sanitized[cat_col] = val

        return sanitized

    @classmethod
    def engineer_features(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generates domain-specific feature interactions without leaking future targets:
        - idv_to_deductible_ratio
        - high_mileage_indicator
        - senior_or_youth_risk_cohort
        """
        df_feat = df.copy()

        # Ratio of vehicle value to selected deductible
        deductible_safe = df_feat['deductible_amount'].replace(0, 100.0)
        df_feat['value_to_deductible_ratio'] = df_feat['vehicle_value'] / deductible_safe

        # Duty cycle exposure indicator
        df_feat['high_mileage_indicator'] = (df_feat['annual_mileage'] > 18000).astype(int)

        # Actuarial risk cohort: young (<25) or senior (>65) drivers
        df_feat['elevated_age_cohort'] = (
            (df_feat['driver_age'] < 25) | (df_feat['driver_age'] > 65)
        ).astype(int)

        return df_feat

    @classmethod
    def build_preprocessor(cls) -> ColumnTransformer:
        """
        Constructs the standardized scikit-learn ColumnTransformer.
        Scales continuous numerical variables and one-hot encodes categoricals.
        """
        return ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), cls.NUMERIC_COLS),
                ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cls.CATEGORICAL_COLS),
            ],
            remainder='drop'
        )

    @classmethod
    def split_data(
        cls,
        df: pd.DataFrame,
        target_col: str,
        test_size: float = 0.20,
        random_state: int = 42,
        stratify: bool = True,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """
        Splits dataset into train and test partitions.
        Ensures zero data leakage between evaluation and training sets.
        """
        X = df[cls.ALL_FEATURE_COLS].copy()
        y = df[target_col].copy()

        stratify_target = y if (stratify and y.nunique() <= 10) else None

        return train_test_split(
            X, y,
            test_size=test_size,
            random_state=random_state,
            stratify=stratify_target
        )

    @classmethod
    def evaluate_classifier(
        cls,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Computes comprehensive evaluation metrics for classification models.
        """
        metrics = {
            'accuracy': round(float(accuracy_score(y_true, y_pred)), 4),
            'precision': round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            'recall': round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            'f1_score': round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
            'confusion_matrix': confusion_matrix(y_true, y_pred).tolist(),
        }
        if y_prob is not None and len(np.unique(y_true)) > 1:
            try:
                metrics['roc_auc'] = round(float(roc_auc_score(y_true, y_prob)), 4)
            except Exception:
                metrics['roc_auc'] = None
        else:
            metrics['roc_auc'] = None

        return metrics

    @classmethod
    def evaluate_regressor(
        cls,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, Any]:
        """
        Computes comprehensive evaluation metrics for regression models.
        """
        return {
            'mae': round(float(mean_absolute_error(y_true, y_pred)), 2),
            'rmse': round(float(root_mean_squared_error(y_true, y_pred)), 2),
            'r2_score': round(float(r2_score(y_true, y_pred)), 4),
        }
