-- Supabase SQL Editor'da çalıştırın
CREATE TABLE IF NOT EXISTS product_cache (
  id            BIGSERIAL PRIMARY KEY,
  cache_key     TEXT NOT NULL UNIQUE,   -- normalize(query) + "|" + category
  query         TEXT NOT NULL,
  category      TEXT NOT NULL DEFAULT 'GENEL',
  products      JSONB NOT NULL DEFAULT '[]',
  source_count  INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at    TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '6 hours'
);

CREATE INDEX IF NOT EXISTS idx_product_cache_key     ON product_cache (cache_key);
CREATE INDEX IF NOT EXISTS idx_product_cache_expires ON product_cache (expires_at);

-- Expired rows'ları otomatik sil (pg_cron eklentisi aktifse)
-- SELECT cron.schedule('cleanup-cache', '0 * * * *', $$DELETE FROM product_cache WHERE expires_at < NOW()$$);
