-- ============================================================
-- Sprint 4: Katalog OCR & Otomasyon Şeması
-- ============================================================

-- ── 1. catalog_runs — Her katalog tarama oturumu ────────────
CREATE TABLE IF NOT EXISTS public.catalog_runs (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    store       TEXT NOT NULL,
    source_url  TEXT,
    source_type TEXT NOT NULL DEFAULT 'html'   -- 'html' | 'pdf' | 'image'
                    CHECK (source_type IN ('html', 'pdf', 'image')),
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'done', 'failed')),
    item_count  INT DEFAULT 0,
    match_count INT DEFAULT 0,
    fingerprint TEXT,                          -- içerik hash — değişmemişse yeniden işleme
    error_msg   TEXT,
    started_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS catalog_runs_store_idx ON public.catalog_runs (store, created_at DESC);
CREATE INDEX IF NOT EXISTS catalog_runs_status_idx ON public.catalog_runs (status);

-- ── 2. catalog_items — OCR ile çıkarılan ürün-fiyat ikilisi ─
CREATE TABLE IF NOT EXISTS public.catalog_items (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES public.catalog_runs(run_id) ON DELETE CASCADE,
    store       TEXT NOT NULL,
    raw_text    TEXT NOT NULL,                 -- OCR ham metin
    product_name TEXT NOT NULL,               -- normalize edilmiş ürün adı
    price       NUMERIC(10,2),                -- çıkarılan fiyat (NULL = bulunamadı)
    original_price NUMERIC(10,2),
    discount_pct SMALLINT,                    -- %indirim (hesaplanmış)
    unit        TEXT,                         -- 'kg', 'lt', 'adet'
    valid_from  DATE,
    valid_until DATE,
    page_number SMALLINT DEFAULT 1,
    confidence  NUMERIC(4,3) DEFAULT 1.0,     -- OCR/parse güven skoru (0-1)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS catalog_items_store_idx ON public.catalog_items (store, created_at DESC);
CREATE INDEX IF NOT EXISTS catalog_items_name_idx  ON public.catalog_items USING gin(to_tsvector('turkish', product_name));

-- ── 3. catalog_matches — Kullanıcı watchlist eşleşmeleri ────
CREATE TABLE IF NOT EXISTS public.catalog_matches (
    id              BIGSERIAL PRIMARY KEY,
    match_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    catalog_item_id BIGINT NOT NULL REFERENCES public.catalog_items(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    device_id       TEXT,                      -- misafir kullanıcı için
    watchlist_title TEXT NOT NULL,             -- kullanıcının ürün başlığı
    match_score     NUMERIC(4,3) NOT NULL,     -- fuzzy match skoru (0-1)
    notified        BOOLEAN NOT NULL DEFAULT FALSE,
    notified_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Aynı ürüne birden fazla bildirim gitmesin (24 saatte bir)
    UNIQUE (catalog_item_id, user_id, watchlist_title)
);

CREATE INDEX IF NOT EXISTS catalog_matches_user_idx
    ON public.catalog_matches (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS catalog_matches_notify_idx
    ON public.catalog_matches (notified, created_at)
    WHERE notified = FALSE;

-- ── 4. RLS ──────────────────────────────────────────────────
ALTER TABLE public.catalog_runs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.catalog_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.catalog_matches ENABLE ROW LEVEL SECURITY;

-- catalog_runs / items: herkese okunabilir, service role yazar
CREATE POLICY catalog_runs_read    ON public.catalog_runs    FOR SELECT USING (TRUE);
CREATE POLICY catalog_items_read   ON public.catalog_items   FOR SELECT USING (TRUE);
CREATE POLICY catalog_runs_write   ON public.catalog_runs    FOR ALL    USING (TRUE);
CREATE POLICY catalog_items_write  ON public.catalog_items   FOR ALL    USING (TRUE);

-- catalog_matches: kullanıcı kendi eşleşmelerini görür
CREATE POLICY catalog_matches_own  ON public.catalog_matches
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY catalog_matches_write ON public.catalog_matches
    FOR ALL USING (TRUE);

-- ── 5. Temizlik (90 günden eski katalog verisi) ──────────────
CREATE OR REPLACE FUNCTION public.cleanup_old_catalog_data()
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE deleted_count INT;
BEGIN
    DELETE FROM public.catalog_runs
    WHERE created_at < NOW() - INTERVAL '90 days'
      AND status = 'done';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;
