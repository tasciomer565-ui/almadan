-- Sprint 13: Kullanıcı bildirimleri + followed_stores email sütunu

-- followed_stores tablosuna email sütunu ekle (takip anında kayıt için)
ALTER TABLE followed_stores ADD COLUMN IF NOT EXISTS email TEXT;

-- Kullanıcı bazlı uygulama içi bildirimler
CREATE TABLE IF NOT EXISTS user_notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    store_slug  TEXT,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    url         TEXT,
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_notifs_user    ON user_notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_user_notifs_created ON user_notifications(created_at DESC);

-- RLS
ALTER TABLE user_notifications ENABLE ROW LEVEL SECURITY;

-- Kullanıcı sadece kendi bildirimlerini görebilir/güncelleyebilir
CREATE POLICY "user_read_own_notifs"
    ON user_notifications FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "user_update_own_notifs"
    ON user_notifications FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Service role her şeyi yapabilir (cron için)
CREATE POLICY "service_all_notifs"
    ON user_notifications FOR ALL
    TO service_role USING (true) WITH CHECK (true);
