-- Sprint 10: Tüketim & Hatırlatıcı Modülü
-- Ürün bazlı tekrar-alım hatırlatıcıları

CREATE TABLE IF NOT EXISTS product_reminders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    product_url         TEXT NOT NULL,
    product_title       TEXT,
    last_purchase_date  DATE NOT NULL,
    reorder_days        INTEGER NOT NULL CHECK (reorder_days > 0),
    remind_before_days  INTEGER NOT NULL DEFAULT 5 CHECK (remind_before_days >= 0),
    notified            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Hesaplanan alanlar için index (tarih hesaplamaları uygulama katmanında)
CREATE INDEX IF NOT EXISTS idx_reminders_user   ON product_reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_notify ON product_reminders(notified, last_purchase_date, reorder_days, remind_before_days);

-- RLS
ALTER TABLE product_reminders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_own_reminders" ON product_reminders
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "service_role_all_reminders" ON product_reminders
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Otomatik updated_at
CREATE OR REPLACE FUNCTION update_reminders_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_reminders_updated_at ON product_reminders;
CREATE TRIGGER trg_reminders_updated_at
    BEFORE UPDATE ON product_reminders
    FOR EACH ROW EXECUTE FUNCTION update_reminders_updated_at();
