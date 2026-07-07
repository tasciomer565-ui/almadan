-- Sorgu tanıma kelime dağarcığı için ayrı tablo + atomik sayaç artırma.
-- app_state blob'unun aynı yerde büyümesini/yarış durumunu önlemek için
-- product_cache gibi kendi tablosunda tutuluyor.
--
-- Supabase Dashboard → SQL Editor içinde bir kere çalıştırman yeterli.

create table if not exists public.vocabulary (
    word text primary key,
    category text not null default 'GENEL',
    count integer not null default 0,
    updated_at timestamptz not null default now()
);

create index if not exists vocabulary_category_idx on public.vocabulary (category);
create index if not exists vocabulary_count_idx on public.vocabulary (count desc);

-- Atomik "gözlem ekle" fonksiyonu: satır yoksa oluşturur, varsa sayacı
-- arttırır. Kategori kararsızsa daha yüksek delta'ya sahip kategori kazanır.
create or replace function public.increment_vocabulary(
    p_word text,
    p_category text,
    p_delta integer
) returns void as $$
begin
    insert into public.vocabulary (word, category, count, updated_at)
    values (p_word, p_category, p_delta, now())
    on conflict (word) do update
    set
        count = public.vocabulary.count + excluded.count,
        category = case
            when excluded.count > public.vocabulary.count / 2 then excluded.category
            else public.vocabulary.category
        end,
        updated_at = now();
end;
$$ language plpgsql;

-- Toplu (batch) versiyon: tek HTTP isteğiyle birçok kelimeyi aynı anda
-- güncellemek için — kelime başına ayrı istek atmamak (bant genişliği/hız).
-- p_items örneği: '[{"word":"tisort","category":"MODA","count":3}, ...]'
create or replace function public.increment_vocabulary_batch(
    p_items jsonb
) returns void as $$
declare
    item jsonb;
begin
    for item in select * from jsonb_array_elements(p_items)
    loop
        perform public.increment_vocabulary(
            (item->>'word')::text,
            (item->>'category')::text,
            (item->>'count')::integer
        );
    end loop;
end;
$$ language plpgsql;

-- Row Level Security: yalnızca service_role yazabilsin/okuyabilsin
-- (backend zaten SUPABASE_SERVICE_KEY ile bağlanıyor, aynı diğer tablolar gibi).
alter table public.vocabulary enable row level security;

create policy if not exists "service_role_all_vocabulary"
    on public.vocabulary
    for all
    to service_role
    using (true)
    with check (true);
