# Nexisure Vehicle Insurance Management & Responsible Decision-Support Platform

Nexisure is an enterprise-grade vehicle insurance management and responsible decision-support platform built on a modular-monolith Django architecture with a PostgreSQL/Supabase database and auth foundation.

The platform provides end-to-end policy lifecycle management, claim adjudication with strict human-in-the-loop governance, portfolio exploratory data analysis (EDA), explainable machine learning decision-support, academic MLOps model lifecycle governance, grounded Retrieval-Augmented Generation (RAG) knowledge retrieval, and a responsible AI assistant with controlled transactional tool execution.

---

## 1. Architectural Principles & Technology Stack

- **Application Framework**: Django 5.x (Modular Monolith) with Django REST Framework for API endpoints.
- **Database Foundation**: Supabase PostgreSQL with `pgvector` extension for vector embeddings (SQLite compatibility mode enabled for local academic development).
- **Authentication**: Supabase Auth integration paired with Django application-level Role-Based Access Control (RBAC).
- **Machine Learning**: Scikit-Learn pipelines, standard normalization, feature interactions, joblib serialization, and isolated candidate shadow evaluation.
- **Explainability**: Deterministic feature attribution and plain-language reasoning (strictly decision-support; automated approvals/rejections are prohibited).
- **Knowledge Retrieval (RAG)**: Chunking pipeline with vector similarity retrieval strictly restricted to approved insurance policy documents.
- **Conversational Assistant**: Multi-turn session persistence, prompt injection defenses, arbitrary SQL rejection, and controlled transactional tools invoking Django services.
- **Currency Standard**: All monetary values are strictly formatted in Indian Rupees (INR / ₹).

---

## 2. Role Governance & Permissions Hierarchy

Nexisure enforces strict multi-tenant customer isolation and role segregation:

| Role | Permitted Workflows | Access Boundaries |
| :--- | :--- | :--- |
| **CUSTOMER** | Vehicle registration, quotation comparison, policy purchase, certificate download, claim filing, service requests, AI assistant | Only own profile, vehicles, policies, claims, and chat sessions. |
| **UNDERWRITER** | Quotation review, custom policy issuance, endorsement approval, portfolio analytics, ML risk assessment | Policy issuance and risk metrics. Cannot adjudicate or settle claims. |
| **CLAIMS_HANDLER**| Shared queue inspection, self-assignment, evidence review, human claim adjudication, settlement payout within limit | Only assigned claims. Cannot exceed financial approval discretion limit. |
| **ADMINISTRATOR** | System governance, staff roster, compliance audit ledger, MLOps model promotion, knowledge document approval | Global administration and compliance auditing. |

---

## 3. End-to-End Workflow Lifecycles

### 3.1 Customer Insurance Journey
1. **Vehicle Registration**: Register vehicle asset with IDV valuation, fuel type, usage type, and chassis number.
2. **Quotation & Plan Comparison**: Select coverage tier (Third-Party Liability, Comprehensive, Zero Depreciation) and optional add-on riders.
3. **Simulated Payment**: Checkout with Luhn-validated credit/debit card.
4. **Policy Issuance**: Automated contract issuance, locked financial fields, and certificate generation.
5. **Claims Lifecycle**: Incident filing into unassigned shared queue with location and damage estimates.
6. **Policy Servicing**: Address change, vehicle detail correction, and renewal requests.

### 3.2 Human-in-the-Loop Claim Adjudication
1. **Filing**: Claim enters `PENDING` shared queue.
2. **Self-Assignment**: Claims handler self-assigns claim, moving status to `IN_REVIEW`.
3. **Human Review**: Handler verifies damage estimates against policy deductible and vehicle IDV.
4. **Adjudication**: Handler formally approves or rejects claim. Settlement payouts are strictly bounded by the handler's authority limit.
5. **AI Guardrail**: AI assistant is strictly prohibited from approving, rejecting, or altering settlements.

---

## 4. Machine Learning & MLOps Lifecycle

- **Feature Pipeline**: Zero-leakage preprocessing using standard scalers, categorical encoders, and interaction terms.
- **Claim Probability Model**: Calibrated probability estimates for underwriting decision-support.
- **Claim Severity Model**: Bounded damage cost estimates based on IDV and vehicle parameters.
- **Model Registry Statuses**:
  $$\text{TRAINED} \longrightarrow \text{EVALUATED} \longrightarrow \text{CANDIDATE} \longrightarrow \text{APPROVED} \longrightarrow \text{ACTIVE} \longrightarrow \text{RETIRED}$$
- **Governance**: Only authorized staff/admin personnel can promote models. All promotions are written to immutable audit logs.

---

## 5. Grounded RAG & Controlled AI Assistant

- **Knowledge Documents**: Policy clauses, exclusions, deductibles, and endorsement guidelines. Only documents with `is_approved_for_rag=True` are retrieved.
- **Prompt Injection Defense**: Guardrail filters detect and reject instruction bypasses (`ignore previous instructions`), credential theft, and arbitrary SQL syntax (`DROP TABLE`, `UNION SELECT`).
- **Controlled Tools**: The assistant interacts with the system exclusively through Django services:
  - `get_my_policies`
  - `get_my_vehicles`
  - `get_my_service_requests`
  - `get_my_quotations`
  - `check_claim_status`
  - `prepare_claim_registration` & `confirm_transaction` (Two-step explicit customer confirmation)

---

## 6. Setup & Local Development Instructions

### Prerequisites
- Python 3.11+
- Virtual environment (`venv`)

### Installation
```bash
# 1. Clone the repository and enter the directory
cd d:/VIS

# 2. Activate virtual environment
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run database migrations
python manage.py migrate

# 5. Seed default insurance coverage plans and knowledge corpus
python manage.py shell -c "from quotations.services.quotation_service import QuotationService; QuotationService.seed_default_plans(); from rag.services.rag_service import RagService; RagService.ingest_corpus()"

# 6. Execute system check
python manage.py check

# 7. Run full test regression suite
pytest -q
```

---

## 7. Demo Seed Mechanism

A synthetic demo seed command is available to populate sample entities for presentation and viva:
```bash
python manage.py seed_demo_data
```
The command seeds:
- Administrator (`admin@nexisure.test`)
- Underwriter (`underwriter@nexisure.test`)
- Claims Handler (`handler@nexisure.test`)
- Customer (`customer@nexisure.test`)
- Vehicles, quotations, active policies, pending/in-review claims, and audit logs.

---

## 8. Limitations & Environment Notes

1. **Synthetic Training Data**: Actuarial analytics and ML models are trained on synthetic vehicle insurance distributions modeled after Indian market parameters.
2. **Local Vector Store Fallback**: Uses an in-memory/cosine similarity vector adapter when external PostgreSQL `pgvector` connections are not configured.
3. **Live LLM Fallback**: When external LLM API keys (`AI_PROVIDER_API_KEY`) are absent, the system uses a deterministic, grounded fallback provider ensuring 100% citation grounding and safe tool execution.
4. **Simulated Payments**: Payment processing is an educational simulation featuring Luhn algorithm validation without real card transactions.
