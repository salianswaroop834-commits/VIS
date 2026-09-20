-- ==============================================================================
-- Nexisure Vehicle Insurance Platform
-- Canonical Supabase PostgreSQL Row Level Security (RLS) & Isolation Policies
-- ==============================================================================
-- Architecture: 3-Role Foundation (USER, STAFF, ADMIN)
-- Data Isolation: Staff can only access Customer data if actively assigned via
--                 staff_customer_assignments or if they underwrote the policy/claim.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. EXTENSIONS & ROLE HELPER FUNCTIONS
-- ------------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Helper to extract canonical role from Supabase JWT: 'USER', 'STAFF', or 'ADMIN'
CREATE OR REPLACE FUNCTION auth.canonical_role()
RETURNS TEXT AS $$
BEGIN
    RETURN COALESCE(
        current_setting('request.jwt.claim.role', true),
        (current_setting('request.jwt.claims', true)::jsonb -> 'user_metadata' ->> 'role'),
        'ANONYMOUS'
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- Helper to check if current authenticated user is an active assigned staff member for a customer
CREATE OR REPLACE FUNCTION auth.is_assigned_staff_for_customer(p_customer_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    -- Administrators have universal tenant access
    IF auth.canonical_role() = 'ADMIN' THEN
        RETURN TRUE;
    END IF;

    -- Check if authenticated staff has an ACTIVE assignment for this customer
    RETURN EXISTS (
        SELECT 1 
        FROM staff_customer_assignments sca
        JOIN staff_profiles sp ON sca.staff_id = sp.id
        WHERE sca.customer_id = p_customer_id
          AND sca.status = 'ACTIVE'
          AND sp.user_id = auth.uid()
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- ------------------------------------------------------------------------------
-- 2. ENABLE RLS ON CANONICAL TABLES
-- ------------------------------------------------------------------------------
ALTER TABLE IF EXISTS staff_customer_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS customer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS kyc_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS customer_feedbacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS staff_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS underwriter_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS claims_handler_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS branches ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS vehicle_model_specs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS area_risks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS quotation_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS claims ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------------------------
-- 3. STAFF CUSTOMER ASSIGNMENTS POLICIES
-- ------------------------------------------------------------------------------
-- Select:
-- - Staff can view assignments assigned to them.
-- - Customers can view their own assignment history.
-- - Admins can view all assignments.
DROP POLICY IF EXISTS sca_select_policy ON staff_customer_assignments;
CREATE POLICY sca_select_policy ON staff_customer_assignments
    FOR SELECT USING (
        auth.canonical_role() = 'ADMIN' OR
        staff_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid()) OR
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );

-- Insert/Update: Only Administrators can create or reassign customer assignments
DROP POLICY IF EXISTS sca_admin_manage ON staff_customer_assignments;
CREATE POLICY sca_admin_manage ON staff_customer_assignments
    FOR ALL USING (
        auth.canonical_role() = 'ADMIN'
    );

-- ------------------------------------------------------------------------------
-- 4. CUSTOMER PROFILES & KYC VERIFICATION POLICIES
-- ------------------------------------------------------------------------------
-- Customer Profiles:
-- - Customer reads their own profile.
-- - Assigned Staff can read customer profiles for their active assignments.
-- - Admins read all profiles.
DROP POLICY IF EXISTS customer_profiles_isolation ON customer_profiles;
CREATE POLICY customer_profiles_isolation ON customer_profiles
    FOR SELECT USING (
        user_id = auth.uid() OR
        auth.is_assigned_staff_for_customer(id) OR
        auth.canonical_role() = 'ADMIN'
    );

DROP POLICY IF EXISTS customer_profiles_update_own ON customer_profiles;
CREATE POLICY customer_profiles_update_own ON customer_profiles
    FOR UPDATE USING (
        user_id = auth.uid() OR
        auth.canonical_role() = 'ADMIN'
    );

-- KYC Verifications:
-- - Customer can view their own verification attempts.
-- - Assigned staff or admins can review customer KYC verification status.
DROP POLICY IF EXISTS kyc_verification_select ON kyc_verifications;
CREATE POLICY kyc_verification_select ON kyc_verifications
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.is_assigned_staff_for_customer(customer_id) OR
        auth.canonical_role() = 'ADMIN'
    );

DROP POLICY IF EXISTS kyc_verification_insert_customer ON kyc_verifications;
CREATE POLICY kyc_verification_insert_customer ON kyc_verifications
    FOR INSERT WITH CHECK (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );

-- ------------------------------------------------------------------------------
-- 5. VEHICLE & ASSET POLICIES
-- ------------------------------------------------------------------------------
-- Vehicle Specs & Area Risks are public reference catalogs for authenticated users
DROP POLICY IF EXISTS vehicle_specs_public_read ON vehicle_model_specs;
CREATE POLICY vehicle_specs_public_read ON vehicle_model_specs
    FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS area_risks_public_read ON area_risks;
CREATE POLICY area_risks_public_read ON area_risks
    FOR SELECT USING (TRUE);

-- Registered Customer Vehicles:
-- - Customer reads/writes their own vehicles.
-- - Assigned Staff can view vehicles belonging to their assigned customers.
-- - Admins read all vehicles.
DROP POLICY IF EXISTS vehicles_isolation_select ON vehicles;
CREATE POLICY vehicles_isolation_select ON vehicles
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.is_assigned_staff_for_customer(customer_id) OR
        auth.canonical_role() = 'ADMIN'
    );

