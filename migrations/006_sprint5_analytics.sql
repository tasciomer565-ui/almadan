-- ============================================================
-- Sprint 5: İşletme Analitiği & Kullanıcı Tutundurma
-- ============================================================
-- Çalıştırma sırası: 006 (005'ten sonra)
-- ============================================================

-- ── 1. Kullanıcı Etkinlik Olayları ──────────────────────────
CREATE TABLE IF NOT EXISTS user_analytics_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    device_id       TEXT,
    event_type      TEXT NOT NULL,           -- search, view_product, add_watchlist, click_buy, share
    payload         JSONB DEFAULT '{}',
    session_id      TEXT,
    platform        TEXT DEFAULT 'web',      -- web, pwa, ios, android
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_uae_user_time   ON user_analytics_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uae_event_type  ON user_analytics_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_uae_device      ON user_analytics_events(device_id, created_at DESC);

-- ── 2. Tasarruf Kayıtları ────────────────────────────────────
-- Kullanıcının watchlist ürünü katalog indiriminden tasarruf ettiğinde
CREATE TABLE IF NOT EXISTS user_savings (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    device_id           TEXT,
    product_title       TEXT NOT NULL,
    store               TEXT NOT NULL,
    price               NUMERIC(10,2) NOT NULL,
    original_price      NUMERIC(10,2),
    saved_amount        NUMERIC(10,2),          -- original_price - price
    saved_pct           SMALLINT,               -- % indirim
    catalog_match_id    BIGINT REFERENCES catalog_matches(id) ON DELETE SET NULL,
    recorded_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_us_user_time  ON user_savings(user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_us_store      ON user_savings(store, recorded_at DESC);

-- ── 3. A/B Deneyleri ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ab_experiments (
    id              SERIAL PRIMARY KEY,
    key             TEXT UNIQUE NOT NULL,       -- 'price_display_v2', 'buy_btn_color'
    description     TEXT,
    variants        JSONB NOT NULL DEFAULT '["control","variant_a"]',
    traffic_pct     SMALLINT DEFAULT 100,       -- katılım oranı (100 = herkes)
    is_active       BOOLEAN DEFAULT TRUE,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    winner_variant  TEXT
);

CREATE TABLE IF NOT EXISTS ab_assignments (
    id              BIGSERIAL PRIMARY KEY,
    experiment_id   INT REFERENCES ab_experiments(id) ON DELETE CASCADE,
    user_id         UUID,
    device_id       TEXT,
    variant         TEXT NOT NULL,
    assigned_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(experiment_id, user_id),
    UNIQUE(experiment_id, device_id)
);

CREATE TABLE IF NOT EXISTS ab_events (
    id              BIGSERIAL PRIMARY KEY,
    experiment_id   INT REFERENCES ab_experiments(id) ON DELETE CASCADE,
    assignment_id   BIGINT REFERENCES ab_assignments(id) ON DELETE CASCADE,
    event_name      TEXT NOT NULL,              -- 'click_buy', 'add_watchlist', 'conversion'
    value           NUMERIC(10,2),              -- opsiyonel: sipariş tutarı vb.
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ab_events_exp ON ab_events(experiment_id, event_name, created_at DESC);

-- ── 4. Kullanıcı Puanları (Gamification) ─────────────────────
CREATE TABLE IF NOT EXISTS user_points (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    points      INT NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL,          -- 'weekly_login', 'first_save', 'share', 'review'
    expires_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_upoints_user ON user_points(user_id, created_at DESC);

-- Kullanıcının toplam aktif puanını döndüren view
CREATE OR REPLACE VIEW user_points_summary AS
SELECT
    user_id,
    SUM(points) AS total_points,
    COUNT(*) FILTER (WHERE points > 0) AS earning_events,
    MAX(created_at) AS last_earned_at
FROM user_points
WHERE expires_at IS NULL OR expires_at > NOW()
GROUP BY user_id;

-- ── 5. Haftalık Digest Log ───────────────────────────────────
CREATE TABLE IF NOT EXISTS digest_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    digest_type TEXT DEFAULT 'weekly',       -- 'weekly', 'monthly', 'deal_alert'
    channel     TEXT DEFAULT 'email',        -- 'email', 'push', 'both'
    status      TEXT DEFAULT 'sent',         -- 'sent', 'failed', 'skipped'
    payload     JSONB DEFAULT '{}',          -- özet içeriği (kaç ürün, tasarruf miktarı)
    sent_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_digest_user_time ON digest_log(user_id, sent_at DESC);

-- ── 6. Admin Metrikleri Tablosu ──────────────────────────────
-- Her cron çalışması sonrası genel sistem sağlığı kaydı
CREATE TABLE IF NOT EXISTS system_health_log (
    id              BIGSERIAL PRIMARY KEY,
    component       TEXT NOT NULL,           -- 'scraper_migros', 'ai_worker', 'catalog_cron'
    status          TEXT NOT NULL,           -- 'ok', 'degraded', 'error'
    latency_ms      INT,
    error_count     INT DEFAULT 0,
    success_count   INT DEFAULT 0,
    metadata        JSONB DEFAULT '{}',
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shl_component ON system_health_log(component, recorded_at DESC);

-- ── 7. RLS Politikaları ───────────────────────────────────────
ALTER TABLE user_analytics_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_savings          ENABLE ROW LEVEL SECURITY;
ALTER TABLE ab_assignments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ab_events             ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_points           ENABLE ROW LEVEL SECURITY;
ALTER TABLE digest_log            ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_health_log     ENABLE ROW LEVEL SECURITY;

-- Kullanıcılar yalnızca kendi verilerini görebilir
CREATE POLICY uae_user_select  ON user_analytics_events FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY uae_user_insert  ON user_analytics_events FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY us_user_select   ON user_savings          FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY ab_assign_select ON ab_assignments        FOR SELECT USING (auth.uid() = user_id OR user_id IS NULL);
CREATE POLICY up_user_select   ON user_points           FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY dl_user_select   ON digest_log            FOR SELECT USING (auth.uid() = user_id);

-- Servis rolü (service_key) her şeye erişebilir
CREATE POLICY uae_service  ON user_analytics_events FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY us_service   ON user_savings          FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY aba_service  ON ab_assignments        FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY abe_service  ON ab_events             FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY up_service   ON user_points           FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY dl_service   ON digest_log            FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY shl_service  ON system_health_log     FOR ALL USING (auth.role() = 'service_role');

-- ── 8. Analitik Aggregasyon Fonksiyonları ────────────────────

-- Kullanıcının aylık tasarruf özeti
CREATE OR REPLACE FUNCTION get_monthly_savings(p_user_id UUID)
RETURNS TABLE (
    month        TEXT,
    total_saved  NUMERIC,
    save_count   BIGINT,
    top_store    TEXT
) LANGUAGE sql STABLE AS $$
    SELECT
        TO_CHAR(recorded_at, 'YYYY-MM')                        AS month,
        COALESCE(SUM(saved_amount), 0)                         AS total_saved,
        COUNT(*)                                               AS save_count,
        MODE() WITHIN GROUP (ORDER BY store)                   AS top_store
    FROM user_savings
    WHERE user_id = p_user_id
      AND recorded_at >= NOW() - INTERVAL '12 months'
    GROUP BY 1
    ORDER BY 1 DESC;
$$;

-- Market bazlı karşılaştırma
CREATE OR REPLACE FUNCTION get_store_comparison(p_user_id UUID)
RETURNS TABLE (
    store           TEXT,
    total_purchases BIGINT,
    total_saved     NUMERIC,
    avg_discount    NUMERIC
) LANGUAGE sql STABLE AS $$
    SELECT
        store,
        COUNT(*)                   AS total_purchases,
        COALESCE(SUM(saved_amount), 0) AS total_saved,
        ROUND(AVG(saved_pct), 1)   AS avg_discount
    FROM user_savings
    WHERE user_id = p_user_id
    GROUP BY store
    ORDER BY total_saved DESC;
$$;

-- Admin: scraper hata özeti (son 24 saat)
CREATE OR REPLACE FUNCTION get_scraper_health_summary()
RETURNS TABLE (
    component       TEXT,
    last_status     TEXT,
    error_rate_pct  NUMERIC,
    avg_latency_ms  NUMERIC,
    last_seen       TIMESTAMPTZ
) LANGUAGE sql STABLE AS $$
    SELECT
        component,
        (ARRAY_AGG(status ORDER BY recorded_at DESC))[1] AS last_status,
        ROUND(
            100.0 * SUM(error_count) / NULLIF(SUM(success_count + error_count), 0),
            1
        )                                                AS error_rate_pct,
        ROUND(AVG(latency_ms), 0)                        AS avg_latency_ms,
        MAX(recorded_at)                                 AS last_seen
    FROM system_health_log
    WHERE recorded_at >= NOW() - INTERVAL '24 hours'
    GROUP BY component
    ORDER BY error_rate_pct DESC NULLS LAST;
$$;

-- A/B test sonuç özeti
CREATE OR REPLACE FUNCTION get_ab_results(p_experiment_key TEXT)
RETURNS TABLE (
    variant          TEXT,
    participants     BIGINT,
    conversions      BIGINT,
    conversion_rate  NUMERIC
) LANGUAGE sql STABLE AS $$
    SELECT
        aa.variant,
        COUNT(DISTINCT aa.id)                                                         AS participants,
        COUNT(ae.id) FILTER (WHERE ae.event_name = 'conversion')                     AS conversions,
        ROUND(
            100.0 * COUNT(ae.id) FILTER (WHERE ae.event_name = 'conversion')
            / NULLIF(COUNT(DISTINCT aa.id), 0),
            2
        )                                                                             AS conversion_rate
    FROM ab_experiments ex
    JOIN ab_assignments aa ON aa.experiment_id = ex.id
    LEFT JOIN ab_events ae ON ae.assignment_id = aa.id
    WHERE ex.key = p_experiment_key
    GROUP BY aa.variant
    ORDER BY conversion_rate DESC NULLS LAST;
$$;
