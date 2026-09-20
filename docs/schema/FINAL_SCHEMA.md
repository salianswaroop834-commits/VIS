# Nexisure Canonical Database Schema Specification

This document defines the final canonical database schema for the Nexisure Vehicle Insurance Management & Responsible Decision-Support Platform. It reconciles previous schema documents into a unified, normalized, and production-grade design conforming to Supabase PostgreSQL standards and Django 5.x conventions.

---

## 1. Core Principles & Standards

1. **Top-Level Role Triad**:
   - `User.role`: `USER` (Customer), `STAFF` (Employee), `ADMIN` (System Administrator).
   - Underwriting and Claims are specializations of `STAFF` designated by `StaffProfile.department` (`UNDERWRITING`, `CLAIMS`).
2. **Staff-Customer Assignment**:
   - Persistent `StaffCustomerAssignment` governs staff authorization. Staff members have access strictly and exclusively to their assigned customers.
3. **Monetary Precision**:
   - All financial amounts use `DecimalField` (e.g., `DECIMAL(12, 2)` or `DECIMAL(10, 2)`). Floating-point fields are strictly prohibited for monetary values.
4. **Primary Key Uniformity**:
   - UUIDv4 primary keys are utilized across all domain entities for seamless integration with Supabase Auth and PostgreSQL `uuid-ossp`/`pgcrypto`.
5. **Data Privacy & KYC Governance**:
   - Raw PAN numbers and full PAN-linked phone numbers are never stored in plaintext or logged.
   - Masked identifiers (`document_number_masked` e.g., `ABCDE****F`, `verified_phone_masked` e.g., `******1234`) are retained for verification auditability.
6. **External Integration Isolation**:
   - External provider adapters (RapidAPI, Firebase) are strictly separated from domain models and view layers.

---

## 2. Canonical Entity Definitions

### 2.1 Identity, Authentication & Access

#### `accounts_user` (`accounts.User`)
Central identity table mapped to Supabase Auth.
- `id`: `UUID`, Primary Key, default `uuid.uuid4`
- `email`: `VARCHAR(254)`, Unique, Indexed, NOT NULL
- `username`: `VARCHAR(150)`, Unique, NOT NULL
- `role`: `VARCHAR(20)`, Choices: `['USER', 'STAFF', 'ADMIN']`, default `'USER'`, Indexed
- `phone_number`: `VARCHAR(20)`, Blank, Indexed
- `supabase_uid`: `VARCHAR(64)`, Unique, Nullable, Indexed
- `email_verified`: `BOOLEAN`, default `FALSE`
- `phone_verified`: `BOOLEAN`, default `FALSE`
- `is_active`: `BOOLEAN`, default `TRUE`
- `is_staff`: `BOOLEAN`, default `FALSE` (Django admin access)
- `is_superuser`: `BOOLEAN`, default `FALSE`
- `last_login`: `TIMESTAMPTZ`, Nullable
- `date_joined`: `TIMESTAMPTZ`, default `NOW()`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `accounts_emailotptoken` (`accounts.EmailOtpToken`)
Hashed one-time passcodes for passwordless email verification.
- `id`: `UUID`, Primary Key
- `email`: `VARCHAR(254)`, Indexed, NOT NULL
- `otp_hash`: `VARCHAR(128)`, NOT NULL (Never raw OTP)
- `purpose`: `VARCHAR(30)`, default `'LOGIN'`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `expires_at`: `TIMESTAMPTZ`, Indexed, NOT NULL
- `is_used`: `BOOLEAN`, default `FALSE`, Indexed
- `attempts_count`: `INTEGER`, default `0`
- `user`: `FK -> accounts_user(id)`, ON DELETE CASCADE, Nullable

---

### 2.2 Customer & KYC Management

