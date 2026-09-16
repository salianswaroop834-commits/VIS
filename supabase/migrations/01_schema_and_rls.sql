-- ==============================================================================
-- Nexisure Vehicle Insurance Platform - Supabase PostgreSQL Schema & RLS
-- PostgreSQL 15+ compatible with pgvector extension
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. HELPER FUNCTIONS FOR JWT ROLE EXTRACTION
CREATE OR REPLACE FUNCTION auth.jwt_role() 
RETURNS TEXT AS $$
BEGIN
    RETURN COALESCE(
        current_setting('request.jwt.claim.role', true),
        (current_setting('request.jwt.claims', true)::jsonb -> 'user_metadata' ->> 'role'),
        'ANONYMOUS'
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- 3. CORE IDENTITY & PROFILES
CREATE TABLE IF NOT EXISTS customer_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    customer_code VARCHAR(30) NOT NULL UNIQUE,
    date_of_birth DATE,
    driving_license_number VARCHAR(50),
    address_line VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    postal_code VARCHAR(20),
    is_identity_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_customer_profiles_user ON customer_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_customer_profiles_code ON customer_profiles(customer_code);

CREATE TABLE IF NOT EXISTS staff_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    staff_code VARCHAR(30) NOT NULL UNIQUE,
    role VARCHAR(30) NOT NULL CHECK (role IN ('UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR')),
    department VARCHAR(100) DEFAULT 'Underwriting',
    max_claim_approval_limit NUMERIC(12, 2) DEFAULT 50000.00,
    assigned_region VARCHAR(100) DEFAULT 'National',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_staff_profiles_user ON staff_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_staff_profiles_code ON staff_profiles(staff_code);
CREATE INDEX IF NOT EXISTS idx_staff_profiles_role ON staff_profiles(role);

-- 4. VEHICLES
CREATE TABLE IF NOT EXISTS vehicles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customer_profiles(id) ON DELETE CASCADE,
    registration_number VARCHAR(20) NOT NULL UNIQUE,
    vehicle_type VARCHAR(30) NOT NULL,
    make VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    manufacture_year INT NOT NULL,
    fuel_type VARCHAR(20) NOT NULL,
    engine_number VARCHAR(50),
    chassis_number VARCHAR(50) NOT NULL UNIQUE,
    vehicle_value NUMERIC(12, 2) NOT NULL CHECK (vehicle_value > 0),
    usage_type VARCHAR(20) DEFAULT 'PERSONAL',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vehicles_customer ON vehicles(customer_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_reg ON vehicles(registration_number);

-- 5. COVERAGE PLANS & QUOTATIONS
CREATE TABLE IF NOT EXISTS coverage_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    tagline VARCHAR(255),
    description TEXT NOT NULL,
    base_rate_percentage NUMERIC(5, 3) NOT NULL,
    standard_deductible NUMERIC(10, 2) DEFAULT 1000.00,
    includes_own_damage BOOLEAN DEFAULT TRUE,
    includes_third_party BOOLEAN DEFAULT TRUE,
    includes_roadside_assistance BOOLEAN DEFAULT FALSE,
    includes_engine_protection BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quotation_drafts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quotation_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id UUID REFERENCES customer_profiles(id) ON DELETE SET NULL,
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
    coverage_plan_id UUID NOT NULL REFERENCES coverage_plans(id) ON DELETE RESTRICT,
    vehicle_value NUMERIC(12, 2) NOT NULL,
    duration_years INT NOT NULL DEFAULT 1 CHECK (duration_years IN (1, 2, 3)),
    calculated_premium NUMERIC(10, 2) NOT NULL,
    deductible_amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    valid_until TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_quotations_customer ON quotation_drafts(customer_id);
CREATE INDEX IF NOT EXISTS idx_quotations_status ON quotation_drafts(status);

-- 6. POLICIES & RENEWAL LINEAGE
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    policy_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES customer_profiles(id) ON DELETE RESTRICT,
    vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    coverage_plan_id UUID NOT NULL REFERENCES coverage_plans(id) ON DELETE RESTRICT,
    underwriter_id UUID REFERENCES staff_profiles(id) ON DELETE SET NULL,
    premium_amount NUMERIC(10, 2) NOT NULL CHECK (premium_amount > 0),
    deductible_amount NUMERIC(10, 2) NOT NULL,
    duration_years INT NOT NULL CHECK (duration_years IN (1, 2, 3)),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'CANCELLED', 'RENEWED')),
    previous_policy_id UUID REFERENCES policies(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_policy_dates CHECK (end_date > start_date)
);
CREATE INDEX IF NOT EXISTS idx_policies_customer ON policies(customer_id);
CREATE INDEX IF NOT EXISTS idx_policies_vehicle ON policies(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_policies_underwriter ON policies(underwriter_id);
CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status);
CREATE INDEX IF NOT EXISTS idx_policies_dates ON policies(start_date, end_date);

