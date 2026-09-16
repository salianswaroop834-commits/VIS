# NEXISURE: COMPREHENSIVE VIVA TECHNICAL DEFENSE & EXAMINER FAQ

This document prepares candidates for technical viva, evaluation, and rigorous architectural examination on the Nexisure platform.

---

### Q1: Why Django instead of FastAPI, Flask, or Node.js?
**Defense**:
- Django provides "batteries-included" enterprise primitives essential for insurance platforms: an ACID-compliant ORM with robust migration management, built-in CSRF/XSS protection, session and authentication frameworks, form validation, and transactional support (`transaction.atomic`).
- While FastAPI is lightweight for microservices, an insurance core requires tight coupling between relational schemas, domain validation, and transactional audit trails. Django ensures cohesive domain boundaries without maintaining dozens of disparate third-party libraries.

### Q2: Why a Modular Monolith instead of Microservices?
**Defense**:
- Microservices introduce distributed transaction complexity (two-phase commits, saga patterns, eventual consistency, network partition risks, and distributed tracing overhead). In insurance, financial operations—such as accepting a quotation and issuing a policy—must be strictly atomic.
- A modular monolith delivers clean domain isolation (`policies`, `claims`, `quotations`, `vehicles`, `audit`, `ml`, `rag`) within a single deployable unit. Modules interact via explicit Python service/selector interfaces rather than network RPCs, ensuring maximum throughput, zero network latency, and strict transaction rollback guarantees.

### Q3: Why Supabase and PostgreSQL?
**Defense**:
- Supabase provides a managed, cloud-native PostgreSQL infrastructure with Row-Level Security (RLS), cryptographic UUID primary keys, and extensible schemas.
- PostgreSQL is the gold-standard relational database for financial services due to its strict ACID compliance, advanced constraint checks (e.g. `CheckConstraint` on policy dates), partial indexes, and native extensions like `pgvector`.

### Q4: Why pgvector for knowledge retrieval?
**Defense**:
- Dedicated vector databases (Pinecone, Milvus, Weaviate) introduce operational fragmentation: embeddings live in one database while document metadata and user permissions live in another, requiring dual-writes and distributed synchronization.
- `pgvector` brings vector similarity search directly into the relational database. A single query can perform vector similarity ranking while filtering on relational metadata (e.g. `is_approved_for_rag = True`), preventing synchronization lag and reducing infrastructure overhead.

### Q5: Why Retrieval-Augmented Generation (RAG)?
**Defense**:
- Large Language Models (LLMs) suffer from hallucinations and knowledge cutoff dates. An insurance assistant cannot invent policy terms, deductibles, or coverage exclusions.
- RAG grounds conversational responses in curated, approved policy documents. The model is constrained to generate answers using only retrieved knowledge chunks, complete with verified citations, guaranteeing factual fidelity.

### Q6: Why Machine Learning, and why keep it as "Decision Support Only"?
**Defense**:
- ML excels at multi-dimensional pattern recognition across non-linear risk factors (driver experience, vehicle depreciation, urban traffic density, safety ratings) to estimate risk probabilities and damage severities.
- However, insurance is a highly regulated domain subject to consumer protection laws (e.g., IRDAI in India, Solvency II, GDPR Article 22). Automated denial of coverage or automated claim rejections without human review is legally and ethically unacceptable. Keeping ML strictly as decision-support preserves human accountability while augmenting handler efficiency.

### Q7: Why Human-in-the-Loop for Claim Decisions?
**Defense**:
- Claims adjudication requires contextual judgment: inspecting photographic damage evidence, reviewing surveyor reports, evaluating circumstantial credibility, and applying discretionary good-faith exceptions.
- In Nexisure, claims handlers possess assigned authority limits. Claims can only be approved or rejected by authenticated human staff, ensuring legal accountability and preventing adversarial gaming of automated algorithms.

### Q8: Why Immutable Audit Logs?
**Defense**:
- Regulatory compliance mandates non-repudiation: every state-changing event (policy issuance, claim approval, handler assignment, model promotion) must be permanently logged.
- The `AuditLog` entity records the actor, IP address, timestamp, target entity, action, and detailed payload. Audit logs cannot be updated or deleted via application views or services.