#### `customers_customerprofile` (`customers.CustomerProfile`)
Customer business profile anchored to a `USER` account.
- `id`: `UUID`, Primary Key
- `user`: `OneToOne -> accounts_user(id)`, ON DELETE CASCADE, Unique
- `customer_code`: `VARCHAR(30)`, Unique, Indexed, NOT NULL (e.g. `CUST-8F32A190`)
- `first_name`: `VARCHAR(100)`, Blank
- `last_name`: `VARCHAR(100)`, Blank
- `date_of_birth`: `DATE`, Nullable
- `gender`: `VARCHAR(20)`, Blank, Choices: `['MALE', 'FEMALE', 'OTHER', 'PREFER_NOT_TO_SAY']`
- `driving_license_number`: `VARCHAR(50)`, Blank
- `driving_license_expiry`: `DATE`, Nullable
- `address_line`: `VARCHAR(255)`, Blank
- `city`: `VARCHAR(100)`, Blank
- `state`: `VARCHAR(100)`, Blank
- `postal_code`: `VARCHAR(20)`, Blank
- `emergency_contact_name`: `VARCHAR(150)`, Blank
- `emergency_contact_phone`: `VARCHAR(20)`, Blank
- `is_identity_verified`: `BOOLEAN`, default `FALSE`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `customers_kycverification` (`customers.KYCVerification`)
Dedicated audit and state machine tracking external PAN verification and Firebase OTP validation.
- `id`: `UUID`, Primary Key
- `user`: `FK -> accounts_user(id)`, ON DELETE CASCADE
- `verification_type`: `VARCHAR(30)`, default `'PAN'`
- `document_number_masked`: `VARCHAR(30)`, NOT NULL (e.g. `ABCDE****F`)
- `provider`: `VARCHAR(50)`, default `'RAPIDAPI'`
- `provider_reference`: `VARCHAR(100)`, Blank
- `status`: `VARCHAR(30)`, Choices: `['PENDING', 'PHONE_OTP_REQUIRED', 'VERIFIED', 'FAILED', 'EXPIRED']`, default `'PENDING'`
- `name_match`: `BOOLEAN`, Nullable
- `dob_match`: `BOOLEAN`, Nullable
- `phone_match`: `BOOLEAN`, Nullable
- `verified_phone_masked`: `VARCHAR(20)`, Blank (e.g. `******1234`)
- `verified_at`: `TIMESTAMPTZ`, Nullable
- `failure_reason`: `TEXT`, Blank
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `customers_customerfeedback` (`customers.CustomerFeedback`)
Customer Net Promoter Score (NPS) and satisfaction ratings.
- `id`: `UUID`, Primary Key
- `user`: `FK -> accounts_user(id)`, ON DELETE CASCADE
- `nps_score`: `SMALLINT`, NOT NULL (0-10)
- `comment`: `TEXT`, Blank
- `submitted_at`: `TIMESTAMPTZ`, default `NOW()`

---

### 2.3 Staff & Organizational Governance

