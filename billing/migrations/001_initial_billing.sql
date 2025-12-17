-- =============================================================================
-- CITATEGENIE BILLING SCHEMA
-- =============================================================================
-- Provider-agnostic billing system
-- Run this on a fresh PostgreSQL database
--
-- Tables:
--   - users: User accounts with email/password auth
--   - orders: Purchase records
--   - payment_events: Webhook idempotency
--   - credit_ledger: Credit transaction history
--   - app_sessions: Database-backed sessions
--   - provider_price_map: Product → Provider price mappings
--   - user_discounts: Per-user discount codes
--
-- Version: 2025-12-17
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- USERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    
    -- Authentication
    email           VARCHAR(500) UNIQUE NOT NULL,
    password_hash   VARCHAR(200) NOT NULL,
    
    -- Profile
    name            VARCHAR(200),
    
    -- Status
    is_active       BOOLEAN DEFAULT TRUE,
    is_admin        BOOLEAN DEFAULT FALSE,
    email_verified  BOOLEAN DEFAULT FALSE,
    
    -- Stats
    total_documents INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at   TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- =============================================================================
-- ORDERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- User
    user_id             INTEGER NOT NULL REFERENCES users(id),
    
    -- Product
    product_code        VARCHAR(50) NOT NULL,
    credits_granted     INTEGER NOT NULL,
    
    -- Provider info (provider-agnostic)
    provider            VARCHAR(50) NOT NULL,
    provider_ref        VARCHAR(200),
    provider_payment_id VARCHAR(200),
    
    -- Status
    status              VARCHAR(50) DEFAULT 'created',
    
    -- Money
    amount_cents        INTEGER NOT NULL,
    currency            VARCHAR(3) DEFAULT 'USD',
    
    -- Timestamps
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at             TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_provider_ref ON orders(provider, provider_ref);

-- =============================================================================
-- PAYMENT EVENTS (Webhook Idempotency)
-- =============================================================================

CREATE TABLE IF NOT EXISTS payment_events (
    id                  SERIAL PRIMARY KEY,
    
    -- Provider info
    provider            VARCHAR(50) NOT NULL,
    provider_event_id   VARCHAR(200) NOT NULL,
    
    -- Event details
    event_type          VARCHAR(100),
    payload_json        JSONB,
    
    -- Processing status
    processed           BOOLEAN DEFAULT FALSE,
    error_message       TEXT,
    
    -- Timestamps
    received_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at        TIMESTAMP WITH TIME ZONE,
    
    -- Unique constraint for idempotency
    UNIQUE(provider, provider_event_id)
);

-- =============================================================================
-- CREDIT LEDGER
-- =============================================================================

CREATE TABLE IF NOT EXISTS credit_ledger (
    id              SERIAL PRIMARY KEY,
    
    -- Who
    user_id         INTEGER NOT NULL REFERENCES users(id),
    
    -- What
    delta           INTEGER NOT NULL,
    reason          VARCHAR(100) NOT NULL,
    
    -- Related order
    order_id        UUID REFERENCES orders(id),
    
    -- Balance snapshot
    balance_after   INTEGER,
    
    -- Notes
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    
    -- Timestamp
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_ledger_user ON credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created ON credit_ledger(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_order ON credit_ledger(order_id) WHERE order_id IS NOT NULL;

-- =============================================================================
-- APP SESSIONS (Database-backed for Fargate)
-- =============================================================================

CREATE TABLE IF NOT EXISTS app_sessions (
    id              VARCHAR(100) PRIMARY KEY,
    
    -- Optional user association
    user_id         INTEGER REFERENCES users(id),
    
    -- Session data
    data            JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at      TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_user ON app_sessions(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_app_sessions_expires ON app_sessions(expires_at);

-- =============================================================================
-- PROVIDER PRICE MAP
-- =============================================================================

CREATE TABLE IF NOT EXISTS provider_price_map (
    id                  SERIAL PRIMARY KEY,
    
    provider            VARCHAR(50) NOT NULL,
    product_code        VARCHAR(50) NOT NULL,
    provider_price_id   VARCHAR(200) NOT NULL,
    
    -- Timestamps
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(provider, product_code)
);

-- =============================================================================
-- USER DISCOUNTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_discounts (
    id              SERIAL PRIMARY KEY,
    
    user_id         INTEGER NOT NULL REFERENCES users(id),
    
    -- Discount type
    discount_type   VARCHAR(50) NOT NULL,
    discount_value  INTEGER NOT NULL,
    
    -- Scope
    product_code    VARCHAR(50),
    
    -- Usage limits
    max_uses        INTEGER,
    times_used      INTEGER DEFAULT 0,
    
    -- Validity
    valid_from      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    valid_until     TIMESTAMP WITH TIME ZONE,
    is_active       BOOLEAN DEFAULT TRUE,
    
    -- Notes
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    
    -- Timestamps
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_discounts_user ON user_discounts(user_id);
CREATE INDEX IF NOT EXISTS idx_user_discounts_active ON user_discounts(user_id, is_active) WHERE is_active = TRUE;

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to get user's credit balance
CREATE OR REPLACE FUNCTION get_user_balance(p_user_id INTEGER)
RETURNS INTEGER AS $$
    SELECT COALESCE(SUM(delta), 0)::INTEGER
    FROM credit_ledger
    WHERE user_id = p_user_id;
$$ LANGUAGE SQL STABLE;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for app_sessions
DROP TRIGGER IF EXISTS trigger_app_sessions_updated ON app_sessions;
CREATE TRIGGER trigger_app_sessions_updated
    BEFORE UPDATE ON app_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- CLEANUP JOB (run periodically)
-- =============================================================================

-- Delete expired sessions (call this from a cron job or scheduled task)
-- DELETE FROM app_sessions WHERE expires_at < NOW();

-- =============================================================================
-- SAMPLE QUERIES
-- =============================================================================

-- Get user balance:
-- SELECT get_user_balance(1);

-- Get user's recent transactions:
-- SELECT * FROM credit_ledger WHERE user_id = 1 ORDER BY created_at DESC LIMIT 10;

-- Get user's orders:
-- SELECT * FROM orders WHERE user_id = 1 ORDER BY created_at DESC;

-- Get total revenue:
-- SELECT SUM(amount_cents) / 100.0 AS revenue_dollars
-- FROM orders WHERE status = 'paid';

-- Get conversion rate:
-- SELECT 
--     COUNT(*) FILTER (WHERE status = 'paid') AS paid,
--     COUNT(*) AS total,
--     ROUND(COUNT(*) FILTER (WHERE status = 'paid') * 100.0 / NULLIF(COUNT(*), 0), 2) AS conversion_rate
-- FROM orders;
