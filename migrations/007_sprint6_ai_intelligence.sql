-- ============================================================
-- Sprint 6: İleri Seviye AI & Zeka Katmanı
-- ============================================================
-- Çalıştırma sırası: 007 (006'dan sonra)
-- Gereksinim: Supabase'de pgvector eklentisi aktif olmalı
-- ============================================================

-- pgvector eklentisini etkinleştir (Supabase'de hazır gelir)
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 1. Ürün Vektörleri (Semantic Search) ────────────────────
-- text-embedding-3-small: 1536 boyut
CREATE TABLE IF NOT EXISTS product_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    product_key     TEXT NOT NULL,           -- normalized: "migros::pinar-sut-1l"
    product_title   TEXT NOT NULL,
    store           TEXT NOT NULL,
    category        TEXT DEFAULT '',
    price           NUMERIC(10,2),
    embedding       vector(1536),            -- OpenAI text-embedding-3-small
    metadata        JSONB DEFAULT '{}',      -- {url, unit, discount_pct, ...}
    embedded_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_key)
);

-- Cosine benzerliği için HNSW indeksi (pgvector önerilen)
CREATE INDEX IF NOT EXISTS idx_pe_embedding
    ON product_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_pe_store ON product_embeddings(store);
CREATE INDEX IF NOT EXISTS idx_pe_category ON product_embeddings(category);

-- ── 2. Fiyat Tahmin Sonuçları ─────────────────────────────────
CREATE TABLE IF NOT EXISTS price_forecasts (
    id              BIGSERIAL PRIMARY KEY,
    product_key     TEXT NOT NULL,
    product_title   TEXT NOT NULL,
    store           TEXT NOT NULL,
    forecast_date   DATE NOT NULL,           -- Tahminin geçerli olduğu gün
    predicted_price NUMERIC(10,2) NOT NULL,
    confidence_low  NUMERIC(10,2),           -- %80 güven aralığı alt sınır
    confidence_high NUMERIC(10,2),           -- %80 güven aralığı üst sınır
    trend           TEXT DEFAULT 'stable',   -- 'rising', 'falling', 'stable'
    change_pct      NUMERIC(5,2),            -- tahmini değişim yüzdesi
    model_version   TEXT DEFAULT 'linear_v1',
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_key, forecast_date)
);

CREATE INDEX IF NOT EXISTS idx_pf_product  ON price_forecasts(product_key, forecast_date);
CREATE INDEX IF NOT EXISTS idx_pf_trend    ON price_forecasts(trend, forecast_date);