DROP POLICY IF EXISTS vehicles_isolation_write ON vehicles;
CREATE POLICY vehicles_isolation_write ON vehicles
    FOR INSERT WITH CHECK (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS vehicles_isolation_update ON vehicles;
CREATE POLICY vehicles_isolation_update ON vehicles
    FOR UPDATE USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.canonical_role() = 'ADMIN'
    );

-- ------------------------------------------------------------------------------
-- 6. POLICIES & QUOTATIONS WITH DATA ISOLATION
-- ------------------------------------------------------------------------------
-- Quotation Drafts:
-- - Customer views drafts they requested.
-- - Assigned Staff views drafts for their assigned customers or assigned underwriter.
-- - Admins view all drafts.
DROP POLICY IF EXISTS quotation_drafts_isolation ON quotation_drafts;
CREATE POLICY quotation_drafts_isolation ON quotation_drafts
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.is_assigned_staff_for_customer(customer_id) OR
        assigned_staff_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid()) OR
        auth.canonical_role() = 'ADMIN'
    );

-- Insurance Policies:
-- - Customer views only their active/bound policies.
-- - Assigned staff views policies of assigned customers or policies where they are assigned_staff.
-- - Staff with underwriting authority can update/bind policies.
DROP POLICY IF EXISTS policies_canonical_select ON policies;
CREATE POLICY policies_canonical_select ON policies
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.is_assigned_staff_for_customer(customer_id) OR
        assigned_staff_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid()) OR
        auth.canonical_role() = 'ADMIN'
    );

DROP POLICY IF EXISTS policies_canonical_staff_manage ON policies;
CREATE POLICY policies_canonical_staff_manage ON policies
    FOR ALL USING (
        (
            auth.canonical_role() = 'STAFF' AND
            EXISTS (
                SELECT 1 FROM underwriter_profiles up
                JOIN staff_profiles sp ON up.staff_profile_id = sp.id
                WHERE sp.user_id = auth.uid()
            ) AND (
                assigned_staff_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid()) OR
                auth.is_assigned_staff_for_customer(customer_id)
            )
        ) OR
        auth.canonical_role() = 'ADMIN'
    );

-- ------------------------------------------------------------------------------
-- 7. CLAIMS PROCESSING & DATA GOVERNANCE
-- ------------------------------------------------------------------------------
-- Claims:
-- - Customer views their own claims.
-- - Claims Handlers view claims assigned to them or unassigned claims in their region.
-- - Assigned Staff for customer can view claim status.
-- - Admin has full visibility and control.
DROP POLICY IF EXISTS claims_canonical_select ON claims;
CREATE POLICY claims_canonical_select ON claims
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.is_assigned_staff_for_customer(customer_id) OR
        handler_id IS NULL OR
        handler_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid()) OR
        auth.canonical_role() = 'ADMIN'
    );

DROP POLICY IF EXISTS claims_canonical_handler_update ON claims;
CREATE POLICY claims_canonical_handler_update ON claims
    FOR UPDATE USING (
        (
            auth.canonical_role() = 'STAFF' AND
            (
                handler_id IS NULL OR
                handler_id IN (SELECT id FROM staff_profiles WHERE user_id = auth.uid())
            )
        ) OR
        auth.canonical_role() = 'ADMIN'
    );

-- ------------------------------------------------------------------------------
-- 8. CUSTOMER FEEDBACK
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS customer_feedback_select ON customer_feedbacks;
CREATE POLICY customer_feedback_select ON customer_feedbacks
    FOR SELECT USING (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid()) OR
        auth.canonical_role() IN ('STAFF', 'ADMIN')
    );

DROP POLICY IF EXISTS customer_feedback_insert ON customer_feedbacks;
CREATE POLICY customer_feedback_insert ON customer_feedbacks
    FOR INSERT WITH CHECK (
        customer_id IN (SELECT id FROM customer_profiles WHERE user_id = auth.uid())
    );
