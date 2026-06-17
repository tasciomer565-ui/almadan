-- ═══════════════════════════════════════════════════════
-- 1. Fiyat Geçmişi Tablosu
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS price_history (
  id          BIGSERIAL PRIMARY KEY,
  product_key TEXT NOT NULL,          -- normalize(title + "|" + source)
  title       TEXT NOT NULL,
  source      TEXT NOT NULL,
  price       NUMERIC(12,2) NOT NULL,
  url         TEXT,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ph_key     ON price_history (product_key);
CREATE INDEX IF NOT EXISTS idx_ph_key_ts  ON price_history (product_key, recorded_at DESC);

-- ═══════════════════════════════════════════════════════
-- 2. VTON İş Kuyruğu
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS vton_jobs (
  id              BIGSERIAL PRIMARY KEY,
  job_id          TEXT NOT NULL UNIQUE DEFAULT gen_random_uuid()::TEXT,
  user_id         TEXT,                         -- opsiyonel Supabase auth user_id
  portrait_url    TEXT NOT NULL,                -- Supabase Storage'a yüklenen fotoğraf
  garment_url     TEXT NOT NULL,                -- kıyafet görseli URL
  status          TEXT NOT NULL DEFAULT 'queued',  -- queued | processing | done | failed
  result_url      TEXT,                         -- tamamlandığında sonuç görseli
  replicate_id    TEXT,                         -- Replicate prediction ID
  error_msg       TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vton_status ON vton_jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vton_job    ON vton_jobs (job_id);

-- ═══════════════════════════════════════════════════════
-- 3. Admin Performans Metrikleri
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS search_metrics (
  id          BIGSERIAL PRIMARY KEY,
  event       TEXT NOT NULL,   -- 'cache_hit' | 'cache_miss' | 'proxy_used' | 'stale_fallback'
  query       TEXT,
  category    TEXT,
  source      TEXT,            -- hangi proxy/site
  duration_ms INT,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_event ON search_metrics (event, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_date  ON search_metrics (recorded_at DESC);
