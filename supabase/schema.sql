-- =====================================================================
-- CareerTrack AI - database schema for Supabase (PostgreSQL)
-- Run this ONCE: Supabase dashboard -> SQL Editor -> New query -> paste -> Run.
-- It is safe to run again (uses IF NOT EXISTS / OR REPLACE).
-- =====================================================================

-- ---------- Main table: one row per job application ----------
create table if not exists public.job_applications (
    id               uuid primary key default gen_random_uuid(),
    company_name     text not null check (char_length(trim(company_name)) > 0),
    job_title        text not null check (char_length(trim(job_title)) > 0),
    job_description  text,
    job_url          text,
    application_date date,
    status           text not null default 'Saved'
                     check (status in ('Saved','Applied','Assessment','Interview','Offer','Rejected','Withdrawn')),
    follow_up_date   date,
    notes            text,
    resume_version   text,
    location         text,
    extracted_info   jsonb,          -- result of the AI job-description extraction
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    constraint follow_up_not_before_applied
        check (follow_up_date is null or application_date is null or follow_up_date >= application_date)
);

-- ---------- History table: one row per status change ----------
create table if not exists public.application_history (
    id             uuid primary key default gen_random_uuid(),
    application_id uuid not null references public.job_applications(id) on delete cascade,
    old_status     text,
    new_status     text not null,
    note           text,
    changed_at     timestamptz not null default now()
);

-- ---------- Indexes for the filters used by the app ----------
create index if not exists idx_apps_status     on public.job_applications (status);
create index if not exists idx_apps_applied    on public.job_applications (application_date);
create index if not exists idx_apps_follow_up  on public.job_applications (follow_up_date);
create index if not exists idx_apps_created    on public.job_applications (created_at desc);
create index if not exists idx_history_app     on public.application_history (application_id, changed_at desc);

-- ---------- Keep updated_at fresh automatically ----------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_apps_updated_at on public.job_applications;
create trigger trg_apps_updated_at
    before update on public.job_applications
    for each row execute function public.set_updated_at();

-- ---------- Security ----------
-- Row Level Security ON with NO policies = the public "anon" key can read/write nothing.
-- Only our FastAPI backend (using the server-side secret / service_role key) can access the data.
alter table public.job_applications  enable row level security;
alter table public.application_history enable row level security;
