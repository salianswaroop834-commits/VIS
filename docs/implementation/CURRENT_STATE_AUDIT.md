# NexiSure Platform — Current State Audit

## 1. Executive Summary

This document captures the verified technical and operational state of the **NexiSure Vehicle Insurance Management Platform** following the final implementation and hardening pass.

All key modules across authentication, vehicle registry integrations, underwriting rating, quotation workflows, simulated payment processing, policy lifecycle, human-in-the-loop claim adjudication, predictive analytics, grounded RAG, chatbot guardrails, and notification systems are fully operational and covered by an automated test suite.

---

## 2. Environment & System Verification

- **Django System Check**:
  ```bash
  python manage.py check
  # Output: System check identified no issues (0 silenced).
  ```
- **Database Migrations Dry-Run**:
  ```bash
  python manage.py makemigrations --check --dry-run
  # Output: No changes detected
  ```
- **Automated Test Suite**:
  ```bash
  pytest tests/ -q
  # Output: 301 passed, 0 failed in 250s
  ```

---

## 3. Subsystem Audit & Operational Status

### 3.1 Authentication & KYC
- **Email OTP Token**: 6-digit cryptographic verification with 10-minute validity, rate limiting, and brute-force lockout after 3 consecutive failures.
- **Firebase Two-Factor Authentication**: Abstracted through `FirebaseOtpProvider` interface with live `RealFirebaseProvider` and robust `MockFirebaseProvider`.
- **PAN Verification**: Seamless integration via `RapidApiPANProvider` with strict regex validation (`[A-Z]{5}[0-9]{4}[A-Z]`), masked mobile verification, and audit logging.

### 3.2 Vehicles & External Registries
- **Vehicle Registry (RC Lookup)**: Communicates via `RapidApiVehicleProvider` with `vehicle-rc-information-v2.p.rapidapi.com`. Gracefully handles 429 quota exhaustion and provider errors by activating deterministic 38-vehicle synthetic catalog fallback.
- **Chassis Verification**: Implemented in `VehicleLookupService.verify_chassis` and exposed at `/vehicles/verify-chassis/`, matching the last 5 characters against the registered vehicle record.
- **Asset Protection**: Strict duplicate prevention prevents registering vehicles already bound to an active customer profile.

### 3.3 Quotations & Underwriting Rating
- **IDV Calculation Engine**: Actuarial depreciation schedules applied to ex-showroom price based on vehicle age tiers (0-6 mo: 5%, 6-12 mo: 15%, 1-2 yr: 20%, 2-3 yr: 30%, 3-4 yr: 40%, 4-5 yr: 50%).
- **Premium Calculation**: Combines base tariff, cubic capacity multiplier, fuel type factor, add-ons selection, No Claim Bonus (NCB) discounts, and standard 18% GST.
- **Add-on Riders**: Default add-ons seeded across all environments (Zero Depreciation, Engine Protection, Roadside Assistance, NCB Protect, Return to Invoice).

### 3.4 Payment Processing & Policy Issuance
- **Synthetic Payment Gateway**: Mod-10 Luhn validation, card brand detection, expiration checks, CVV verification, and zero raw credential storage (masked as `**** **** **** 0001`).
- **Idempotency & Lifecycle**: Atomic transition from accepted draft to `ACTIVE` policy upon successful payment authorization. Full endorsement, renewal (+1 year rollover), and cancellation flows supported.
- **Policy PDF Generation**: Generates compliant downloadable certificates with complete financial breakdowns, terms, and academic prototype disclaimers.

### 3.5 Claims Management & Document Security
- **Lifecycle Workflow**: Pending $\rightarrow$ In Review $\rightarrow$ Approved / Rejected $\rightarrow$ Settled.
- **Human-in-the-Loop Safeguards**: ML models provide risk and anomaly indicators; claim approval and settlement are strictly reserved for authorized claims handlers within financial discretion limits.
- **Document Management**: File size ceiling (10MB), extension whitelist (`.pdf`, `.jpg`, `.jpeg`, `.png`), and path traversal sanitization.

### 3.6 AI, ML & RAG Integration
- **Predictive ML**: Trained pipeline for claim probability and severity estimation with inference logging via `PredictionLog`.
- **RAG System**: Approved insurance document chunking, cosine vector similarity retrieval, citation tracing, prompt injection defense, and safe fallbacks for insufficient information.
- **Unsafe RAG Demonstration**: Live adversarial demonstration at `/rag/unsafe-demo/` proving prompt injection defense.
- **Chatbot Guardrails**: Strict tool allowlist, customer data isolation, and two-step confirmation for state-changing operations.

### 3.7 Notifications & Operational Auditing
- **Context Processor**: Injects real-time unread counts and alerts into navigation bars.
- **Triggers**: Fully wired to KYC, vehicle verification, quotation generation, payment, policy issuance/cancellation, and claim adjudication.
- **Audit Logging**: Structured before/after delta logs with actor, IP address, and timestamp.
