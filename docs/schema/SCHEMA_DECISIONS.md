# Nexisure Architecture & Schema Decisions

This document records the architectural decisions, design rationales, and reconciliation tradeoffs undertaken to establish the final canonical schema for Nexisure.

---

## 1. Schema Comparison: Old Schema vs. Nexisure Schema vs. Final Canonical Schema

| Domain Entity | Old Schema | Initial Nexisure Draft | Final Canonical Schema | Decision Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **User Identity** | 4 roles: `CUSTOMER`, `UNDERWRITER`, `CLAIMS_HANDLER`, `ADMINISTRATOR` | Same 4 roles | **3 Top-Level Roles**: `USER`, `STAFF`, `ADMIN` | Underwriter and Claims Handler are specializations of `STAFF` designated by `StaffProfile.department`. A customer is `USER`. |
| **User Phone Verification** | `phone_number` string only | `phone_number` string only | `phone_number` + `phone_verified` boolean | Tracks verified registered phone number essential for 2FA phone matching in KYC. |
| **Email OTP Token** | `id, email, otp_hash, expires_at, is_used, attempts_count, user` | Same | Added `purpose` (e.g., `LOGIN`, `VERIFICATION`) | Distinguishes login tokens from step-up verification tokens while preserving cryptographic hashing. |
| **Customer Profile** | Minimal fields: code, DOB, DL number, address | Extended profile | Full profile: names, gender, DL expiry, emergency contacts, identity verification flag | Provides a complete customer 360 view for assigned staff without redundant user lookups. |
| **KYC / PAN Verification** | None / treated as simple text | Embedded fields in customer profile | Dedicated `KYCVerification` model with state machine | Separates third-party provider tracking and audit trail from customer profile. Hides sensitive raw PAN and phone data. |
| **Staff Profile** | Flat employee profile with hard-coded approval limit | Generic staff profile | `StaffProfile` with department (`UNDERWRITING`/`CLAIMS`), branch FK, manager FK, performance metrics | Modular staff foundation anchoring specialized profiles. |
| **Specialized Profiles** | Independent profiles | Linked to staff | `UnderwriterProfile` and `ClaimsHandlerProfile` linked 1-to-1 to `StaffProfile` | Keeps operational limits (e.g., claim approval limit, underwriting limit) tied strictly to staff specialization. |
| **Staff-Customer Relationship**| None (Staff had global access) | Conceptual only | **Persistent `StaffCustomerAssignment`** model with full audit history | Enforces zero-trust data access: staff members can only access their assigned customers. |
| **Vehicle Asset** | Basic specs (make, model, year, value, reg, chassis) | Basic specs | Extended with `variant`, `purchase_date`, `owner_name`, `registration_state/city`, `fitness_upto`, `insurance_upto` | Supports normalized data fetched from official vehicle registries via RapidAPI. |
| **Vehicle Catalog** | Hard-coded or unstructured | None | `VehicleModelSpec` master catalog | Standardizes automotive technical characteristics (NCAP safety rating, dimensions, powertrain, base price). |
| **Quotation Draft** | Single `underwriter` relationship | `underwriter` FK | Renamed to `assigned_staff`, added `reviewed_by` and `created_by` | Generalizes relationship away from legacy underwriter role to multi-tier staff review. |
| **Policy Contract** | `underwriter` relationship | `underwriter` FK | Renamed to `assigned_staff`, added `issued_by`, cancellation reason/date, renewal date | Provides complete policy contract lifecycle tracking and renewal lineage via `previous_policy`. |
| **Policy Addons** | M2M on features | M2M on features | Explicit `Addon` and `PolicyAddon` junction table | Captures immutable historical purchase price of riders at policy binding time. |
| **Claim Lifecycle** | Basic fields (estimate, settlement, handler, status) | Shared queue | Extended: `claim_type`, `claim_severity`, `approved_amount`, `priority`, assignment/review/resolution timestamps | Complete human-in-the-loop claim adjudication workflow with decision timestamps. |
| **Claim Document** | `claim, doc_type, title, file` | Same | Added `uploaded_by`, `verification_status`, `verified_by`, `verified_at` | Provides chain of custody and document verification for claims adjudication. |
| **Service Requests** | `request_type, payload, status, assigned_staff` | Same | Added `assigned_by`, `resolved_by`, `priority` | Tracks dispatch and resolution accountability. |
| **Simulated Payment** | Basic transaction details | Same | Added `payment_method`, explicit simulated disclaimers | Ensures compliance with non-production educational requirements. |
| **Audit Ledger** | Basic event logging | Immutable append-only | Multi-role actor taxonomy (`USER`, `STAFF/UNDERWRITING`, `STAFF/CLAIMS`, `ADMIN`) | Non-repudiation ledger covering all security, KYC, and operational events. |

---

## 2. Detailed Rationale of Key Architectural Decisions

