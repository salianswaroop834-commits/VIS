# NEXISURE VEHICLE INSURANCE PLATFORM — BUSINESS REQUIREMENTS DOCUMENT (BRD)

**Document Version**: 2.0  
**Status**: Approved / Production Specification  
**Domain**: Automotive Insurance (InsurTech)  
**Currency Standard**: Indian Rupees (INR / ₹)  
**Target Market**: Indian Motor Insurance Ecosystem (Personal & Commercial Fleet Segments)  

---

## 1. Business Problem Statement

Traditional automotive insurance in India is plagued by four critical operational pain points:

1. **Slow and Friction-Heavy Policy Issuance**: Customers face cumbersome manual form-filling, slow vehicle identification, and non-transparent pricing that creates high drop-off rates during policy onboarding.
2. **Opaque Actuarial Underwriting**: Risk tiering and pricing adjustments are traditionally locked in manual actuarial tables or proprietary black-box calculations, with zero explainability provided to customers or underwriters.
3. **High Loss Adjustment Expense (LAE) & Claims Friction**: Adjudication workflows are fragmented across manual spreadsheets and emails. Unstructured document intake and lack of real-time risk scoring cause prolonged claim settlement cycles (averaging 15–30 days industry-wide).
4. **Knowledge Hallucination & Conversational Risk**: AI chatbots in financial services often hallucinate coverage clauses, promise non-existent coverage, or execute unintended state changes without explicit customer authorization.

**Nexisure** addresses these challenges by delivering a cohesive, modular-monolith InsurTech platform that bridges automated external registry verification (VAHAN/RapidAPI), explainable machine learning decision-support, strict human-in-the-loop claim adjudication, and dual-boundary-defended RAG conversational assistance.

---

## 2. Key Stakeholders

| Stakeholder Group | Organizational Role | Core Responsibilities & Interests |
|---|---|---|
| **Executive Leadership** | Chief Executive Officer, Chief Risk Officer | Overall business sustainability, combined ratio, regulatory compliance, investor ROI. |
| **Underwriting Team** | Head Underwriter, Actuarial Analysts | Risk assessment, policy terms, custom rating rules, loss ratio monitoring. |
| **Claims Operations** | Claims Managers, Field Surveyors | Incident review, fraud detection, loss assessment, settlement disbursement within authority limits. |
| **Compliance & Legal** | IRDAI Compliance Officer, Legal Counsel | Statutory motor liability enforcement, non-repudiation audit trails, data privacy. |
| **Engineering & AI** | Lead Architect, MLOps Engineers | Platform availability, vector search precision, prompt injection safety, model drift telemetry. |

---

## 3. Target Users

1. **Retail Vehicle Owners (Customers)**:
   - Individual car and two-wheeler owners seeking fast digital coverage, paperless KYC, self-service claim filing, and real-time claim status tracking.
2. **Commercial Fleet Operators**:
   - Small-to-medium enterprise owners managing multiple commercial or rideshare vehicles with standardized pricing and fleet policy tracking.
3. **Underwriters (Internal Staff)**:
   - Licensed insurance specialists reviewing high-value policy applications, approving bespoke endorsements, and monitoring portfolio loss ratios.
4. **Claims Handlers (Internal Staff)**:
   - Adjudication officers reviewing loss evidence, damage estimates, surveyor notes, and approving settlements up to authorized monetary ceilings.
5. **Platform Administrators**:
   - System operators managing user roles, staff assignments, operational KPIs, and inspecting immutable audit logs.

---

## 4. Primary Beneficiaries

- **Policyholders**: Experience transparent, instant digital quotes with IDV depreciation visibility, instantaneous policy certificate generation (PDF), and frictionless claim progress alerts.
- **Insurers**: Achieve substantial reductions in Loss Adjustment Expense (LAE), lower customer acquisition costs (CAC), and eliminated unauthorized claim leakage via mandatory human approval limits.
- **Third Parties & Garages**: Receive accelerated settlement disbursements backed by clear reference numbers and structured damage documentation.

---

## 5. Value Proposition

| Dimension | Legacy Insurance Model | NexiSure Digital Platform |
|---|---|---|
| **Vehicle Onboarding** | Manual entry of 20+ vehicle attributes | Automated 2-step VAHAN registry lookup + chassis verification |
| **Customer KYC** | Physical photo upload & branch visit | 2-step PAN format validation + masked registry phone match + OTP |
| **Quotation & Pricing** | Fixed opaque tables | Dynamic actuarial formula with multi-year discounts & add-on riders |
| **Underwriting AI** | Unchecked automated black box | Dual ML models (probability + severity) with feature attribution & shadow mode |
| **Claims Adjudication** | Fragmented manual email queues | Shared pending queue, self-assignment, financial authority caps, human-only approval |
| **Customer Assistance** | Static FAQ or hallucinating bots | pgvector-grounded RAG with exact clause citations & prompt-injection defense |

---

