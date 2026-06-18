-- Sprint 11: Mağaza Bülten & Takip Modülü

-- Mağaza kataloğu (statik + yönetici tarafından güncellenebilir)
CREATE TABLE IF NOT EXISTS store_newsletters (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT NOT NULL UNIQUE,          -- 'bim', 'a101', 'karaca'
    name             TEXT NOT NULL,                 -- 'BİM'
    logo_url         TEXT,
    category         TEXT NOT NULL DEFAULT 'market', -- 'market' | 'fashion' | 'beauty' | 'home'
    publication_day  TEXT,                          -- 'friday' | 'thursday' | NULL (rastgele/manuel)
    publication_note TEXT,                          -- 'Her Cuma 09:00'
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Kullanıcı → Mağaza takip ilişkisi
CREATE TABLE IF NOT EXISTS followed_stores (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    store_slug TEXT NOT NULL REFERENCES store_newsletters(slug) ON DELETE CASCADE,
    followed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, store_slug)
);

-- Mağaza kampanya/bülten kayıtları
CREATE TABLE IF NOT EXISTS store_campaigns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_slug   TEXT NOT NULL REFERENCES store_newsletters(slug) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT,
    catalog_url  TEXT,
    valid_from   DATE,
    valid_until  DATE,
    notified     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_followed_stores_user   ON followed_stores(user_id);
CREATE INDEX IF NOT EXISTS idx_followed_stores_slug   ON followed_stores(store_slug);
CREATE INDEX IF NOT EXISTS idx_store_campaigns_notify ON store_campaigns(notified, store_slug);

-- RLS
ALTER TABLE store_newsletters  ENABLE ROW LEVEL SECURITY;
ALTER TABLE followed_stores    ENABLE ROW LEVEL SECURITY;
ALTER TABLE store_campaigns    ENABLE ROW LEVEL SECURITY;

-- store_newsletters: herkes okuyabilir, sadece service_role yazabilir
CREATE POLICY "public_read_stores"    ON store_newsletters FOR SELECT USING (true);
CREATE POLICY "service_write_stores"  ON store_newsletters FOR ALL TO service_role USING (true) WITH CHECK (true);

-- followed_stores: kullanıcı kendi kayıtlarını yönetir
CREATE POLICY "user_own_follows"      ON followed_stores FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "service_all_follows"   ON followed_stores FOR ALL TO service_role USING (true) WITH CHECK (true);

-- store_campaigns: herkes okur, service_role yazar
CREATE POLICY "public_read_campaigns" ON store_campaigns FOR SELECT USING (true);
CREATE POLICY "service_write_campaigns" ON store_campaigns FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Başlangıç verisi: Türkiye'nin popüler mağazaları
INSERT INTO store_newsletters (slug, name, category, publication_day, publication_note) VALUES
    ('bim',       'BİM',          'market',  'friday',    'Her Cuma 09:00 yeni kampanya'),
    ('a101',      'A101',         'market',  'thursday',  'Her Perşembe indirimler başlar'),
    ('sok',       'ŞOK',          'market',  'wednesday', 'Her Çarşamba fırsatlar'),
    ('migros',    'Migros',       'market',  NULL,        'Haftalık değişken'),
    ('carrefour', 'CarrefourSA',  'market',  NULL,        'Haftalık değişken'),
    ('karaca',    'Karaca',       'home',    NULL,        'Sezon ve özel günlerde'),
    ('gratis',    'Gratis',       'beauty',  NULL,        'Kampanya dönemlerinde'),
    ('hepsiburada','Hepsiburada', 'fashion', NULL,        'Büyük indirim günlerinde'),
    ('trendyol',  'Trendyol',     'fashion', NULL,        'Büyük indirim günlerinde'),
    ('lcwaikiki', 'LC Waikiki',   'fashion', NULL,        'Sezon geçişlerinde')
ON CONFLICT (slug) DO NOTHING;
