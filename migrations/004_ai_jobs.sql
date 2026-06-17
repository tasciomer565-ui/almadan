-- ============================================================
-- Sprint 3: AI İş Kuyruğu Şeması
-- Supabase SQL Editor'dan çalıştırın (003 sonrası)
-- ============================================================

-- ── 1. ai_jobs — Genelleştirilmiş AI İş Kuyruğu ───────────
-- VTON, OCR, fiyat analizi ve diğer tüm AI işleri buradan geçer.
CREATE TABLE IF NOT EXISTS public.ai_jobs (
    id              BIGSERIAL PRIMARY KEY,
    job_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,

    -- İş tipi ve sahipliği
    job_type        TEXT NOT NULL                   -- 'vton' | 'ocr' | 'price_analysis' | 'skin_analysis'
                        CHECK (job_type IN ('vton', 'ocr', 'price_analysis', 'skin_analysis', 'custom')),
    user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    device_id       TEXT,                            -- misafir kullanıcı için

    -- Durum makinesi
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'queued', 'processing', 'done', 'failed', 'canceled')),
    priority        SMALLINT NOT NULL DEFAULT 5      -- 1 (acil) – 10 (düşük)
                        CHECK (priority BETWEEN 1 AND 10),
    retry_count     SMALLINT NOT NULL DEFAULT 0,
    max_retries     SMALLINT NOT NULL DEFAULT 2,

    -- Girdi / Çıktı
    input_data      JSONB NOT NULL DEFAULT '{}',     -- iş girdileri (URL'ler, parametreler)
    output_data     JSONB,                           -- tamamlandığında sonuçlar
    error_message   TEXT,

    -- Harici provider bilgisi
    provider        TEXT DEFAULT 'replicate'         -- 'replicate' | 'openai' | 'local'
                        CHECK (provider IN ('replicate', 'openai', 'google_vision', 'local')),
    provider_job_id TEXT,                            -- Replicate prediction ID vb.
    webhook_secret  TEXT,                            -- Webhook doğrulama token'ı

    -- Zamanlama
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    queued_at       TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days',  -- otomatik temizleme

    -- Maliyet takibi
    estimated_cost_usd NUMERIC(8,4),
    actual_cost_usd    NUMERIC(8,4)
);

-- ── İndeksler ────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ai_jobs_status_priority_idx
    ON public.ai_jobs (status, priority, created_at)
    WHERE status IN ('pending', 'queued');          -- sadece aktif işler için kısmi index

CREATE INDEX IF NOT EXISTS ai_jobs_user_idx      ON public.ai_jobs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_jobs_type_idx      ON public.ai_jobs (job_type, status);
CREATE INDEX IF NOT EXISTS ai_jobs_provider_idx  ON public.ai_jobs (provider_job_id)
    WHERE provider_job_id IS NOT NULL;

-- ── 2. ai_job_events — Durum Geçiş Günlüğü ─────────────────
-- Her durum değişikliği burada kayıt altına alınır.
CREATE TABLE IF NOT EXISTS public.ai_job_events (
    id          BIGSERIAL PRIMARY KEY,
    job_id      UUID NOT NULL REFERENCES public.ai_jobs(job_id) ON DELETE CASCADE,
    event       TEXT NOT NULL,                      -- 'queued', 'started', 'completed', 'failed', 'retried'
    old_status  TEXT,
    new_status  TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ai_job_events_job_idx ON public.ai_job_events (job_id, created_at DESC);

-- ── 3. Trigger: Durum değişikliğini otomatik logla ──────────
CREATE OR REPLACE FUNCTION public.log_ai_job_status_change()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO public.ai_job_events (job_id, event, old_status, new_status)
        VALUES (NEW.job_id, 'status_change', OLD.status, NEW.status);

        -- Zaman damgalarını otomatik güncelle
        CASE NEW.status
            WHEN 'queued'     THEN NEW.queued_at    = NOW();
            WHEN 'processing' THEN NEW.started_at   = NOW();
            WHEN 'done'       THEN NEW.completed_at = NOW();
            WHEN 'failed'     THEN NEW.completed_at = NOW();
            ELSE NULL;
        END CASE;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS ai_job_status_trigger ON public.ai_jobs;
CREATE TRIGGER ai_job_status_trigger
    BEFORE UPDATE ON public.ai_jobs
    FOR EACH ROW EXECUTE FUNCTION public.log_ai_job_status_change();

-- ── 4. Eski vton_jobs ile uyumluluk ─────────────────────────
-- Eski kodun vton_jobs okumaya devam etmesi için VIEW
CREATE OR REPLACE VIEW public.vton_jobs_compat AS
SELECT
    job_id::TEXT AS job_id,
    user_id::TEXT AS user_id,
    (input_data->>'portrait_url')  AS portrait_url,
    (input_data->>'garment_url')   AS garment_url,
    status,
    (output_data->>'result_url')   AS result_url,
    provider_job_id                AS replicate_id,
    error_message                  AS error_msg,
    created_at,
    completed_at                   AS updated_at
FROM public.ai_jobs
WHERE job_type = 'vton';

-- ── 5. RLS ──────────────────────────────────────────────────
ALTER TABLE public.ai_jobs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_job_events  ENABLE ROW LEVEL SECURITY;

-- Kullanıcı kendi işlerini görür
DROP POLICY IF EXISTS ai_jobs_own ON public.ai_jobs;
CREATE POLICY ai_jobs_own ON public.ai_jobs
    FOR SELECT USING (auth.uid() = user_id);

-- Service role her şeyi yazabilir (backend SERVICE_KEY ile çalışır)
DROP POLICY IF EXISTS ai_jobs_service_insert ON public.ai_jobs;
CREATE POLICY ai_jobs_service_insert ON public.ai_jobs
    FOR ALL USING (TRUE);

-- ── 6. Temizlik fonksiyonu (pg_cron ile haftalık çağrılabilir) ──
CREATE OR REPLACE FUNCTION public.cleanup_expired_ai_jobs()
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE deleted_count INT;
BEGIN
    DELETE FROM public.ai_jobs
    WHERE expires_at < NOW()
      AND status IN ('done', 'failed', 'canceled');
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- ── 7. Kuyruk'tan sıradaki işi al (SELECT ... FOR UPDATE SKIP LOCKED) ──
-- Bu fonksiyon worker'ın race condition olmadan iş almasını sağlar
CREATE OR REPLACE FUNCTION public.claim_next_ai_job(p_job_type TEXT DEFAULT NULL)
RETURNS public.ai_jobs LANGUAGE plpgsql AS $$
DECLARE claimed public.ai_jobs;
BEGIN
    WITH next_job AS (
        SELECT job_id FROM public.ai_jobs
        WHERE status = 'pending'
          AND (p_job_type IS NULL OR job_type = p_job_type)
          AND retry_count < max_retries
        ORDER BY priority ASC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED          -- birden fazla worker aynı işi almasın
    )
    UPDATE public.ai_jobs SET status = 'queued'
    WHERE job_id = (SELECT job_id FROM next_job)
    RETURNING * INTO claimed;

    RETURN claimed;
END;
$$;