-- 7. CLAIMS & SHARED WORKFLOW QUEUE
CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_number VARCHAR(40) NOT NULL UNIQUE,
    policy_id UUID NOT NULL REFERENCES policies(id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES customer_profiles(id) ON DELETE RESTRICT,
    handler_id UUID REFERENCES staff_profiles(id) ON DELETE SET NULL,
    incident_date TIMESTAMPTZ NOT NULL,
    incident_location VARCHAR(255) NOT NULL,
    incident_description TEXT NOT NULL,
    estimated_loss_amount NUMERIC(12, 2) NOT NULL CHECK (estimated_loss_amount > 0),
    settlement_amount NUMERIC(12, 2),
    rejection_reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_claims_policy ON claims(policy_id);
CREATE INDEX IF NOT EXISTS idx_claims_customer ON claims(customer_id);
CREATE INDEX IF NOT EXISTS idx_claims_handler ON claims(handler_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);

CREATE TABLE IF NOT EXISTS claim_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    document_type VARCHAR(30) NOT NULL,
    title VARCHAR(150) NOT NULL,
    file_path TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_claim_docs_claim ON claim_documents(claim_id);

CREATE TABLE IF NOT EXISTS claim_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL,
    actor_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_role VARCHAR(30) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_claim_events_claim ON claim_events(claim_id);

-- 8. SERVICE REQUESTS & RECOMMENDATIONS
CREATE TABLE IF NOT EXISTS service_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES customer_profiles(id) ON DELETE CASCADE,
    policy_id UUID REFERENCES policies(id) ON DELETE SET NULL,
    request_type VARCHAR(30) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'SUBMITTED' CHECK (status IN ('SUBMITTED', 'IN_PROGRESS', 'RESOLVED', 'REJECTED')),
    assigned_staff_id UUID REFERENCES staff_profiles(id) ON DELETE SET NULL,
    resolution_notes TEXT,
    resolved_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_service_requests_customer ON service_requests(customer_id);
CREATE INDEX IF NOT EXISTS idx_service_requests_status ON service_requests(status);

CREATE TABLE IF NOT EXISTS coverage_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID REFERENCES customer_profiles(id) ON DELETE SET NULL,
    vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
    recommended_plan_id UUID NOT NULL REFERENCES coverage_plans(id) ON DELETE RESTRICT,
    alternative_plan_id UUID REFERENCES coverage_plans(id) ON DELETE SET NULL,
    confidence_score NUMERIC(5, 2) NOT NULL,
    rationale TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    disclaimer TEXT DEFAULT 'Educational decision support only.',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. AUDIT LOG & COMPLIANCE
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_email VARCHAR(255),
    actor_role VARCHAR(50),
    action VARCHAR(60) NOT NULL,
    target_entity VARCHAR(60) NOT NULL,
    target_id VARCHAR(64) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    is_success BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON audit_logs(target_entity, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);

-- 10. RAG KNOWLEDGE BASE WITH PGVECTOR
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(200) NOT NULL UNIQUE,
    category VARCHAR(40) NOT NULL,
    version VARCHAR(20) DEFAULT '1.0',
    source_reference VARCHAR(255),
    is_approved_for_rag BOOLEAN DEFAULT TRUE,
    content_raw TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    token_count INT DEFAULT 0,
    embedding VECTOR(1536), -- Standard embedding dimension for OpenAI / compatible vector models
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc ON knowledge_chunks(document_id);
-- HNSW vector similarity search index using Cosine distance
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding 
ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- 11. NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(30) DEFAULT 'GENERAL',
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);