## 6. Strategic Business Objectives

1. **Reduce Time-to-Issue (TTI)**: Enable customers to complete registration, KYC, quote selection, and policy issuance in under **5 minutes**.
2. **Accelerate Claim Turnaround Time (TAT)**: Reduce average claim processing from industry-average 21 days to under **48 hours** for standard comprehensive claims.
3. **Enforce 100% Non-Repudiation**: Guarantee that every state-changing action (KYC, vehicle registration, quotation, payment, policy issuance, claim filing, settlement) is logged in an append-only audit trail.
4. **Zero AI Financial Autonomy**: Maintain strict human-in-the-loop governance: AI provides decision support; licensed human handlers make all final claim decisions.
5. **Zero Regulatory Non-Compliance**: Provide full transparency with IRDAI-standard statutory disclaimers, clear INR formatting, and downloadable motor insurance certificates.

---

## 7. Key Performance Indicators (KPIs)

### 7.1 Commercial & Operational KPIs
- **Loss Ratio (LR)**: Target $\le 65\%$ across comprehensive and zero depreciation portfolios.
- **Combined Ratio**: Target $\le 92\%$ including operational expenses.
- **Quotation-to-Policy Conversion Rate**: Target $\ge 28\%$.
- **Average Claim Settlement Days**: Target $\le 3$ business days.
- **Net Promoter Score (NPS)**: Target $\ge 70$ via built-in customer feedback collection.

### 7.2 Technical & Safety KPIs
- **Test Suite Pass Rate**: 100% green builds (currently 289/289 tests passing).
- **RAG Groundedness & Citation Rate**: 100% of generated policy answers must cite official documentation or safely refuse.
- **Prompt Injection Neutralization Rate**: 100% of adversarial jailbreak and system-override attempts blocked before execution.
- **Payment Idempotency**: Zero duplicate policy issuances from repeated payment submissions.

---

## 8. Risks & Mitigation Strategies

| Risk Description | Severity | Likelihood | Mitigation Strategy |
|---|---|---|---|
| **Adversarial Prompt Injection in Chatbot/RAG** | High | Medium | Regex heuristic filter blocks injection patterns; XML `<untrusted_insurance_knowledge>` tags isolate data from instructions. |
| **Unauthorized Automated Claim Approval** | Critical | Low | Hard architectural boundary: no API or AI tool can approve claims. Handlers must review in portal with financial discretion ceilings. |
| **External Registry (RapidAPI/VAHAN) Outage** | Medium | Medium | Provider abstraction with automatic deterministic fallback simulation catalog (38 synthetic Indian vehicles). |
| **Credit Card / Payment Fraud** | High | Low | Modulo-10 Luhn validation, test card network classification, zero raw card/CVV storage, masked PAN/cards in logs. |
| **IDOR / Unauthorized Object Access** | High | Low | Strict object-level customer isolation in views; `CustomerRequiredMixin` and `ClaimsHandlerRequiredMixin` on all sensitive endpoints. |

---

## 9. Product Roadmap

```
Phase 1: Foundation (COMPLETED)
├── Modular-monolith Django architecture
├── 16 cohesive domain apps
├── Database schemas & Supabase RLS specifications
└── 289 automated unit and integration tests

Phase 2: Core Insurance Lifecycle (COMPLETED)
├── 2-step VAHAN vehicle registry lookup & chassis verification
├── 2-factor PAN KYC with phone match & Firebase OTP abstraction
├── Actuarial quotation engine with multi-year discounts & add-ons
├── Simulated payment gateway with Luhn validation & idempotency
├── PDF Certificate of Motor Insurance generation
└── Human-in-the-loop claims queue with authority limits

Phase 3: AI, MLOps & RAG Intelligence (COMPLETED)
├── Dual-model ML inference (Gradient Boosting classifier + Ridge regressor)
├── Feature importance attribution & plain-language explainability
├── MLOps model registry with shadow mode evaluation
├── Semantic RAG policy search with citations & out-of-scope fallback
├── Unsafe RAG demonstration proving prompt injection boundary defense
└── Stateful conversational assistant with two-step transactional confirmation

Phase 4: Future Scale & Enterprise Integrations (PLANNED)
├── Live VAHAN API enterprise direct integration (NIC gateway)
├── Real-time IoT OBD-II telematics ingestion for usage-based insurance (UBI)
├── Computer vision AI for automated vehicular damage estimation
└── Multi-lingual vernacular support for regional Indian languages
```

---

## 10. Business Pitch & Executive Value Case

> *"In an industry where buying car insurance takes hours and settling a claim takes weeks, **Nexisure** reimagines automotive insurance from the ground up. By fusing instant government registry lookup, explainable machine learning underwriting, and human-in-the-loop claim adjudication, Nexisure eliminates operational friction while upholding 100% regulatory compliance. Our platform empowers policyholders with transparent, self-service digital coverage while arming underwriters and claims handlers with auditable, explainable decision-support intelligence."*