#### `staff_branch` (`staff.Branch`)
Internal operational office / branch registry.
- `id`: `UUID`, Primary Key
- `state`: `VARCHAR(100)`, NOT NULL
- `city`: `VARCHAR(100)`, NOT NULL
- `branch_opening_date`: `DATE`, Nullable
- `office_rent_cost`: `DECIMAL(12, 2)`, default `0.00`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `staff_staffprofile` (`staff.StaffProfile`)
Operational profile for an employee (`STAFF` role).
- `id`: `UUID`, Primary Key
- `user`: `OneToOne -> accounts_user(id)`, ON DELETE CASCADE, Unique
- `staff_code`: `VARCHAR(30)`, Unique, Indexed, NOT NULL (e.g. `UW-104`, `CH-201`)
- `first_name`: `VARCHAR(100)`, Blank
- `last_name`: `VARCHAR(100)`, Blank
- `department`: `VARCHAR(30)`, Choices: `['UNDERWRITING', 'CLAIMS']`, default `'UNDERWRITING'`
- `designation`: `VARCHAR(100)`, default `'Operational Specialist'`
- `phone_contact`: `VARCHAR(20)`, Blank
- `joining_date`: `DATE`, default `CURRENT_DATE`
- `status`: `VARCHAR(20)`, Choices: `['ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'INACTIVE']`, default `'ACTIVE'`
- `assigned_region`: `VARCHAR(100)`, default `'National'`
- `branch`: `FK -> staff_branch(id)`, ON DELETE SET NULL, Nullable
- `manager`: `FK -> self`, ON DELETE SET NULL, Nullable
- `employee_level`: `VARCHAR(30)`, default `'L1'`
- `performance_target`: `DECIMAL(12, 2)`, default `0.00`
- `max_claim_approval_limit`: `DECIMAL(12, 2)`, default `50000.00` (retained for backward compatibility)
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `staff_underwriterprofile` (`staff.UnderwriterProfile`)
Specialized parameters for Underwriting personnel.
- `id`: `UUID`, Primary Key
- `staff_profile`: `OneToOne -> staff_staffprofile(id)`, ON DELETE CASCADE, Unique
- `underwriting_limit`: `DECIMAL(12, 2)`, default `2500000.00` (IDV ceiling)
- `license_number`: `VARCHAR(50)`, Blank
- `specialization`: `VARCHAR(100)`, default `'General Motor'`
- `portfolio_name`: `VARCHAR(100)`, default `'Standard Personal Lines'`
- `approval_authority_level`: `VARCHAR(30)`, default `'STANDARD'`
- `status`: `VARCHAR(20)`, Choices: `['ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'INACTIVE']`, default `'ACTIVE'`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `staff_claimshandlerprofile` (`staff.ClaimsHandlerProfile`)
Specialized parameters for Claims Handlers.
- `id`: `UUID`, Primary Key
- `staff_profile`: `OneToOne -> staff_staffprofile(id)`, ON DELETE CASCADE, Unique
- `max_claim_approval_limit`: `DECIMAL(12, 2)`, default `50000.00` (Single claim payout limit)
- `active_claim_capacity`: `INTEGER`, default `25`
- `specialization_team`: `VARCHAR(100)`, default `'General Claims'`
- `status`: `VARCHAR(20)`, Choices: `['ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'INACTIVE']`, default `'ACTIVE'`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `staff_staffcustomerassignment` (`staff.StaffCustomerAssignment`)
Persistent relationship binding a staff member to an assigned customer.
- `id`: `UUID`, Primary Key
- `staff`: `FK -> accounts_user(id)`, ON DELETE CASCADE (Enforces `role='STAFF'`)
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE CASCADE
- `assigned_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable (Enforces `role='ADMIN'`)
- `assigned_at`: `TIMESTAMPTZ`, default `NOW()`
- `status`: `VARCHAR(20)`, Choices: `['ACTIVE', 'INACTIVE', 'TRANSFERRED']`, default `'ACTIVE'`
- `unassigned_at`: `TIMESTAMPTZ`, Nullable
- `assignment_reason`: `VARCHAR(255)`, Blank
- `notes`: `TEXT`, Blank
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update
- **Constraints**: `UniqueConstraint(fields=['customer'], condition=Q(status='ACTIVE'))` (A customer can have at most one active staff assignment at any given time).

---

### 2.4 Vehicles & Actuarial Assets

#### `vehicles_vehicle` (`vehicles.Vehicle`)
Registered automotive asset owned by a customer.
- `id`: `UUID`, Primary Key
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE CASCADE
- `registration_number`: `VARCHAR(20)`, Unique, Indexed, NOT NULL (e.g. `MH12AB1234`)
- `vehicle_type`: `VARCHAR(30)`, Choices: `['SEDAN', 'SUV', 'HATCHBACK', 'TRUCK', 'MOTORCYCLE', 'COMMERCIAL_VAN']`
- `make`: `VARCHAR(50)`, Indexed, NOT NULL
- `model`: `VARCHAR(50)`, NOT NULL
- `variant`: `VARCHAR(50)`, Blank
- `manufacture_year`: `INTEGER`, Indexed, NOT NULL
- `purchase_date`: `DATE`, Nullable
- `fuel_type`: `VARCHAR(20)`, Choices: `['PETROL', 'DIESEL', 'ELECTRIC', 'HYBRID', 'CNG']`
- `engine_number`: `VARCHAR(50)`, Blank
- `chassis_number`: `VARCHAR(50)`, Unique, Indexed, NOT NULL
- `vehicle_value`: `DECIMAL(12, 2)`, NOT NULL (Insured Declared Value - IDV)
- `usage_type`: `VARCHAR(20)`, Choices: `['PERSONAL', 'COMMERCIAL', 'RIDESHARE']`, default `'PERSONAL'`
- `registration_state`: `VARCHAR(100)`, Blank
- `registration_city`: `VARCHAR(100)`, Blank
- `owner_name`: `VARCHAR(150)`, Blank
- `registration_date`: `DATE`, Nullable
- `fitness_upto`: `DATE`, Nullable
- `insurance_upto`: `DATE`, Nullable
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `vehicles_vehiclemodelspec` (`vehicles.VehicleModelSpec`)
Catalog master specification entity for technical characteristics.
- `id`: `UUID`, Primary Key
- `make`: `VARCHAR(50)`, Indexed, NOT NULL
- `model`: `VARCHAR(50)`, Indexed, NOT NULL
- `variant`: `VARCHAR(50)`, Blank
- `segment`: `VARCHAR(50)`, Blank
- `fuel_type`: `VARCHAR(20)`, Blank
- `engine_type`: `VARCHAR(50)`, Blank
- `displacement`: `INTEGER`, Nullable
- `cylinder`: `INTEGER`, Nullable
- `transmission_type`: `VARCHAR(30)`, Blank
- `gear_box`: `VARCHAR(30)`, Blank
- `max_power`: `VARCHAR(50)`, Blank
- `max_torque`: `VARCHAR(50)`, Blank
- `gross_weight`: `INTEGER`, Nullable
- `length`: `INTEGER`, Nullable
- `width`: `INTEGER`, Nullable
- `height`: `INTEGER`, Nullable
- `airbags`: `INTEGER`, default `2`
- `is_esc`: `BOOLEAN`, default `FALSE`
- `is_tpms`: `BOOLEAN`, default `FALSE`
- `is_parking_sensors`: `BOOLEAN`, default `FALSE`
- `is_parking_camera`: `BOOLEAN`, default `FALSE`
- `ncap_rating`: `DECIMAL(3, 1)`, default `0.0`
- `base_price`: `DECIMAL(12, 2)`, default `0.00`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `vehicles_arearisk` (`vehicles.AreaRisk`)
Actuarial regional risk factor index.
- `id`: `UUID`, Primary Key
- `state`: `VARCHAR(100)`, NOT NULL
- `city`: `VARCHAR(100)`, NOT NULL
- `vehicle_theft_rate_area`: `DECIMAL(6, 4)`, default `0.0`
- `accident_hotspot_flag`: `BOOLEAN`, default `FALSE`
- `avg_repair_cost_area`: `DECIMAL(10, 2)`, default `0.00`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

---

### 2.5 Quotations, Plans & Features

#### `quotations_coverageplan` (`quotations.CoveragePlan`)
Insurance coverage offering baseline terms.
- `id`: `UUID`, Primary Key
- `plan_code`: `VARCHAR(50)`, Unique, NOT NULL
- `name`: `VARCHAR(100)`, NOT NULL
- `tagline`: `VARCHAR(255)`, Blank
- `description`: `TEXT`, NOT NULL
- `base_rate_percentage`: `DECIMAL(5, 3)`, NOT NULL (Annual rate as % of IDV)
- `standard_deductible`: `DECIMAL(10, 2)`, default `1000.00`
- `includes_own_damage`: `BOOLEAN`, default `TRUE`
- `includes_third_party`: `BOOLEAN`, default `TRUE`
- `includes_roadside_assistance`: `BOOLEAN`, default `FALSE`
- `includes_engine_protection`: `BOOLEAN`, default `FALSE`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `quotations_coveragefeature` (`quotations.CoverageFeature`)
Itemized coverage riders and plan features.
- `id`: `UUID`, Primary Key
- `plan`: `FK -> quotations_coverageplan(id)`, ON DELETE CASCADE
- `feature_code`: `VARCHAR(50)`, Indexed, NOT NULL
- `title`: `VARCHAR(150)`, NOT NULL
- `description`: `TEXT`, Blank
- `is_standard`: `BOOLEAN`, default `TRUE`
- `add_on_premium`: `DECIMAL(8, 2)`, default `0.00`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update
- **Constraints**: `UniqueConstraint(fields=['plan', 'feature_code'])`

#### `quotations_quotationdraft` (`quotations.QuotationDraft`)
Customer quotation estimate before purchase.
- `id`: `UUID`, Primary Key
- `quotation_number`: `VARCHAR(40)`, Unique, Indexed, NOT NULL (e.g. `QTE-2026-00123`)
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE SET NULL, Nullable
- `vehicle`: `FK -> vehicles_vehicle(id)`, ON DELETE SET NULL, Nullable
- `coverage_plan`: `FK -> quotations_coverageplan(id)`, ON DELETE PROTECT
- `assigned_staff`: `FK -> staff_staffprofile(id)`, ON DELETE SET NULL, Nullable
- `reviewed_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `created_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `vehicle_value`: `DECIMAL(12, 2)`, NOT NULL (IDV)
- `duration_years`: `INTEGER`, default `1` (1, 2, or 3)
- `base_premium`: `DECIMAL(10, 2)`, default `0.00`
- `addon_premium`: `DECIMAL(10, 2)`, default `0.00`
- `calculated_premium`: `DECIMAL(10, 2)`, NOT NULL
- `deductible_amount`: `DECIMAL(10, 2)`, NOT NULL
- `selected_features`: `M2M -> quotations_coveragefeature`
- `status`: `VARCHAR(20)`, Choices: `['DRAFT', 'ACCEPTED', 'EXPIRED', 'CONVERTED']`, default `'DRAFT'`
- `valid_until`: `TIMESTAMPTZ`, NOT NULL
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

---

### 2.6 Policies & Addons

#### `policies_policy` (`policies.Policy`)
Active legal insurance contract.
- `id`: `UUID`, Primary Key
- `policy_number`: `VARCHAR(40)`, Unique, Indexed, NOT NULL (e.g. `POL-2026-100234`)
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE PROTECT
- `vehicle`: `FK -> vehicles_vehicle(id)`, ON DELETE PROTECT
- `coverage_plan`: `FK -> quotations_coverageplan(id)`, ON DELETE PROTECT
- `assigned_staff`: `FK -> staff_staffprofile(id)`, ON DELETE SET NULL, Nullable
- `issued_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `premium_amount`: `DECIMAL(10, 2)`, NOT NULL (Locked)
- `deductible_amount`: `DECIMAL(10, 2)`, NOT NULL (Locked)
- `duration_years`: `INTEGER`, NOT NULL
- `start_date`: `DATE`, Indexed, NOT NULL
- `end_date`: `DATE`, Indexed, NOT NULL
- `status`: `VARCHAR(20)`, Choices: `['ACTIVE', 'LAPSED', 'CANCELLED', 'EXPIRED', 'RENEWED']`, default `'ACTIVE'`
- `previous_policy`: `FK -> self`, ON DELETE SET NULL, Nullable (Renewal lineage)
- `cancellation_reason`: `TEXT`, Blank
- `cancellation_date`: `DATE`, Nullable
- `renewal_date`: `DATE`, Nullable
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update
- **Constraints**: `CheckConstraint(check=Q(end_date__gt=F('start_date')))`

