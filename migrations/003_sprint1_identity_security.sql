-- ============================================================
-- Sprint 1: Kimlik, Güvenlik ve Erişim Şeması
-- Supabase SQL Editor'dan çalıştırın (once 001, 002 çalıştırılmış olmalı)
-- ============================================================

-- ── 1. profiles ─────────────────────────────────────────────
-- Her auth.users kaydına otomatik bağlanan genişletilmiş profil.
CREATE TABLE IF NOT EXISTS public.profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'free'
                        CHECK (role IN ('free', 'premium', 'admin')),
    display_name    TEXT,
    avatar_url      TEXT,
    phone           TEXT,
    stripe_status   TEXT DEFAULT 'inactive'
                        CHECK (stripe_status IN ('inactive', 'trialing', 'active', 'past_due', 'canceled')),
    preferences     JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Yeni kullanıcı kayıt olunca otomatik profil aç
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, phone)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.phone
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- updated_at otomatik güncelleme
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS profiles_updated_at ON public.profiles;
CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── 2. activity_logs (Audit Logs) ───────────────────────────
CREATE TABLE IF NOT EXISTS public.activity_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    session_id  TEXT,
    event       TEXT NOT NULL,            -- 'login', 'logout', 'search', 'barcode_scan', vb.
    metadata    JSONB NOT NULL DEFAULT '{}',
    ip_address  TEXT,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS activity_logs_user_idx  ON public.activity_logs(user_id);
CREATE INDEX IF NOT EXISTS activity_logs_event_idx ON public.activity_logs(event);
CREATE INDEX IF NOT EXISTS activity_logs_time_idx  ON public.activity_logs(created_at DESC);

-- ── 3. device_sessions (Cihaz Senkronizasyonu) ──────────────
CREATE TABLE IF NOT EXISTS public.device_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    device_id   TEXT NOT NULL,
    device_name TEXT,
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, device_id)
);

CREATE INDEX IF NOT EXISTS device_sessions_user_idx ON public.device_sessions(user_id);

-- ── 4. csrf_tokens ──────────────────────────────────────────
-- Server-side CSRF doğrulaması için (stateless alternatif: HMAC-imzalı cookie)
CREATE TABLE IF NOT EXISTS public.csrf_tokens (
    token       TEXT PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id  TEXT,
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '2 hours',
    used        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS csrf_tokens_session_idx ON public.csrf_tokens(session_id);

-- Süresi dolmuş token'ları temizle (pg_cron kuruluysa schedule eklenebilir)
CREATE OR REPLACE FUNCTION public.cleanup_expired_csrf()
RETURNS void LANGUAGE sql AS $$
    DELETE FROM public.csrf_tokens WHERE expires_at < NOW();
$$;

-- ── 5. RLS Politikaları ──────────────────────────────────────
ALTER TABLE public.profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_logs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.device_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.csrf_tokens     ENABLE ROW LEVEL SECURITY;

-- profiles: kullanıcı sadece kendi profilini okur/günceller
DROP POLICY IF EXISTS profiles_select_own ON public.profiles;
CREATE POLICY profiles_select_own ON public.profiles
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS profiles_update_own ON public.profiles;
CREATE POLICY profiles_update_own ON public.profiles
    FOR UPDATE USING (auth.uid() = id)
    WITH CHECK (
        auth.uid() = id
        AND role = (SELECT role FROM public.profiles WHERE id = auth.uid()) -- role değiştiremez
    );

-- Admin her profili okuyabilir
DROP POLICY IF EXISTS profiles_select_admin ON public.profiles;
CREATE POLICY profiles_select_admin ON public.profiles
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- activity_logs: kullanıcı sadece kendi loglarını okur
DROP POLICY IF EXISTS activity_logs_select_own ON public.activity_logs;
CREATE POLICY activity_logs_select_own ON public.activity_logs
    FOR SELECT USING (auth.uid() = user_id);

-- activity_logs: servis rolü her şeyi yazabilir (backend SERVICE_KEY ile yazar)
DROP POLICY IF EXISTS activity_logs_insert_service ON public.activity_logs;
CREATE POLICY activity_logs_insert_service ON public.activity_logs
    FOR INSERT WITH CHECK (TRUE);  -- RLS'yi service_role bypass eder zaten

-- device_sessions: kullanıcı kendi cihazlarını yönetir
DROP POLICY IF EXISTS device_sessions_own ON public.device_sessions;
CREATE POLICY device_sessions_own ON public.device_sessions
    FOR ALL USING (auth.uid() = user_id);

-- ── 6. product_cache — RLS (var olan tabloya ekle) ──────────
ALTER TABLE public.product_cache ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS product_cache_public_read ON public.product_cache;
CREATE POLICY product_cache_public_read ON public.product_cache
    FOR SELECT USING (TRUE);  -- cache herkese açık okunur

DROP POLICY IF EXISTS product_cache_service_write ON public.product_cache;
CREATE POLICY product_cache_service_write ON public.product_cache
    FOR ALL USING (TRUE);     -- yazma sadece service_role ile (backend)

-- ── 7. Helper: kullanıcı rolü sorgusu (RLS'de kullanmak için) ──
CREATE OR REPLACE FUNCTION public.get_my_role()
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

-- Premium özellik kontrolü
CREATE OR REPLACE FUNCTION public.is_premium()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT role IN ('premium', 'admin') FROM public.profiles WHERE id = auth.uid();
$$;
