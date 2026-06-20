-- Sprint 14: followed_stores FK kısıtlamasını kaldır — frontend 100+ mağazayı destekliyor
-- store_newsletters tablosunda olmayan mağazalar da takip edilebilsin

-- Mevcut FK kısıtlamasını kaldır (store_slug -> store_newsletters)
ALTER TABLE followed_stores DROP CONSTRAINT IF EXISTS followed_stores_store_slug_fkey;

-- Bülten cron'u giriş yapan takipçiye e-posta gönderebilsin.
ALTER TABLE followed_stores ADD COLUMN IF NOT EXISTS email TEXT;

-- service_role politikası ekle (cron job kayıt okuyabilsin)
DROP POLICY IF EXISTS "service_read_follows" ON followed_stores;
CREATE POLICY "service_read_follows"
    ON followed_stores FOR SELECT
    TO service_role USING (true);

-- Kullanıcı kendi takiplerini görebilsin
DROP POLICY IF EXISTS "user_read_own_follows" ON followed_stores;
CREATE POLICY "user_read_own_follows"
    ON followed_stores FOR SELECT
    USING (auth.uid() = user_id);

-- Kullanıcı kendi takiplerini ekleyip silebilsin
DROP POLICY IF EXISTS "user_write_own_follows" ON followed_stores;
CREATE POLICY "user_write_own_follows"
    ON followed_stores FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "user_delete_own_follows" ON followed_stores;
CREATE POLICY "user_delete_own_follows"
    ON followed_stores FOR DELETE
    USING (auth.uid() = user_id);
