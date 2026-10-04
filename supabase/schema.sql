-- Run once in the Supabase SQL Editor before enabling APP_MODE=public.
-- Monthly quotas are counted as AI requests for the beta. Subscription webhooks
-- can later update plan, subscription_status, period_end and monthly_request_limit.

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    plan text not null default 'free'
        check (plan in ('free', 'standard', 'pro', 'admin')),
    subscription_status text not null default 'free'
        check (subscription_status in ('free', 'active', 'trialing', 'past_due', 'canceled', 'unpaid')),
    requests_used integer not null default 0 check (requests_used >= 0),
    monthly_request_limit integer not null default 20 check (monthly_request_limit >= 0),
    period_start timestamptz not null default date_trunc('month', now()),
    period_end timestamptz,
    payment_provider text,
    provider_customer_id text,
    provider_subscription_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "Users can read their own profile" on public.profiles;
create policy "Users can read their own profile"
    on public.profiles for select to authenticated
    using (auth.uid() = id);

create or replace function public.create_profile_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (id) values (new.id)
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created_profile on auth.users;
create trigger on_auth_user_created_profile
    after insert on auth.users
    for each row execute procedure public.create_profile_for_new_user();

create or replace function public.reserve_ai_request(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    profile_row public.profiles%rowtype;
    current_period timestamptz := date_trunc('month', now());
begin
    if p_user_id is null then
        raise exception 'user id is required';
    end if;

    insert into public.profiles (id) values (p_user_id)
    on conflict (id) do nothing;

    select * into profile_row
    from public.profiles
    where id = p_user_id
    for update;

    if profile_row.period_start < current_period then
        update public.profiles
        set requests_used = 0,
            period_start = current_period,
            updated_at = now()
        where id = p_user_id
        returning * into profile_row;
    end if;

    if (profile_row.subscription_status in ('canceled', 'unpaid')
        and (profile_row.period_end is null or profile_row.period_end <= now()))
       or (profile_row.subscription_status = 'past_due'
           and (profile_row.period_end is null or profile_row.period_end <= now()))
       or (profile_row.subscription_status in ('active', 'trialing')
           and profile_row.period_end is not null and profile_row.period_end <= now()) then
        update public.profiles
        set plan = 'free',
            subscription_status = 'free',
            monthly_request_limit = 20,
            payment_provider = null,
            provider_subscription_id = null,
            updated_at = now()
        where id = p_user_id
        returning * into profile_row;
    end if;

    if profile_row.plan <> 'admin'
       and profile_row.requests_used >= profile_row.monthly_request_limit then
        return jsonb_build_object(
            'allowed', false,
            'requests_used', profile_row.requests_used,
            'monthly_request_limit', profile_row.monthly_request_limit,
            'plan', profile_row.plan,
            'subscription_status', profile_row.subscription_status
        );
    end if;

    if profile_row.plan <> 'admin' then
        update public.profiles
        set requests_used = requests_used + 1,
            updated_at = now()
        where id = p_user_id
        returning * into profile_row;
    end if;

    return jsonb_build_object(
        'allowed', true,
        'requests_used', profile_row.requests_used,
        'monthly_request_limit', profile_row.monthly_request_limit,
        'plan', profile_row.plan,
        'subscription_status', profile_row.subscription_status
    );
end;
$$;

revoke all on function public.reserve_ai_request(uuid) from public, anon, authenticated;
grant execute on function public.reserve_ai_request(uuid) to service_role;
grant select on public.profiles to authenticated;
revoke insert, update, delete on public.profiles from anon, authenticated;
