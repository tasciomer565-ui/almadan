-- ============================================================
-- Sprint 7: Ekosistem & İş Ortaklığı
-- ============================================================
-- Çalıştırma sırası: 008 (007'den sonra)
-- ============================================================

-- ── 1. Partner API Gateway ───────────────────────────────────

CREATE TABLE IF NOT EXISTS partner_api_keys (
    id              SERIAL PRIMARY KEY,
    partner_id      TEXT UNIQUE NOT NULL,        -- "aura_studio", "migros_partner"
    display_name    TEXT NOT NULL,
    key_hash        TEXT NOT NULL,               -- SHA-256(api_key) — düz key saklanmaz
    key_prefix      TEXT NOT NULL,               -- "pk_live_abc123" ilk 12 karakter
    scopes          TEXT[] DEFAULT '{}',         -- ["read:prices","write:orders","read:coupons"]
    rate_limit_rpm  INT DEFAULT 60,              -- dakikada max istek
    webhook_url     TEXT,                        -- Partner'ın gelen webhook URL'i
    webhook_secret  TEXT,                        -- HMAC-SHA256 imzalama anahtarı (şifreli)
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ
);

-- Rate limiting: sliding window sayaçları
CREATE TABLE IF NOT EXISTS partner_rate_limits (
    id              BIGSERIAL PRIMARY KEY,
    partner_id      TEXT NOT NULL REFERENCES partner_api_keys(partner_id) ON DELETE CASCADE,
    window_start    TIMESTAMPTZ NOT NULL,        -- 1 dakikalık pencere başlangıcı
    request_count   INT DEFAULT 1,
    UNIQUE(partner_id, window_start)
);

CREATE INDEX IF NOT EXISTS idx_prl_partner_window
    ON partner_rate_limits(partner_id, window_start DESC);

-- Webhook gönderim geçmişi
CREATE TABLE IF NOT EXISTS partner_webhook_log (
    id              BIGSERIAL PRIMARY KEY,
    partner_id      TEXT NOT NULL,
    event_type      TEXT NOT NULL,               -- "price_alert", "group_buy_ready", "coupon_issued"
    payload_hash    TEXT,                        -- SHA-256(payload) — gizlilik için
    status_code     INT,
    attempts        INT DEFAULT 1,
    delivered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── 2. Kupon & Puan Dönüşümü ────────────────────────────────

CREATE TABLE IF NOT EXISTS coupons (
    id              SERIAL PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,         -- "ALMADAN-XYZ123"
    partner_id      TEXT REFERENCES partner_api_keys(partner_id) ON DELETE SET NULL,
    coupon_type     TEXT DEFAULT 'percentage',    -- 'percentage', 'fixed', 'free_item'
    discount_pct    NUMERIC(5,2),                 -- % indirim
    discount_amount NUMERIC(10,2),                -- Sabit indirim (TL)
    min_spend       NUMERIC(10,2) DEFAULT 0,      -- Minimum harcama
    max_uses        INT DEFAULT 1,                -- Toplam kullanım sınırı
    uses_count      INT DEFAULT 0,
    points_cost     INT DEFAULT 0,                -- Kaç Almadan puanına denk
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    metadata        JSONB DEFAULT '{}',           -- {store, category, product_key}
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id              BIGSERIAL PRIMARY KEY,
    coupon_id       INT NOT NULL REFERENCES coupons(id),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    redeemed_at     TIMESTAMPTZ DEFAULT NOW(),
    order_total     NUMERIC(10,2),
    discount_applied NUMERIC(10,2),
    UNIQUE(coupon_id, user_id)                    -- Kullanıcı başına 1 kullanım
);

CREATE TABLE IF NOT EXISTS point_exchanges (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    points_spent    INT NOT NULL,
    coupon_id       INT REFERENCES coupons(id),
    exchange_rate   NUMERIC(8,4),                 -- 1 puan = X TL
    exchanged_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coupons_code     ON coupons(code) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_coupons_partner  ON coupons(partner_id, is_active);
CREATE INDEX IF NOT EXISTS idx_cr_user          ON coupon_redemptions(user_id, redeemed_at DESC);
CREATE INDEX IF NOT EXISTS idx_pe_user          ON point_exchanges(user_id, exchanged_at DESC);

-- ── 3. Grup Alışveriş (Community Buy) ───────────────────────

CREATE TABLE IF NOT EXISTS group_buys (
    id              SERIAL PRIMARY KEY,
    product_title   TEXT NOT NULL,
    store           TEXT NOT NULL,
    current_price   NUMERIC(10,2) NOT NULL,       -- Şu anki fiyat
    target_price    NUMERIC(10,2) NOT NULL,        -- Hedef fiyat (grup indirimli)
    target_quantity INT NOT NULL,                  -- Hedef adet
    current_quantity INT DEFAULT 0,                -- Şu anki katılım
    location_hash   TEXT DEFAULT '',              -- İlçe/semt hash'i (gizlilik)
    status          TEXT DEFAULT 'recruiting',     -- 'recruiting','active','completed','expired'
    organizer_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS group_buy_members (
    id              BIGSERIAL PRIMARY KEY,
    group_buy_id    INT NOT NULL REFERENCES group_buys(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    quantity_wanted INT DEFAULT 1,
    joined_at       TIMESTAMPTZ DEFAULT NOW(),
    notified        BOOLEAN DEFAULT FALSE,
    UNIQUE(group_buy_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_gb_status    ON group_buys(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_gb_product   ON group_buys(product_title, store, status);
CREATE INDEX IF NOT EXISTS idx_gbm_user     ON group_buy_members(user_id, joined_at DESC);

-- Group buy tamamlanma tetikleyicisi
CREATE OR REPLACE FUNCTION check_group_buy_completion()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- Hedef adede ulaşıldıysa tamamla
    IF NEW.current_quantity >= (
        SELECT target_quantity FROM group_buys WHERE id = NEW.group_buy_id
    ) THEN
        UPDATE group_buys
        SET status = 'completed', completed_at = NOW()
        WHERE id = NEW.group_buy_id AND status = 'recruiting';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_group_buy_complete
    AFTER INSERT ON group_buy_members
    FOR EACH ROW EXECUTE FUNCTION check_group_buy_completion();

-- ── 4. Eko-Skor ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS eco_scores (
    id              SERIAL PRIMARY KEY,
    product_key     TEXT UNIQUE NOT NULL,
    product_title   TEXT NOT NULL,
    packaging_type  TEXT DEFAULT 'unknown',   -- 'plastic','cardboard','glass','metal','bio'
    eco_score       SMALLINT NOT NULL,        -- 0–100
    breakdown       JSONB DEFAULT '{}',       -- {packaging:40, transport:30, organic:20, local:10}
    certifications  TEXT[] DEFAULT '{}',      -- ['organic', 'fair_trade', 'local']
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_es_score ON eco_scores(eco_score DESC);

-- ── 5. Fiş Dışa Aktarım Geçmişi ─────────────────────────────

CREATE TABLE IF NOT EXISTS receipt_exports (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    receipt_id      TEXT,
    export_format   TEXT NOT NULL,           -- 'json', 'xml', 'csv'
    record_count    INT DEFAULT 0,
    file_size_bytes INT,
    exported_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ── 6. RLS ───────────────────────────────────────────────────

ALTER TABLE partner_api_keys     ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_rate_limits  ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_webhook_log  ENABLE ROW LEVEL SECURITY;
ALTER TABLE coupons              ENABLE ROW LEVEL SECURITY;
ALTER TABLE coupon_redemptions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE point_exchanges      ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_buys           ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_buy_members    ENABLE ROW LEVEL SECURITY;
ALTER TABLE eco_scores           ENABLE ROW LEVEL SECURITY;
ALTER TABLE receipt_exports      ENABLE ROW LEVEL SECURITY;

-- Kuponlar: herkes aktif olanları görebilir
CREATE POLICY coupons_public_read ON coupons
    FOR SELECT USING (is_active = TRUE);

-- Grup alışveriş: herkes "recruiting" olanları görebilir
CREATE POLICY gb_public_read ON group_buys
    FOR SELECT USING (status IN ('recruiting', 'active'));

-- Eko-skor: public
CREATE POLICY es_public_read ON eco_scores FOR SELECT USING (TRUE);

-- Kullanıcı kendi verilerini görür
CREATE POLICY cr_user_select ON coupon_redemptions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY pe_user_select ON point_exchanges    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY gbm_user_select ON group_buy_members FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY re_user_select ON receipt_exports    FOR SELECT USING (auth.uid() = user_id);

-- Servis rolü tam erişim
CREATE POLICY pak_service  ON partner_api_keys     FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY prl_service  ON partner_rate_limits  FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY pwl_service  ON partner_webhook_log  FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY co_service   ON coupons              FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY cr_service   ON coupon_redemptions   FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY pe_service   ON point_exchanges      FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY gb_service   ON group_buys           FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY gbm_service  ON group_buy_members    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY es_service   ON eco_scores           FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY re_service   ON receipt_exports      FOR ALL USING (auth.role() = 'service_role');

-- ── 7. Yardımcı Fonksiyonlar ─────────────────────────────────

-- Kullanıcının aktif kuponlarını getir
CREATE OR REPLACE FUNCTION get_user_coupons(p_user_id UUID)
RETURNS TABLE (
    code            TEXT,
    partner_id      TEXT,
    coupon_type     TEXT,
    discount_pct    NUMERIC,
    discount_amount NUMERIC,
    min_spend       NUMERIC,
    expires_at      TIMESTAMPTZ,
    already_used    BOOLEAN
) LANGUAGE sql STABLE AS $$
    SELECT
        c.code, c.partner_id, c.coupon_type,
        c.discount_pct, c.discount_amount, c.min_spend, c.expires_at,
        EXISTS(
            SELECT 1 FROM coupon_redemptions cr
            WHERE cr.coupon_id = c.id AND cr.user_id = p_user_id
        ) AS already_used
    FROM coupons c
    WHERE c.is_active = TRUE
      AND (c.expires_at IS NULL OR c.expires_at > NOW())
      AND c.uses_count < c.max_uses
    ORDER BY c.expires_at NULLS LAST;
$$;

-- Yakın grup alışverişleri (aynı location_hash)
CREATE OR REPLACE FUNCTION get_nearby_group_buys(p_location_hash TEXT, p_limit INT DEFAULT 10)
RETURNS TABLE (
    id              INT,
    product_title   TEXT,
    store           TEXT,
    current_price   NUMERIC,
    target_price    NUMERIC,
    progress_pct    NUMERIC,
    members_count   BIGINT,
    expires_at      TIMESTAMPTZ
) LANGUAGE sql STABLE AS $$
    SELECT
        gb.id,
        gb.product_title,
        gb.store,
        gb.current_price,
        gb.target_price,
        ROUND(100.0 * gb.current_quantity / NULLIF(gb.target_quantity, 0), 1) AS progress_pct,
        COUNT(gbm.id)                                                           AS members_count,
        gb.expires_at
    FROM group_buys gb
    LEFT JOIN group_buy_members gbm ON gbm.group_buy_id = gb.id
    WHERE gb.status = 'recruiting'
      AND (p_location_hash = '' OR gb.location_hash = p_location_hash)
      AND gb.expires_at > NOW()
    GROUP BY gb.id
    ORDER BY progress_pct DESC
    LIMIT p_limit;
$$;
