-- ============================================================
-- 016: Geliştirici API Anahtarları & Mağaza Doğrulama Rozeti
-- ============================================================
-- app/security.py::require_api_key ve app/main.py'daki
-- /api/admin/api-keys/* ve /api/admin/stores/*/verify uçları
-- bu tabloları Supabase REST üzerinden doğrudan kullanıyor.
-- ============================================================

-- ── 1. Geliştirici API Anahtarları ──────────────────────────

CREATE TABLE IF NOT EXISTS api_keys (
    id          SERIAL PRIMARY KEY,
    key_hash    TEXT UNIQUE NOT NULL,       -- sha256(ham anahtar) -- ham anahtar hiç saklanmaz
    label       TEXT NOT NULL,
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE active = TRUE;

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY api_keys_service ON api_keys FOR ALL USING (auth.role() = 'service_role');

-- ── 2. Mağaza Doğrulama Rozeti ──────────────────────────────

CREATE TABLE IF NOT EXISTS verified_stores (
    slug        TEXT PRIMARY KEY,
    verified    BOOLEAN DEFAULT TRUE,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE verified_stores ENABLE ROW LEVEL SECURITY;

CREATE POLICY verified_stores_public_read ON verified_stores
    FOR SELECT USING (TRUE);

CREATE POLICY verified_stores_service ON verified_stores
    FOR ALL USING (auth.role() = 'service_role');
