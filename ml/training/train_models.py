import os
import json
import time
from pathlib import Path
from decimal import Decimal
import numpy as np
import pandas as pd
import joblib
import mlflow

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_score, recall_score, accuracy_score,
    root_mean_squared_error, mean_absolute_error, r2_score
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / 'data' / 'synthetic_vehicle_insurance_dataset.csv'
ARTIFACTS_DIR = BASE_DIR / 'artifacts'
MLRUNS_DIR = BASE_DIR.parent / 'mlruns'


def build_preprocessor() -> ColumnTransformer:
    """Builds the standardized ColumnTransformer for insurance feature transformations."""
    numeric_features = [
        'vehicle_age', 'vehicle_value', 'driver_age', 'annual_mileage',
        'previous_claims_count', 'deductible_amount'
    ]
    categorical_features = [
        'vehicle_type', 'fuel_type', 'usage_type', 'credit_score_tier', 'coverage_tier'
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features),
        ],
        remainder='drop'
    )
    return preprocessor


def train_and_evaluate_models():
    """
    Executes the complete machine learning training and model selection lifecycle:
    1. Loads historical synthetic dataset.
    2. Trains and compares 3 classification algorithms for Claim Probability.
    3. Trains and compares 3 regression algorithms for Claim Severity.
    4. Persists the best winning pipelines and metadata.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    MLFLOW_DB_PATH = BASE_DIR.parent / 'mlruns.db'

    try:
        os.environ['MLFLOW_ALLOW_FILE_STORE'] = 'true'
        mlflow.set_tracking_uri(f"sqlite:///{MLFLOW_DB_PATH.as_posix()}")
        mlflow.set_experiment("nexisure_vehicle_insurance")
    except Exception as e:
        print(f"MLflow setup note: {e}")

    curated_path = BASE_DIR / 'data' / 'curated_vehicle_insurance_dataset.csv'
    if curated_path.exists():
        print(f"Loading user-curated dataset from {curated_path}...")
        df = pd.read_csv(curated_path)
    elif not DATA_PATH.exists():
        from ml.data.generate_dataset import generate_synthetic_dataset
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        df = generate_synthetic_dataset(n_samples=7500, random_state=42)
        df.to_csv(DATA_PATH, index=False)
    else:
        df = pd.read_csv(DATA_PATH)

    if 'past_claims_count' in df.columns and 'previous_claims_count' not in df.columns:
        df['previous_claims_count'] = df['past_claims_count']

    print(f"Loaded dataset with {len(df)} records. Claim rate: {df['claim_filed'].mean():.2%}")

    feature_cols = [
        'vehicle_age', 'vehicle_type', 'fuel_type', 'usage_type',
        'vehicle_value', 'driver_age', 'annual_mileage', 'credit_score_tier',
        'previous_claims_count', 'coverage_tier', 'deductible_amount'
    ]
    X = df[feature_cols]
    y_clf = df['claim_filed']

    X_train_c, X_test_c, y_train_c, y_test_c = train_test_split(
        X, y_clf, test_size=0.20, random_state=42, stratify=y_clf
    )

    # -------------------------------------------------------------------------
    # 1. MODEL 1: CLAIM PROBABILITY CLASSIFIER COMPARISON
    # -------------------------------------------------------------------------
    print("\n=======================================================")
    print("--- Training & Comparing Claim Probability Classifiers ---")
    print("=======================================================")

    clf_candidates = {
        'LogisticRegression': LogisticRegression(max_iter=1000, random_state=42),
        'RandomForestClassifier': RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42),
        'GradientBoostingClassifier': GradientBoostingClassifier(n_estimators=100, learning_rate=0.08, max_depth=4, random_state=42),
    }

    clf_results = {}
    best_clf_name = None
    best_clf_score = -1.0
    best_clf_pipeline = None

    for name, model in clf_candidates.items():
        pipe = Pipeline(steps=[
            ('preprocessor', build_preprocessor()),
            ('classifier', model)
        ])
        t0 = time.time()
        pipe.fit(X_train_c, y_train_c)
        train_time = time.time() - t0

        y_pred = pipe.predict(X_test_c)
        y_prob = pipe.predict_proba(X_test_c)[:, 1]

        auc = roc_auc_score(y_test_c, y_prob)
        f1 = f1_score(y_test_c, y_pred, zero_division=0)
        prec = precision_score(y_test_c, y_pred, zero_division=0)
        rec = recall_score(y_test_c, y_pred, zero_division=0)
        acc = accuracy_score(y_test_c, y_pred)

        clf_results[name] = {
            'roc_auc': round(float(auc), 4),
            'f1_score': round(float(f1), 4),
            'precision': round(float(prec), 4),
            'recall': round(float(rec), 4),
            'accuracy': round(float(acc), 4),
            'train_time_sec': round(train_time, 3),
        }
        print(f"[{name}] ROC-AUC: {auc:.4f} | F1: {f1:.4f} | Recall: {rec:.4f} | Accuracy: {acc:.4f}")

        try:
            with mlflow.start_run(run_name=f"clf_{name}"):
                mlflow.log_params({
                    "algorithm": name,
                    "model_type": "classifier",
                    "dataset_version": "synthetic_v1_7500_records"
                })
                mlflow.log_metrics(clf_results[name])
                mlflow.set_tag("task", "claim_probability")
        except Exception as e:
            print(f"MLflow clf run note: {e}")

        if auc > best_clf_score:
            best_clf_score = auc
            best_clf_name = name
            best_clf_pipeline = pipe

    print(f"\nWinning Classifier: {best_clf_name} (ROC-AUC: {best_clf_score:.4f})")

    # Save winning classifier pipeline
    clf_path = ARTIFACTS_DIR / 'claim_probability_pipeline.joblib'
    joblib.dump(best_clf_pipeline, clf_path)
    print(f"Saved classifier pipeline to: {clf_path}")

    # -------------------------------------------------------------------------
    # 2. MODEL 2: CLAIM SEVERITY REGRESSOR COMPARISON
    # -------------------------------------------------------------------------
    print("\n=======================================================")
    print("--- Training & Comparing Claim Severity Regressors ---")
    print("=======================================================")

    positive_mask = df['claim_filed'] == 1
    df_pos = df[positive_mask].copy()
    X_pos = df_pos[feature_cols]
    y_reg = df_pos['claim_amount']

    X_train_r, X_test_r, y_train_r, y_test_r = train_test_split(
        X_pos, y_reg, test_size=0.20, random_state=42
    )

    reg_candidates = {
        'RidgeRegression': Ridge(alpha=10.0, random_state=42),
        'RandomForestRegressor': RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42),
        'GradientBoostingRegressor': GradientBoostingRegressor(n_estimators=100, learning_rate=0.08, max_depth=4, random_state=42),
    }

    reg_results = {}
    best_reg_name = None
    best_reg_score = float('inf')
    best_reg_pipeline = None

    for name, model in reg_candidates.items():
        pipe = Pipeline(steps=[
            ('preprocessor', build_preprocessor()),
            ('regressor', model)
        ])
        t0 = time.time()
        pipe.fit(X_train_r, y_train_r)
        train_time = time.time() - t0

        y_pred = pipe.predict(X_test_r)

        rmse = root_mean_squared_error(y_test_r, y_pred)
        mae = mean_absolute_error(y_test_r, y_pred)
        r2 = r2_score(y_test_r, y_pred)

        reg_results[name] = {
            'rmse': round(float(rmse), 2),
            'mae': round(float(mae), 2),
            'r2_score': round(float(r2), 4),
            'train_time_sec': round(train_time, 3),
        }
        print(f"[{name}] RMSE: ${rmse:.2f} | MAE: ${mae:.2f} | R²: {r2:.4f}")

        try:
            with mlflow.start_run(run_name=f"reg_{name}"):
                mlflow.log_params({
                    "algorithm": name,
                    "model_type": "regressor",
                    "dataset_version": "synthetic_v1_7500_records"
                })
                mlflow.log_metrics(reg_results[name])
                mlflow.set_tag("task", "claim_severity")
        except Exception as e:
            print(f"MLflow reg run note: {e}")

        if rmse < best_reg_score:
            best_reg_score = rmse
            best_reg_name = name
            best_reg_pipeline = pipe

    print(f"\nWinning Regressor: {best_reg_name} (RMSE: ${best_reg_score:.2f})")

    # Save winning regressor pipeline
    reg_path = ARTIFACTS_DIR / 'claim_severity_pipeline.joblib'
    joblib.dump(best_reg_pipeline, reg_path)
    print(f"Saved regressor pipeline to: {reg_path}")

    # -------------------------------------------------------------------------
    # 3. SAVE COMPREHENSIVE METADATA FOR REGISTRY & AUDIT
    # -------------------------------------------------------------------------
    metadata = {
        'trained_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'dataset_version': 'synthetic_v1_7500_records',
        'classifier': {
            'model_name': 'ClaimProbabilityPredictor',
            'version': '1.0.0',
            'best_algorithm': best_clf_name,
            'metric_evaluated': 'roc_auc',
            'all_results': clf_results,
            'artifact_file': 'claim_probability_pipeline.joblib',
            'feature_names': feature_cols,
        },
        'regressor': {
            'model_name': 'ClaimSeverityPredictor',
            'version': '1.0.0',
            'best_algorithm': best_reg_name,
            'metric_evaluated': 'rmse',
            'all_results': reg_results,
            'artifact_file': 'claim_severity_pipeline.joblib',
            'feature_names': feature_cols,
        }
    }

    meta_path = ARTIFACTS_DIR / 'models_metadata.json'
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved model metadata and comparison summary to: {meta_path}")

    return metadata


def sync_with_django_registry():
    """Synchronizes the trained models into Django's ModelVersion table."""
    try:
        import sys
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        django.setup()
        from predictions.models import ModelVersion

        meta_path = ARTIFACTS_DIR / 'models_metadata.json'
        if not meta_path.exists():
            return

        with open(meta_path, 'r') as f:
            meta = json.load(f)

        # 1. Sync Classifier
        clf_meta = meta['classifier']
        # Deactivate old versions
        ModelVersion.objects.filter(model_name=clf_meta['model_name']).update(is_active_for_inference=False)
        ModelVersion.objects.update_or_create(
            model_name=clf_meta['model_name'],
            version=clf_meta['version'],
            defaults={
                'algorithm_name': clf_meta['best_algorithm'],
                'evaluation_metrics': clf_meta['all_results'][clf_meta['best_algorithm']],
                'artifact_path': str(ARTIFACTS_DIR / clf_meta['artifact_file']),
                'training_dataset_version': meta['dataset_version'],
                'is_active_for_inference': True,
                'notes': f"Trained with {clf_meta['best_algorithm']}. ROC-AUC: {clf_meta['all_results'][clf_meta['best_algorithm']]['roc_auc']}",
            }
        )

        # 2. Sync Regressor
        reg_meta = meta['regressor']
        ModelVersion.objects.filter(model_name=reg_meta['model_name']).update(is_active_for_inference=False)
        ModelVersion.objects.update_or_create(
            model_name=reg_meta['model_name'],
            version=reg_meta['version'],
            defaults={
                'algorithm_name': reg_meta['best_algorithm'],
                'evaluation_metrics': reg_meta['all_results'][reg_meta['best_algorithm']],
                'artifact_path': str(ARTIFACTS_DIR / reg_meta['artifact_file']),
                'training_dataset_version': meta['dataset_version'],
                'is_active_for_inference': True,
                'notes': f"Trained with {reg_meta['best_algorithm']}. RMSE: ${reg_meta['all_results'][reg_meta['best_algorithm']]['rmse']}",
            }
        )
        print("Successfully synchronized models into Django ModelVersion registry.")
    except Exception as e:
        print(f"Note: Django sync skipped or deferred: {e}")


if __name__ == '__main__':
    train_and_evaluate_models()
    sync_with_django_registry()
