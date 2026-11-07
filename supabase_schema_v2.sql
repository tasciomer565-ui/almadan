-- ============================================================================
-- Almadan.app & Ne Giysem — Supabase İlişkisel Şema v2 (Cloud Sync & LWW)
-- Aşama 1.4: Tek satırlık `app_state` JSONB yapısından ilişkisel UUID v4 +
-- Tombstone (is_deleted) + Last-Write-Wins (updated_at) mimarisine geçiş.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Eski tek satırlık JSONB tablosunu kullanımdan kaldır
DROP TABLE IF EXISTS public.app_state CASCADE;

-- Ortak updated_at tetikleyici fonksiyonu
CREATE OR REPLACE FUNCTION public.trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.updated_at IS NULL THEN
    NEW.updated_at = NOW();
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. USERS TABLOSU
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE,
  email TEXT,
  display_name TEXT,
  sensitivity TEXT NOT NULL DEFAULT 'normal',
  transport TEXT NOT NULL DEFAULT 'yuruyus',
  is_premium BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_users_user_id ON public.users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON public.users(updated_at DESC);

-- ============================================================================
-- 2. GARMENTS (GARDIROP PARÇALARI) TABLOSU
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.garments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  sub_kind TEXT,
  color TEXT NOT NULL,
  min_temp_c DOUBLE PRECISION NOT NULL DEFAULT 10.0,
  max_temp_c DOUBLE PRECISION NOT NULL DEFAULT 25.0,
  season TEXT NOT NULL DEFAULT 'dortMevsim',
  thickness TEXT NOT NULL DEFAULT 'orta',
  waterproof BOOLEAN NOT NULL DEFAULT FALSE,
  is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
  is_dirty BOOLEAN NOT NULL DEFAULT FALSE,
  storage_location TEXT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  purchase_date TIMESTAMPTZ,
  photo_path TEXT,
  image_path TEXT,
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_garments_user_updated ON public.garments(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_garments_user_deleted ON public.garments(user_id, is_deleted);

-- ============================================================================
-- 3. OUTFIT_LOGS (GÜNLÜK KOMBİN GEÇMİŞİ VE AKŞAM GERİ BİLDİRİMLERİ) TABLOSU
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.outfit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  date TIMESTAMPTZ NOT NULL,
  garment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  evening_answer TEXT,
  event_type TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_outfit_logs_user_updated ON public.outfit_logs(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_outfit_logs_user_date ON public.outfit_logs(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_outfit_logs_user_deleted ON public.outfit_logs(user_id, is_deleted);

-- ============================================================================
-- 4. PINNED_DAYS (SABİTLENMİŞ GELECEK GÜN KOMBİNLERİ) TABLOSU
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.pinned_days (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  date TIMESTAMPTZ NOT NULL,
  garment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_pinned_days_user_updated ON public.pinned_days(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_pinned_days_user_date ON public.pinned_days(user_id, date);
CREATE INDEX IF NOT EXISTS idx_pinned_days_user_deleted ON public.pinned_days(user_id, is_deleted);

-- ============================================================================
-- 5. TRIPS (SEYAHAT VE BAVUL LİSTELERİ) TABLOSU
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.trips (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  city TEXT NOT NULL,
  start_date TIMESTAMPTZ NOT NULL,
  end_date TIMESTAMPTZ NOT NULL,
  packing_checks JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_trips_user_updated ON public.trips(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_user_deleted ON public.trips(user_id, is_deleted);

-- ============================================================================
-- 6. TRANSACTIONS (GELİR / GİDER VE FİŞ İŞLEMLERİ) TABLOSU (Aşama 1.7)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
  type TEXT NOT NULL DEFAULT 'expense' CHECK (type IN ('income', 'expense')),
  category TEXT NOT NULL,
  merchant_name TEXT NOT NULL,
  transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
  receipt_image_url TEXT,
  tax_amount NUMERIC(12, 2) DEFAULT 0,
  items JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON public.transactions(user_id, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON public.transactions(user_id, category);

-- ============================================================================
-- 7. BUDGETS (AYLIK KATEGORİ BAZLI BÜTÇE LİMİTLERİ) TABLOSU (Aşama 1.7)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.budgets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  limit_amount NUMERIC(12, 2) NOT NULL CHECK (limit_amount > 0),
  current_spent NUMERIC(12, 2) NOT NULL DEFAULT 0,
  month_year TEXT NOT NULL, -- Format: 'YYYY-MM' (Örn: '2026-11')
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT uq_budgets_user_category_month UNIQUE (user_id, category, month_year)
);

CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON public.budgets(user_id, month_year);

-- ============================================================================
-- 8. PRICE_ALERTS (OTONOM FİYAT İZLEME VE ALARM) TABLOSU (Aşama 1.8)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.price_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  product_name TEXT NOT NULL,
  product_url TEXT NOT NULL,
  target_price NUMERIC(12, 2) NOT NULL CHECK (target_price > 0),
  current_price NUMERIC(12, 2) NOT NULL CHECK (current_price >= 0),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_price_alerts_user_active ON public.price_alerts(user_id, is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_price_alerts_active_scan ON public.price_alerts(is_active) WHERE is_active = TRUE;

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLİTİKALARI
-- Her kullanıcı yalnızca kendi user_id'sine ait satırları okuyabilir/yazabilir.
-- ============================================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.garments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outfit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pinned_days ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_self_policy ON public.users;
CREATE POLICY users_self_policy ON public.users
  FOR ALL USING (auth.uid() = id OR auth.uid() = user_id)
  WITH CHECK (auth.uid() = id OR auth.uid() = user_id);

DROP POLICY IF EXISTS garments_owner_policy ON public.garments;
CREATE POLICY garments_owner_policy ON public.garments
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS outfit_logs_owner_policy ON public.outfit_logs;
CREATE POLICY outfit_logs_owner_policy ON public.outfit_logs
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS pinned_days_owner_policy ON public.pinned_days;
CREATE POLICY pinned_days_owner_policy ON public.pinned_days
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS trips_owner_policy ON public.trips;
CREATE POLICY trips_owner_policy ON public.trips
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS transactions_owner_policy ON public.transactions;
CREATE POLICY transactions_owner_policy ON public.transactions
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS budgets_owner_policy ON public.budgets;
CREATE POLICY budgets_owner_policy ON public.budgets
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS price_alerts_owner_policy ON public.price_alerts;
CREATE POLICY price_alerts_owner_policy ON public.price_alerts
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

GRANT ALL ON public.users, public.garments, public.outfit_logs, public.pinned_days, public.trips, public.transactions, public.budgets, public.price_alerts TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.users, public.garments, public.outfit_logs, public.pinned_days, public.trips, public.transactions, public.budgets, public.price_alerts TO authenticated;