-- ── 3. AI İzleme Kayıtları ───────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_monitor_log (
    id              BIGSERIAL PRIMARY KEY,
    service         TEXT NOT NULL,           -- 'embedding', 'forecast', 'vision', 'vton'
    operation       TEXT NOT NULL,           -- 'embed_product', 'predict_price', 'analyze_fridge'
    user_id         UUID,
    status          TEXT DEFAULT 'ok',       -- 'ok', 'error', 'timeout', 'guardrail_blocked'
    latency_ms      INT,
    input_tokens    INT DEFAULT 0,
    output_tokens   INT DEFAULT 0,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    model_id        TEXT,
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}',
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aml_service  ON ai_monitor_log(service, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_aml_status   ON ai_monitor_log(status, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_aml_user     ON ai_monitor_log(user_id, recorded_at DESC);

-- ── 4. Vision Analiz Sonuçları (Buzdolabı) ───────────────────
CREATE TABLE IF NOT EXISTS vision_analyses (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    device_id       TEXT,
    image_url       TEXT,
    analysis_type   TEXT DEFAULT 'fridge',   -- 'fridge', 'receipt', 'label'
    detected_items  JSONB DEFAULT '[]',      -- [{"name":"Süt","quantity":1,"low":true}]
    shopping_list   JSONB DEFAULT '[]',      -- [{"title":"Süt 1L","priority":"high"}]
    raw_response    TEXT,
    model_used      TEXT,
    ai_job_id       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_va_user ON vision_analyses(user_id, created_at DESC);

-- ── 5. Guardrail Kayıtları ────────────────────────────────────
CREATE TABLE IF NOT EXISTS guardrail_logs (
    id              BIGSERIAL PRIMARY KEY,
    check_type      TEXT NOT NULL,           -- 'price_bounds', 'hallucination', 'toxicity'
    input_value     TEXT,
    reason          TEXT,
    passed          BOOLEAN NOT NULL,
    metadata        JSONB DEFAULT '{}',
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gl_check ON guardrail_logs(check_type, passed, recorded_at DESC);

-- ── 6. RLS Politikaları ───────────────────────────────────────
ALTER TABLE product_embeddings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_forecasts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_monitor_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE vision_analyses     ENABLE ROW LEVEL SECURITY;
ALTER TABLE guardrail_logs      ENABLE ROW LEVEL SECURITY;

-- Herkes okuyabilir (ürün vektörleri ve tahminler public)
CREATE POLICY pe_public_read    ON product_embeddings  FOR SELECT USING (true);
CREATE POLICY pf_public_read    ON price_forecasts     FOR SELECT USING (true);

-- Kullanıcılar kendi vision analizlerini görebilir
CREATE POLICY va_user_select    ON vision_analyses     FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY aml_user_select   ON ai_monitor_log      FOR SELECT USING (auth.uid() = user_id);

-- Servis rolü tam erişim
CREATE POLICY pe_service  ON product_embeddings  FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY pf_service  ON price_forecasts     FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY aml_service ON ai_monitor_log      FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY va_service  ON vision_analyses     FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY gl_service  ON guardrail_logs      FOR ALL USING (auth.role() = 'service_role');

-- ── 7. Yardımcı Fonksiyonlar ─────────────────────────────────

-- Semantik ürün arama (cosine similarity)
CREATE OR REPLACE FUNCTION search_products_semantic(
    query_embedding vector(1536),
    p_store         TEXT DEFAULT NULL,
    p_category      TEXT DEFAULT NULL,
    p_limit         INT  DEFAULT 10,
    p_threshold     FLOAT DEFAULT 0.75
)
RETURNS TABLE (
    product_key    TEXT,
    product_title  TEXT,
    store          TEXT,
    category       TEXT,
    price          NUMERIC,
    similarity     FLOAT,
    metadata       JSONB
) LANGUAGE sql STABLE AS $$
    SELECT
        pe.product_key,
        pe.product_title,
        pe.store,
        pe.category,
        pe.price,
        1 - (pe.embedding <=> query_embedding) AS similarity,
        pe.metadata
    FROM product_embeddings pe
    WHERE
        (p_store IS NULL OR pe.store = p_store)
        AND (p_category IS NULL OR pe.category = p_category)
        AND 1 - (pe.embedding <=> query_embedding) >= p_threshold
    ORDER BY pe.embedding <=> query_embedding
    LIMIT p_limit;
$$;

-- AI maliyet özeti (admin dashboard için)
CREATE OR REPLACE FUNCTION get_ai_cost_summary(hours INT DEFAULT 24)
RETURNS TABLE (
    service      TEXT,
    call_count   BIGINT,
    total_cost   NUMERIC,
    avg_latency  NUMERIC,
    error_count  BIGINT
) LANGUAGE sql STABLE AS $$
    SELECT
        service,
        COUNT(*)                       AS call_count,
        ROUND(SUM(cost_usd), 6)        AS total_cost,
        ROUND(AVG(latency_ms), 0)      AS avg_latency,
        COUNT(*) FILTER (WHERE status != 'ok') AS error_count
    FROM ai_monitor_log
    WHERE recorded_at >= NOW() - (hours || ' hours')::INTERVAL
    GROUP BY service
    ORDER BY total_cost DESC;
$$;

-- Ürünün en güncel fiyat tahmini
CREATE OR REPLACE FUNCTION get_latest_forecast(p_product_key TEXT)
RETURNS TABLE (
    forecast_date   DATE,
    predicted_price NUMERIC,
    confidence_low  NUMERIC,
    confidence_high NUMERIC,
    trend           TEXT,
    change_pct      NUMERIC
) LANGUAGE sql STABLE AS $$
    SELECT forecast_date, predicted_price, confidence_low,
           confidence_high, trend, change_pct
    FROM price_forecasts
    WHERE product_key = p_product_key
      AND forecast_date >= CURRENT_DATE
    ORDER BY forecast_date
    LIMIT 14;
$$;