### 2.1 Three-Role Hierarchy & Specialization Modeling
- **Problem**: Treating `UNDERWRITER` and `CLAIMS_HANDLER` as top-level roles creates role explosion, fragmented authorization logic, and prevents staff cross-training or organizational reassignment.
- **Solution**:
  - `User.role` has exactly three values: `USER`, `STAFF`, `ADMIN`.
  - `StaffProfile.department` holds the employee's operational domain: `UNDERWRITING` or `CLAIMS`.
  - To prevent breaking existing templates and business logic, property accessors (`user.is_underwriter`, `user.is_claims_handler`, `user.is_customer`, `user.is_administrator`) dynamically inspect the staff profile department and user role.

### 2.2 Persistent Staff-Customer Assignment
- **Problem**: In previous prototypes, any staff member could view or edit any customer's records, creating severe multi-tenant data leakage risks.
- **Solution**:
  - Created `StaffCustomerAssignment` model connecting a `STAFF` user to a `CustomerProfile`, recorded by an `ADMIN` user.
  - Added a unique database constraint guaranteeing that a customer has at most one `ACTIVE` staff assignment at a time.
  - Implemented `IsAssignedStaffOrAdmin` permission checks on all customer, vehicle, quotation, policy, claim, and service request endpoints. If a staff member attempts to view or modify an unassigned customer's record via manual URL tampering, the backend raises `PermissionDenied`.

### 2.3 KYC / PAN Verification Architecture
- **Problem**: Raw PAN lookups from third-party APIs can be abused if a user enters another citizen's PAN. Relying on API success alone allows identity theft.
- **Solution: Two-Factor Identity Verification**:
  1. User enters PAN.
  2. Backend queries RapidAPI PAN provider.
  3. Backend extracts identity attributes and the PAN-linked mobile number.
  4. Backend matches the provider-linked phone against the customer's verified registered account phone.
  5. **If phone mismatch**: Verification immediately aborts. Safe mismatch message shown. No OTP is sent. Provider phone is never exposed. Failed KYC event is audited.
  6. **If phone matches**: Server initiates short-lived Firebase Phone OTP challenge.
  7. User submits OTP received on their verified device.
  8. Firebase verifies the OTP; backend validates the Firebase authentication result.
  9. `KYCVerification.status` transitions to `VERIFIED`, and `CustomerProfile.is_identity_verified` is set to `True`.

### 2.4 Data Privacy & Masking Rules
- **PAN**: Never store raw 10-character PAN in plain text or application logs. Only `document_number_masked` (e.g. `ABCDE****F`) is stored.
- **Phone Number**: Never display or store full PAN-linked phone numbers from external APIs. Only `verified_phone_masked` (e.g. `******1234`) is retained and displayed.
- **OTPs**: Never log OTPs; always store secure cryptographic hashes.
- **Financial Cards**: Simulated card transactions only store masked representations (e.g. `**** **** **** 4242`). Full PAN and CVV are never persisted.

### 2.5 Vehicle Registry Lookup & Confirmation Workflow
- **Problem**: Automatically saving external API data without user confirmation creates corrupted assets and violates data governance.
- **Solution: Two-Step Registry Verification**:
  1. Customer submits Registration Plate (e.g., `MH12AB1234`).
  2. Backend validates format and queries RapidAPI Vehicle RC provider.
  3. Data is normalized (nulling missing fields rather than guessing).
  4. Normalized preview is rendered to the user with clear badges: *"Fetched from vehicle registry"*.
  5. Customer reviews details and explicitly clicks *"Confirm & Save Vehicle"*.
  6. Only upon explicit confirmation is the vehicle entity saved to the database.

### 2.6 External Integration Layer Isolation
- Third-party HTTP requests to RapidAPI and Firebase are isolated in `integrations/`:
  - `integrations/rapidapi/pan/`: `RapidApiPANProvider` adapter, normalization, exception mapping.
  - `integrations/rapidapi/vehicle/`: `RapidApiVehicleProvider` adapter, RC normalization, exception mapping.
  - `integrations/firebase/`: Firebase OTP challenge and token verification adapter.
- Abstract provider interfaces (`PANProvider`, `VehicleProvider`) allow switching to official government portals (e.g. Parivahan, NSDL) without touching application domain logic.
- Built-in fallback providers support 100% offline, deterministic testing and academic evaluation when live API keys are absent.

### 2.7 Derived vs. Persisted Metrics
- Avoid storing mutable performance counters in database columns:
  - `claims_handled_count` and `claims_settled_count` are dynamically aggregated from `Claim` records.
  - `average_resolution_hours` is calculated from `created_at` and `resolved_at` timestamps.
- Preserved historical financial values:
  - `Policy.premium_amount` and `PolicyAddon.price_at_purchase` are locked at issuance and never mutate even if plan base rates change.
