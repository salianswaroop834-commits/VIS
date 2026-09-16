# NEXISURE VEHICLE INSURANCE PLATFORM: COMPREHENSIVE PITCH & ARCHITECTURAL SPECIFICATION

## 1. Executive Summary & Problem Statement
Traditional automotive insurance management suffers from severe operational bottlenecks:
1. **Opaque Underwriting**: Actuarial risk assessment is frequently locked in legacy mainframe black-boxes or manual spreadsheets.
2. **Unchecked Automation vs. Regulatory Compliance**: Modern AI implementations in insurance often overstep regulatory boundaries by automating claim rejections or denying coverage without human explainability or due process.
3. **Data Fragmentation**: Policy administration, claims adjudication, customer servicing, and predictive modeling operate in isolated silos, leading to high loss adjustment expenses (LAE) and customer churn.
4. **Knowledge Retrieval Hallucination**: Conversational agents in finance often fabricate policy clauses, hallucinate coverage benefits, or fall prey to adversarial prompt injection.

**Nexisure** solves these challenges through a unified, modular-monolith Django platform that pairs database-backed actuarial analytics with responsible, explainable machine learning decision-support, strict human-in-the-loop claim adjudication, pgvector-grounded RAG retrieval, and secured transactional conversational tools.

---

## 2. Platform Architecture & Technology Stack

### 2.1 Monolithic Architecture with Domain Modularity
Nexisure rejects distributed microservice overhead in favor of a clean, highly cohesive Django modular monolith:
- **Core Engine**: Django 5.x & Django REST Framework
- **Database & Auth**: Supabase PostgreSQL with `pgvector` extension for vector embeddings (SQLite compatibility mode enabled for zero-dependency academic evaluation)
- **Machine Learning**: Scikit-Learn pipelines, standard normalization, feature interactions, joblib serialization, and isolated candidate shadow evaluation
- **Explainability**: Deterministic feature attribution and plain-language reasoning
- **Frontend Presentation**: Responsive Bootstrap 5 with server-side rendered Django templates and Vanilla CSS design tokens
- **Financial Standard**: Strictly formatted in Indian Rupees (INR / ₹) across all entities, forms, calculations, and UI displays

### 2.2 Layered Security & Authorization Architecture
Every state-changing operation traverses a mandatory six-tier defense:
```
1. Authentication (Supabase / Django Session)
       ↓
2. Role & Multi-Tenant Ownership Authorization (RBAC & Customer Ownership)
       ↓
3. Domain Validation (Business Rules, Temporal Bounds, Financial Bounds)
       ↓
4. Service Layer Execution (Django Services & Transactions)
       ↓
5. Database Constraints & Row-Level Security
       ↓
6. Non-Repudiation Audit Logging (Immutable Ledger)
```

---

## 3. Core Insurance Workflows

### 3.1 Customer Self-Service Lifecycle
- **Asset Registration**: Normalizes vehicle registration plates, validates IDV bounds against age depreciation schedules, and records usage profiles (Personal, Commercial, Rideshare).
- **Plan Selection & Actuarial Quotation**: Provides instantaneous premium calculations across statutory Third-Party Liability, Comprehensive, and Zero Depreciation plans with optional add-on riders.
- **Simulated Payment Gateway**: Tests Luhn algorithm checksums, identifies card brand networks (Visa, Mastercard, Amex, Discover), and issues active policies upon verified transaction authorization.
- **Policy Contract Lock**: Once issued, contractual financial fields (`premium_amount`, `deductible_amount`, `policy_number`) are permanently locked against unauthorized tampering.
- **Servicing & Claims**: Registered policyholders can track active coverage, file servicing endorsements, or initiate incident claims into the shared queue.

### 3.2 Human-in-the-Loop Claims Adjudication
- **Mandatory Human Discretion**: Machine learning risk scores and estimated damage severities serve strictly as decision-support signals. Automated claim approvals, rejections, or settlement adjustments are strictly forbidden.
- **Shared Queue & Self-Assignment**: Claims enter an unassigned `PENDING` queue. Authorized claims handlers self-assign claims to move them into `IN_REVIEW`.
- **Financial Authority Limits**: Handlers cannot approve settlements exceeding their individually configured approval discretion ceiling (e.g., ₹50,000 for standard handlers; ₹1,000,000 for executive administrators).
- **IDV Capping**: Payouts cannot exceed the vehicle's Insured Declared Value.

---

## 4. Responsible AI, MLOps & RAG Integration

### 4.1 Explainable Decision-Support Models
- **Claim Occurrence Model**: Calibrated Gradient Boosting Classifier evaluating historical risk factors (driver age, vehicle age, urban exposure, usage classification) to output risk probabilities and risk tier bands (LOW, MODERATE, ELEVATED, HIGH).
- **Claim Severity Regressor**: Random Forest Regressor estimating potential loss severity bounded by the vehicle's IDV.
- **Explainability Factors**: Every inference generates plain-language, human-readable explanations (e.g., *"Vehicle age and urban usage contributed to elevated risk score"*).

### 4.2 Academic MLOps Governance
- **Controlled Lifecycle Progression**:
  $$\text{TRAINED} \longrightarrow \text{EVALUATED} \longrightarrow \text{CANDIDATE} \longrightarrow \text{APPROVED} \longrightarrow \text{ACTIVE} \longrightarrow \text{RETIRED}$$
- **Role Enforcement**: Only authorized staff/admin personnel can promote models.
- **Shadow Mode**: Candidate models can be evaluated against live payloads in isolated shadow mode with zero influence on active business contracts.
- **Drift Telemetry**: Tracks feature central tendencies, prediction tier shifts, and payload missing-value rates.

### 4.3 Grounded RAG & Prompt-Injection-Defended Assistant
- **Curated Knowledge Base**: Policy clauses, exclusions, endorsements, and deductible rules stored as approved documents (`is_approved_for_rag=True`). Unapproved drafts are strictly excluded from retrieval.
- **Grounded Attribution**: Responses cite exact source document titles.
- **Prompt Injection Defense**: Multi-pattern regex filters block prompt injections, jailbreak attempts, rule overrides, and SQL injection syntax.
- **Controlled Transactional Tools**: Conversational tool calling executes strictly through existing Django service layers with two-step customer confirmation for state-changing operations.

---

## 5. Limitations & Future Scope
- **Synthetic Data**: Trained on synthetic automotive portfolios modeled after Indian market parameters.
- **Simulated Financial Gateway**: Luhn validation is implemented without real card processing.
- **Local Fallback Adapters**: Clean abstraction interfaces provide in-memory/cosine similarity vector retrieval and deterministic LLM fallbacks when external cloud infrastructure is absent.
- **Future Scope**: Direct telematics IoT ingestion, real-time computer vision damage assessment, and live Supabase PostgreSQL RLS policy verification in production cloud clusters.
