-- Sprint 15: Kullanıcı davranış analitikleri

CREATE TABLE IF NOT EXISTS user_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    session_id  TEXT,                      -- giriş yapmamış kullanıcılar için
    event_type  TEXT NOT NULL,             -- 'url_search' | 'store_follow' | 'price_track' | 'barcode_scan'
    payload     JSONB NOT NULL DEFAULT '{}', -- event'e özel veriler
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_events_user    ON user_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_events_type    ON user_events(event_type);
CREATE INDEX IF NOT EXISTS idx_user_events_created ON user_events(created_at DESC);

ALTER TABLE user_events ENABLE ROW LEVEL SECURITY;

-- Sadece service_role yazabilir ve okuyabilir (admin analytics)
DROP POLICY IF EXISTS "service_all_events" ON user_events;
CREATE POLICY "service_all_events"
    ON user_events FOR ALL
    TO service_role USING (true) WITH CHECK (true);