#### `policies_addon` (`policies.Addon`)
Rider / endorsement definition for policies.
- `id`: `UUID`, Primary Key
- `addon_name`: `VARCHAR(100)`, NOT NULL
- `addon_code`: `VARCHAR(50)`, Unique, NOT NULL
- `description`: `TEXT`, Blank
- `addon_cost`: `DECIMAL(10, 2)`, default `0.00`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `policies_policyaddon` (`policies.PolicyAddon`)
Explicit junction table binding purchased addons to a Policy.
- `id`: `UUID`, Primary Key
- `policy`: `FK -> policies_policy(id)`, ON DELETE CASCADE
- `addon`: `FK -> policies_addon(id)`, ON DELETE PROTECT
- `price_at_purchase`: `DECIMAL(10, 2)`, NOT NULL
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- **Constraints**: `UniqueConstraint(fields=['policy', 'addon'])`

---

### 2.7 Claims Management

#### `claims_claim` (`claims.Claim`)
Claim lifecycle record.
- `id`: `UUID`, Primary Key
- `claim_number`: `VARCHAR(40)`, Unique, Indexed, NOT NULL (e.g. `CLM-2026-00421`)
- `policy`: `FK -> policies_policy(id)`, ON DELETE PROTECT
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE PROTECT
- `handler`: `FK -> staff_staffprofile(id)`, ON DELETE SET NULL, Nullable
- `incident_date`: `TIMESTAMPTZ`, Indexed, NOT NULL
- `incident_location`: `VARCHAR(255)`, NOT NULL
- `incident_description`: `TEXT`, NOT NULL
- `claim_type`: `VARCHAR(30)`, Choices: `['ACCIDENT', 'THEFT', 'FIRE', 'NATURAL_DISASTER']`, default `'ACCIDENT'`
- `claim_severity`: `VARCHAR(30)`, default `'MODERATE'`
- `estimated_loss_amount`: `DECIMAL(12, 2)`, NOT NULL
- `approved_amount`: `DECIMAL(12, 2)`, Nullable
- `settlement_amount`: `DECIMAL(12, 2)`, Nullable
- `settlement_reference`: `VARCHAR(64)`, Blank
- `settled_at`: `TIMESTAMPTZ`, Nullable
- `rejection_reason`: `TEXT`, Blank
- `status`: `VARCHAR(20)`, Choices: `['PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'SETTLED']`, default `'PENDING'`
- `priority`: `VARCHAR(20)`, default `'MEDIUM'`
- `assigned_at`: `TIMESTAMPTZ`, Nullable
- `reviewed_at`: `TIMESTAMPTZ`, Nullable
- `resolved_at`: `TIMESTAMPTZ`, Nullable
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update
- **Constraints**: `CheckConstraint(check=~(Q(status='PENDING') & Q(handler__isnull=False)))`