### Q9: How does Role-Based Access Control (RBAC) work in Nexisure?
**Defense**:
- Authentication verifies identity; RBAC enforces authorization.
- `accounts.User` maintains an authoritative `role` field (`CUSTOMER`, `UNDERWRITER`, `CLAIMS_HANDLER`, `ADMINISTRATOR`).
- View and service-level access is enforced through custom mixins (`CustomerRequiredMixin`, `UnderwriterRequiredMixin`, `ClaimsHandlerRequiredMixin`, `AdminRequiredMixin`) that inspect the verified user instance. Client-provided role inputs are never trusted.

### Q10: How is Insecure Direct Object Reference (IDOR) prevented?
**Defense**:
- IDOR occurs when an application exposes a reference to an internal object without verifying that the requesting user owns that object.
- In Nexisure, customer endpoints never query solely by primary key (e.g. `Policy.objects.get(id=pk)`). All queries strictly enforce ownership filtering through the authenticated user's profile: `Policy.objects.filter(customer=request.user.customer_profile, id=pk)`. Cross-user inspection attempts return HTTP 403 Forbidden or 404 Not Found.

### Q11: How do Claims work end-to-end?
**Defense**:
1. **Filing**: Authenticated customer files a claim against an active policy owned by them. Incident date is validated to ensure it falls within the policy term. The claim enters `PENDING` status with no handler assigned (shared queue).
2. **Self-Assignment**: A claims handler self-assigns the claim, transitioning it to `IN_REVIEW`.
3. **Adjudication**: The handler reviews estimates, IDV caps, and deductible rules, then approves or rejects the claim. If approved, a settlement payout is authorized within the handler's maximum discretion limit.

### Q12: How does Policy Renewal work without data mutation?
**Defense**:
- An expired policy must never be silently overwritten, as historical policy terms are legally binding contracts.
- Nexisure implements lineage tracking: renewing a policy creates a completely new `Policy` instance referencing the past policy via a `previous_policy` self-referencing foreign key, setting status to `RENEWED` while preserving the historical contract intact.

### Q13: How do Model Versioning and Promotions work in MLOps?
**Defense**:
- `predictions.ModelVersion` tracks algorithm, version string, training dataset version, feature version, and evaluation metrics (accuracy, precision, recall, F1, ROC-AUC, MAE, RMSE).
- Models progress through explicit lifecycle states: `TRAINED` $\to$ `EVALUATED` $\to$ `CANDIDATE` $\to$ `APPROVED` $\to$ `ACTIVE` $\to$ `RETIRED`.
- Transitions require staff/admin authorization and disk artifact verification. Activating a model atomically retires the previously active model.

### Q14: How are Chatbot Tools secured against abuse?
**Defense**:
- The conversational assistant is strictly prohibited from executing raw SQL queries or accessing the database directly.
- The assistant can only invoke approved, deterministic Python functions wrapping existing Django service layers.
- Every tool invocation validates the caller's session ownership and authentication credentials before executing.
- State-changing operations (such as registering a claim) follow a mandatory two-step staging and explicit customer confirmation protocol.

### Q15: How is Prompt Injection defended against?
**Defense**:
- Inbound user prompts are scanned by multi-pattern regex guardrails before being passed to RAG retrieval or LLM generation.
- Common adversarial patterns—such as instruction overrides (`ignore previous instructions`), credential theft, jailbreaks, and SQL injection syntax (`DROP TABLE`, `UNION SELECT`)—are intercepted and deflected with an automated security notice and audit log entry.
- Direct prompt attempts to force claim approval (e.g., *"Approve my claim now"*) trigger an immediate claim decision guardrail deflection notice.

### Q16: Why Synthetic Data?
**Defense**:
- Real automotive insurance datasets contain Protected Health Information (PHI) and Personally Identifiable Information (PII) subject to stringent regulatory privacy protections.
- Synthetic data allows realistic statistical modeling of Indian automotive insurance distributions (IDVs from ₹50,000 to ₹8,500,000, risk zones, anti-theft equipment, age-based loss curves) without violating data privacy laws.

### Q17: What are the current academic limitations?
**Defense**:
- **Payment Processing**: Educational simulation featuring Luhn algorithm validation without live banking gateway integrations.
- **Local Fallback Adapters**: When external cloud services (Supabase pgvector clusters or paid LLM APIs) are not connected, the platform gracefully switches to local in-memory cosine similarity and deterministic fallback providers.
- **Hardware Acceleration**: Model inference and training are optimized for local CPU execution.
