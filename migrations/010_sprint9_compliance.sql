-- ============================================================
-- Sprint 9: GDPR/KVKK Uyumluluk & Final
-- ============================================================
-- Çalıştırma sırası: 010 (009'dan sonra)
-- ============================================================

-- ── 1. GDPR Talep Audit Logu ─────────────────────────────────
CREATE TABLE IF NOT EXISTS gdpr_requests (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,
    request_type    TEXT NOT NULL,   -- 'forget', 'export', 'consent'
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending, completed, partial, failed
    details         JSONB DEFAULT '{}',
    requested_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_gdpr_user   ON gdpr_requests(user_id, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_gdpr_type   ON gdpr_requests(request_type, status);

-- ── 2. Onay Yönetimi (Consent) ────────────────────────────────
CREATE TABLE IF NOT EXISTS user_consents (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,
    consent_type    TEXT NOT NULL,   -- 'marketing', 'analytics', 'push', 'data_sharing'
    granted         BOOLEAN NOT NULL DEFAULT FALSE,
    ip_hash         TEXT,            -- SHA-256 ilk 16 karakter (IP log için)
    user_agent_hash TEXT,
    granted_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, consent_type)
);

-- ── 3. Veri Saklama Politikası Metadata ──────────────────────
CREATE TABLE IF NOT EXISTS data_retention_policy (
    table_name      TEXT PRIMARY KEY,
    retention_days  INT NOT NULL,
    anonymize       BOOLEAN DEFAULT FALSE,   -- silmek yerine anonimleştir
    last_cleanup_at TIMESTAMPTZ,
    notes           TEXT
);

-- Politika kayıtları
INSERT INTO data_retention_policy (table_name, retention_days, anonymize, notes) VALUES
    ('request_metrics',         30,  false, 'Otomatik cleanup cron var'),
    ('structured_logs',          7,  false, 'debug/info 7 gun, error/critical 30 gun'),
    ('user_analytics_events',  365,  true,  'KVKK: 1 yil sonra anonimlestirilir'),
    ('user_savings',           365,  false, 'Kullanici sildiginde kaldirilir'),
    ('vision_analyses',         90,  false, 'Goruntu analizi 90 gun saklanir'),
    ('chaos_experiments',       30,  false, 'Test logu 30 gun')
ON CONFLICT (table_name) DO NOTHING;

-- ── 4. RLS ───────────────────────────────────────────────────
ALTER TABLE gdpr_requests        ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_consents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_retention_policy ENABLE ROW LEVEL SECURITY;

-- gdpr_requests: kullanıcı kendi talebini görebilir, servis rolü her şeyi
CREATE POLICY gdpr_user_read ON gdpr_requests FOR SELECT
    USING (auth.uid() = user_id OR auth.role() = 'service_role');

CREATE POLICY gdpr_service_all ON gdpr_requests FOR ALL
    USING (auth.role() = 'service_role');

-- user_consents: kullanıcı kendi onaylarını yönetir
CREATE POLICY consent_user_all ON user_consents FOR ALL
    USING (auth.uid() = user_id OR auth.role() = 'service_role');

-- data_retention_policy: sadece service_role
CREATE POLICY drp_service ON data_retention_policy FOR ALL
    USING (auth.role() = 'service_role');