-- ==============================================================================
-- 12. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

-- Enable RLS on all operational tables
ALTER TABLE customer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE quotation_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE coverage_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------------------------
-- CUSTOMER POLICIES: Customers can only access their own records
-- ------------------------------------------------------------------------------

-- Customer Profiles: User owns their profile; Staff can view for underwriting/claims
CREATE POLICY customer_read_own_profile ON customer_profiles
    FOR SELECT USING (
        user_id = auth.uid() OR 
        auth.jwt_role() IN ('UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR')
    );

CREATE POLICY customer_update_own_profile ON customer_profiles
    FOR UPDATE USING (user_id = auth.uid());

-- Vehicles: Customer can read/insert/update their own vehicles; Staff can read
CREATE POLICY customer_vehicles_select ON vehicles
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.jwt_role() IN ('UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR')
    );

CREATE POLICY customer_vehicles_insert ON vehicles
    FOR INSERT WITH CHECK (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );

CREATE POLICY customer_vehicles_update ON vehicles
    FOR UPDATE USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );

-- Policies: Customers can only view their own policies.
-- Underwriters can view & insert policies.
CREATE POLICY policies_select ON policies
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.jwt_role() IN ('UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR')
    );

CREATE POLICY policies_underwriter_insert ON policies
    FOR INSERT WITH CHECK (
        auth.jwt_role() IN ('UNDERWRITER', 'ADMINISTRATOR')
    );

CREATE POLICY policies_underwriter_update ON policies
    FOR UPDATE USING (
        auth.jwt_role() IN ('UNDERWRITER', 'ADMINISTRATOR')
    );

-- Claims:
-- 1. Customer can view their own claims.
-- 2. Customer can insert new claims against their active policies.
-- 3. Claims Handler can view unassigned pending claims (shared queue) OR claims assigned to themselves.
-- 4. Claims Handler can update only assigned claims.
CREATE POLICY claims_select_customer ON claims
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );

CREATE POLICY claims_select_handler ON claims
    FOR SELECT USING (
        auth.jwt_role() = 'CLAIMS_HANDLER' AND (
            handler_id IS NULL OR -- Shared unassigned pending queue
            handler_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid())
        ) OR
        auth.jwt_role() = 'ADMINISTRATOR'
    );

CREATE POLICY claims_insert_customer ON claims
    FOR INSERT WITH CHECK (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) AND
        status = 'PENDING' AND
        handler_id IS NULL -- Customer can never assign the handler
    );

CREATE POLICY claims_update_handler ON claims
    FOR UPDATE USING (
        (
            auth.jwt_role() = 'CLAIMS_HANDLER' AND
            (
                handler_id IS NULL OR -- Picking up unassigned claim
                handler_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid())
            )
        ) OR
        auth.jwt_role() = 'ADMINISTRATOR'
    );

-- Notifications: Users only see their own notifications
CREATE POLICY notifications_user_isolation ON notifications
    FOR ALL USING (user_id = auth.uid());

-- Audit Logs: Insertable by system/authenticated users, viewable by Administrator only
CREATE POLICY audit_logs_insert_all ON audit_logs
    FOR INSERT WITH CHECK (TRUE);

CREATE POLICY audit_logs_select_admin ON audit_logs
    FOR SELECT USING (auth.jwt_role() = 'ADMINISTRATOR');