#### `claims_claimdocument` (`claims.ClaimDocument`)
Supporting evidentiary documents for a claim.
- `id`: `UUID`, Primary Key
- `claim`: `FK -> claims_claim(id)`, ON DELETE CASCADE
- `document_type`: `VARCHAR(30)`, Choices: `['POLICE_REPORT', 'DAMAGE_PHOTO', 'REPAIR_ESTIMATE', 'DRIVING_LICENSE', 'OTHER']`
- `title`: `VARCHAR(150)`, NOT NULL
- `file`: `FileField`, upload path `claims/documents/%Y/%m/`
- `uploaded_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `verification_status`: `VARCHAR(30)`, default `'PENDING'`
- `verified_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `verified_at`: `TIMESTAMPTZ`, Nullable
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `claims_claimevent` (`claims.ClaimEvent`)
Append-only immutable audit trail for claim state transitions.
- `id`: `UUID`, Primary Key
- `claim`: `FK -> claims_claim(id)`, ON DELETE CASCADE
- `event_type`: `VARCHAR(40)`, NOT NULL
- `actor`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `actor_role`: `VARCHAR(30)`, Blank
- `notes`: `TEXT`, Blank
- `created_at`: `TIMESTAMPTZ`, default `NOW()`

---

### 2.8 Servicing & Payments

