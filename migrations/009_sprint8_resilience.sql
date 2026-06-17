-- ============================================================
-- Sprint 8: Kırılmazlık, Ölçekleme & Gözlemlenebilirlik
-- ============================================================
-- Çalıştırma sırası: 009 (008'den sonra)
-- ============================================================

-- ── 1. Performans Takibi ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS request_metrics (
    id              BIGSERIAL PRIMARY KEY,
    endpoint        TEXT NOT NULL,
    method          TEXT NOT NULL DEFAULT 'GET',
    status_code     INT,
    latency_ms      INT NOT NULL,
    user_id         UUID,
    request_id      TEXT,
    region          TEXT DEFAULT 'fra1',
    is_cache_hit    BOOLEAN DEFAULT FALSE,
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rm_endpoint  ON request_metrics(endpoint, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_rm_latency   ON request_metrics(latency_ms DESC) WHERE latency_ms > 500;
CREATE INDEX IF NOT EXISTS idx_rm_time      ON request_metrics(recorded_at DESC);

-- Eski kayıtları otomatik temizle (30 gün)
CREATE OR REPLACE FUNCTION cleanup_request_metrics()
RETURNS void LANGUAGE sql AS $$
    DELETE FROM request_metrics WHERE recorded_at < NOW() - INTERVAL '30 days';
$$;

-- ── 2. Circuit Breaker Durumu ────────────────────────────────
CREATE TABLE IF NOT EXISTS circuit_breaker_state (
    service         TEXT PRIMARY KEY,
    state           TEXT NOT NULL DEFAULT 'closed',   -- closed, open, half_open
    failure_count   INT DEFAULT 0,
    success_count   INT DEFAULT 0,
    last_failure_at TIMESTAMPTZ,
    opened_at       TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Varsayılan circuit breaker kayıtları
INSERT INTO circuit_breaker_state (service, state) VALUES
    ('supabase',  'closed'),
    ('replicate', 'closed'),
    ('openai',    'closed'),
    ('scrapers',  'closed'),
    ('push',      'closed')
ON CONFLICT (service) DO NOTHING;

-- ── 3. Chaos Engineering Log ─────────────────────────────────
CREATE TABLE IF NOT EXISTS chaos_experiments (
    id              BIGSERIAL PRIMARY KEY,
    experiment_name TEXT NOT NULL,
    target_service  TEXT NOT NULL,
    fault_type      TEXT NOT NULL,   -- 'latency', 'error', 'timeout', 'data_corruption'
    duration_sec    INT DEFAULT 30,
    status          TEXT DEFAULT 'pending', -- pending, running, completed, aborted
    result          JSONB DEFAULT '{}',
    triggered_by    TEXT DEFAULT 'manual',  -- manual, cron, ci
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── 4. Yapılandırılmış Log Tablosu ───────────────────────────
CREATE TABLE IF NOT EXISTS structured_logs (
    id              BIGSERIAL PRIMARY KEY,
    level           TEXT NOT NULL DEFAULT 'info',  -- debug, info, warning, error, critical
    logger          TEXT NOT NULL,
    message         TEXT NOT NULL,
    request_id      TEXT,
    user_id         UUID,
    endpoint        TEXT,
    error_type      TEXT,
    stack_trace     TEXT,
    extra           JSONB DEFAULT '{}',
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sl_level   ON structured_logs(level, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_sl_error   ON structured_logs(error_type, recorded_at DESC) WHERE level IN ('error', 'critical');
CREATE INDEX IF NOT EXISTS idx_sl_req     ON structured_logs(request_id) WHERE request_id IS NOT NULL;

-- 7 günden eski debug/info logları temizle
CREATE OR REPLACE FUNCTION cleanup_old_logs()
RETURNS void LANGUAGE sql AS $$
    DELETE FROM structured_logs
    WHERE recorded_at < NOW() - INTERVAL '7 days'
      AND level IN ('debug', 'info');
    DELETE FROM structured_logs
    WHERE recorded_at < NOW() - INTERVAL '30 days';
$$;

-- ── 5. Edge Cache Meta Verisi ────────────────────────────────
CREATE TABLE IF NOT EXISTS cache_invalidations (
    id              BIGSERIAL PRIMARY KEY,
    cache_key       TEXT NOT NULL,
    reason          TEXT,
    triggered_by    TEXT,
    invalidated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 6. Performans Aggregasyon Fonksiyonları ──────────────────

-- Endpoint başına P50/P95/P99 latency (son N saat)
CREATE OR REPLACE FUNCTION get_endpoint_latency_stats(hours INT DEFAULT 1)
RETURNS TABLE (
    endpoint       TEXT,
    request_count  BIGINT,
    p50_ms         NUMERIC,
    p95_ms         NUMERIC,
    p99_ms         NUMERIC,
    error_rate_pct NUMERIC,
    cache_hit_pct  NUMERIC
) LANGUAGE sql STABLE AS $$
    SELECT
        endpoint,
        COUNT(*)                                                           AS request_count,
        ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms))   AS p50_ms,
        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms))   AS p95_ms,
        ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms))   AS p99_ms,
        ROUND(100.0 * COUNT(*) FILTER (WHERE status_code >= 500) / COUNT(*), 2) AS error_rate_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE is_cache_hit) / COUNT(*), 2) AS cache_hit_pct
    FROM request_metrics
    WHERE recorded_at >= NOW() - (hours || ' hours')::INTERVAL
    GROUP BY endpoint
    ORDER BY p99_ms DESC NULLS LAST;
$$;

-- ── 7. RLS ───────────────────────────────────────────────────
ALTER TABLE request_metrics        ENABLE ROW LEVEL SECURITY;
ALTER TABLE circuit_breaker_state  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chaos_experiments      ENABLE ROW LEVEL SECURITY;
ALTER TABLE structured_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE cache_invalidations    ENABLE ROW LEVEL SECURITY;

-- Yalnızca servis rolü erişebilir (tüm tablo admin verisi)
CREATE POLICY rm_service  ON request_metrics        FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY cb_service  ON circuit_breaker_state  FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY ce_service  ON chaos_experiments      FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY sl_service  ON structured_logs        FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY ci_service  ON cache_invalidations    FOR ALL USING (auth.role() = 'service_role');
