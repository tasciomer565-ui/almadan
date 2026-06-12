create table if not exists public.app_state (
  id text primary key,
  data jsonb not null default '{"products":[],"notifications":[]}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.app_state enable row level security;

revoke all on table public.app_state from anon, authenticated;

grant select, insert, update, delete
on table public.app_state
to service_role;

comment on table public.app_state is
  'Server-side application state for the Almadan MVP. Accessed with service_role only.';