#### `service_requests_servicerequest` (`service_requests.ServiceRequest`)
Customer-initiated policy endorsements or support requests.
- `id`: `UUID`, Primary Key
- `request_number`: `VARCHAR(40)`, Unique, Indexed, NOT NULL (e.g. `SRV-2026-0010`)
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE CASCADE
- `policy`: `FK -> policies_policy(id)`, ON DELETE SET NULL, Nullable
- `request_type`: `VARCHAR(30)`, Choices: `['POLICY_RENEWAL', 'ADDRESS_UPDATE', 'CONTACT_UPDATE', 'VEHICLE_UPDATE', 'DOCUMENT_REQUEST', 'COVERAGE_CHANGE', 'ENDORSEMENT', 'OTHER']`
- `title`: `VARCHAR(200)`, NOT NULL
- `description`: `TEXT`, NOT NULL
- `status`: `VARCHAR(20)`, Choices: `['SUBMITTED', 'IN_PROGRESS', 'RESOLVED', 'REJECTED']`, default `'SUBMITTED'`
- `assigned_staff`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `assigned_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `change_payload`: `JSONField`, default `dict`
- `resolution_notes`: `TEXT`, Blank
- `resolved_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `resolved_at`: `TIMESTAMPTZ`, Nullable
- `priority`: `VARCHAR(20)`, default `'NORMAL'`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `payments_simulatedpayment` (`payments.SimulatedPayment`)
Demonstration card transaction entity.
- `id`: `UUID`, Primary Key
- `quotation`: `FK -> quotations_quotationdraft(id)`, ON DELETE SET NULL, Nullable
- `policy`: `FK -> policies_policy(id)`, ON DELETE SET NULL, Nullable
- `amount`: `DECIMAL(10, 2)`, NOT NULL
- `currency`: `VARCHAR(3)`, default `'INR'`
- `payment_method`: `VARCHAR(30)`, default `'CREDIT_CARD'`
- `card_network`: `VARCHAR(20)`, Choices: `['VISA', 'MASTERCARD', 'AMEX', 'DISCOVER', 'OTHER']`, default `'VISA'`
- `masked_card_number`: `VARCHAR(25)`, NOT NULL (e.g. `**** **** **** 4242`)
- `simulated_transaction_id`: `VARCHAR(50)`, Unique, Indexed, NOT NULL
- `is_successful`: `BOOLEAN`, default `TRUE`
- `simulated_gateway_response`: `JSONField`, default `dict`
- `disclaimer`: `TEXT`, default `'Simulated educational payment demonstration. No real funds or sensitive card data are processed.'`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

---

### 2.9 Machine Learning, Governance & Audit

#### `predictions_modelversion` (`predictions.ModelVersion`)
Model registry for trained ML models and shadow evaluation.
- `id`: `UUID`, Primary Key
- `model_name`: `VARCHAR(100)`, Indexed, NOT NULL
- `version`: `VARCHAR(50)`, Indexed, NOT NULL
- `algorithm_name`: `VARCHAR(100)`, NOT NULL
- `hyperparameters`: `JSONField`, default `dict`
- `evaluation_metrics`: `JSONField`, default `dict`
- `artifact_path`: `VARCHAR(255)`, NOT NULL
- `training_dataset_version`: `VARCHAR(50)`, default `'synthetic_v1'`
- `feature_version`: `VARCHAR(50)`, default `'v1.0'`
- `status`: `VARCHAR(30)`, Choices: `['TRAINED', 'EVALUATED', 'CANDIDATE', 'APPROVED', 'ACTIVE', 'RETIRED']`, default `'TRAINED'`
- `deployment_status`: `VARCHAR(50)`, default `'STAGING'`
- `is_active_for_inference`: `BOOLEAN`, default `FALSE`, Indexed
- `notes`: `TEXT`, Blank
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `predictions_predictionlog` (`predictions.PredictionLog`)
Inference execution log for model observability and decision support.
- `id`: `UUID`, Primary Key
- `model_version`: `FK -> predictions_modelversion(id)`, ON DELETE SET NULL, Nullable
- `prediction_type`: `VARCHAR(50)`, Indexed, NOT NULL
- `input_payload`: `JSONField`, default `dict` (Sanitized and masked)
- `output_result`: `JSONField`, default `dict`
- `confidence_or_probability`: `FLOAT`, Nullable
- `latency_ms`: `FLOAT`, default `0.0`
- `is_successful`: `BOOLEAN`, default `TRUE`
- `error_message`: `TEXT`, Blank
- `disclaimer`: `TEXT`, default `'ML estimation signal only. Not an automated claim decision.'`
- `requested_by`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `recommendations_coveragerecommendation` (`recommendations.CoverageRecommendation`)
Explainable coverage recommendations for vehicles.
- `id`: `UUID`, Primary Key
- `customer`: `FK -> customers_customerprofile(id)`, ON DELETE SET NULL, Nullable
- `vehicle`: `FK -> vehicles_vehicle(id)`, ON DELETE SET NULL, Nullable
- `recommended_plan`: `FK -> quotations_coverageplan(id)`, ON DELETE PROTECT
- `alternative_plan`: `FK -> quotations_coverageplan(id)`, ON DELETE SET NULL, Nullable
- `confidence_score`: `DECIMAL(5, 2)`, NOT NULL (0.00 to 100.00)
- `rationale`: `TEXT`, NOT NULL
- `assumptions`: `TEXT`, NOT NULL
- `disclaimer`: `TEXT`, default `'Educational decision support only. Not guaranteed financial or statutory insurance advice.'`
- `generated_by_model`: `VARCHAR(100)`, Blank
- `model_version`: `FK -> predictions_modelversion(id)`, ON DELETE SET NULL, Nullable
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `audit_auditlog` (`audit.AuditLog`)
Append-only, immutable regulatory ledger.
- `id`: `UUID`, Primary Key
- `actor`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `actor_email`: `VARCHAR(254)`, Blank
- `actor_role`: `VARCHAR(30)`, Choices: `['USER', 'STAFF/UNDERWRITING', 'STAFF/CLAIMS', 'ADMIN']`
- `action`: `VARCHAR(50)`, Indexed, NOT NULL
- `target_entity`: `VARCHAR(100)`, Blank
- `target_id`: `VARCHAR(64)`, Blank
- `details`: `JSONField`, default `dict` (Strictly excludes raw passwords, OTPs, full PANs)
- `ip_address`: `GenericIPAddressField`, Nullable
- `is_success`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`

---

### 2.10 RAG & Conversational Assistant

#### `rag_knowledgedocument` (`rag.KnowledgeDocument`)
Approved source policy documentation for RAG.
- `id`: `UUID`, Primary Key
- `title`: `VARCHAR(200)`, Unique, NOT NULL
- `category`: `VARCHAR(40)`, NOT NULL
- `version`: `VARCHAR(20)`, default `'1.0'`
- `source_reference`: `VARCHAR(255)`, NOT NULL
- `is_approved_for_rag`: `BOOLEAN`, default `TRUE`, Indexed
- `content_raw`: `TEXT`, NOT NULL
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `rag_knowledgechunk` (`rag.KnowledgeChunk`)
Text segments mapped to vector embeddings.
- `id`: `UUID`, Primary Key
- `document`: `FK -> rag_knowledgedocument(id)`, ON DELETE CASCADE
- `chunk_index`: `INTEGER`, NOT NULL
- `content`: `TEXT`, NOT NULL
- `token_count`: `INTEGER`, default `0`
- `supabase_embedding_id`: `VARCHAR(64)`, Blank
- `metadata`: `JSONField`, default `dict`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `chatbot_chatsession` (`chatbot.ChatSession`)
User conversation session with pending transaction state.
- `id`: `UUID`, Primary Key
- `user`: `FK -> accounts_user(id)`, ON DELETE SET NULL, Nullable
- `session_key`: `VARCHAR(64)`, Indexed, NOT NULL
- `title`: `VARCHAR(150)`, default `'Vehicle Insurance Assistance'`
- `pending_transaction`: `JSONField`, Nullable
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `chatbot_chatmessage` (`chatbot.ChatMessage`)
Individual conversational turn.
- `id`: `UUID`, Primary Key
- `session`: `FK -> chatbot_chatsession(id)`, ON DELETE CASCADE
- `sender`: `VARCHAR(20)`, Choices: `['USER', 'ASSISTANT', 'SYSTEM']`
- `content`: `TEXT`, NOT NULL
- `sources`: `JSONField`, default `list`
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `chatbot_chatbottoolcall` (`chatbot.ChatbotToolCall`)
Guardrailed service invocation ledger.
- `id`: `UUID`, Primary Key
- `session`: `FK -> chatbot_chatsession(id)`, ON DELETE CASCADE
- `tool_name`: `VARCHAR(100)`, NOT NULL
- `parameters`: `JSONField`, default `dict`
- `execution_status`: `VARCHAR(30)`, NOT NULL
- `result_payload`: `JSONField`, default `dict`
- `guardrail_notes`: `TEXT`, Blank
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update

#### `core_notification` (`core.Notification`)
In-app notifications for alerts and policy updates.
- `id`: `UUID`, Primary Key
- `recipient`: `FK -> accounts_user(id)`, ON DELETE CASCADE
- `title`: `VARCHAR(150)`, NOT NULL
- `message`: `TEXT`, NOT NULL
- `notification_type`: `VARCHAR(30)`, Choices: `['RENEWAL_REMINDER', 'CLAIM_STATUS', 'SERVICE_UPDATE', 'SECURITY_ALERT', 'GENERAL']`
- `is_read`: `BOOLEAN`, default `FALSE`, Indexed
- `action_url`: `VARCHAR(255)`, Blank
- `is_active`: `BOOLEAN`, default `TRUE`
- `created_at`: `TIMESTAMPTZ`, default `NOW()`
- `updated_at`: `TIMESTAMPTZ`, auto-update
