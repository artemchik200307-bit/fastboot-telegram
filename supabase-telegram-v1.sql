-- FASTBOOT TELEGRAM MODULE V1
-- Выполнить целиком в Supabase SQL Editor.
-- Таблицы защищены RLS. Telegram-сервис использует SERVICE_ROLE_KEY.

create table if not exists public.telegram_accounts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  telegram_user_id bigint not null unique,
  telegram_chat_id bigint not null,
  telegram_username text,
  telegram_first_name text,
  is_active boolean not null default true,
  linked_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.telegram_link_codes (
  user_id uuid primary key references auth.users(id) on delete cascade,
  fastboot_id text not null,
  code text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0,
  used_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.telegram_sessions (
  telegram_user_id bigint not null,
  bot_kind text not null check (bot_kind in ('user','admin')),
  state text not null,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key(telegram_user_id, bot_kind)
);

create table if not exists public.telegram_admin_topics (
  topic_key text primary key,
  group_chat_id bigint not null,
  message_thread_id integer not null,
  title text not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.telegram_notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  destination text not null check (destination in ('user','admin')),
  chat_id bigint,
  topic_key text,
  event_type text not null,
  message_text text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending','processing','sent','failed')),
  attempts integer not null default 0,
  available_at timestamptz not null default now(),
  claimed_at timestamptz,
  sent_at timestamptz,
  error_message text,
  created_at timestamptz not null default now()
);

create index if not exists telegram_notifications_pending_idx
on public.telegram_notifications(status, available_at, created_at);

alter table public.telegram_accounts enable row level security;
alter table public.telegram_link_codes enable row level security;
alter table public.telegram_sessions enable row level security;
alter table public.telegram_admin_topics enable row level security;
alter table public.telegram_notifications enable row level security;

drop policy if exists telegram_accounts_select_own
on public.telegram_accounts;

create policy telegram_accounts_select_own
on public.telegram_accounts
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists telegram_link_codes_own
on public.telegram_link_codes;

create policy telegram_link_codes_own
on public.telegram_link_codes
for select
to authenticated
using (user_id = auth.uid());


insert into public.telegram_admin_topics(
  topic_key, group_chat_id, message_thread_id, title
)
values
  ('users',       -1004434268756, 4,  'Пользователи'),
  ('deposits',    -1004434268756, 7,  'Пополнения'),
  ('withdrawals', -1004434268756, 8,  'Выводы'),
  ('ai_bot',      -1004434268756, 9,  'AI-бот'),
  ('trading',     -1004434268756, 10, 'Торговля'),
  ('referrals',   -1004434268756, 11, 'Рефералы'),
  ('errors',      -1004434268756, 12, 'Ошибки'),
  ('reports',     -1004434268756, 13, 'Отчёты'),
  ('system',      -1004434268756, 14, 'Система'),
  ('finance',     -1004434268756, 16, 'Финансы платформы')
on conflict(topic_key) do update
set
  group_chat_id = excluded.group_chat_id,
  message_thread_id = excluded.message_thread_id,
  title = excluded.title,
  updated_at = now();


create or replace function public.telegram_generate_link_code()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := auth.uid();
  v_fastboot_id text;
  v_code text;
begin
  if v_user_id is null then
    raise exception 'Пользователь не авторизован';
  end if;

  select p.fastboot_id
  into v_fastboot_id
  from public.profiles p
  where p.id = v_user_id;

  if v_fastboot_id is null then
    raise exception 'Профиль пользователя не найден';
  end if;

  v_code := lpad(floor(random() * 1000000)::integer::text, 6, '0');

  insert into public.telegram_link_codes(
    user_id,
    fastboot_id,
    code,
    expires_at,
    attempts,
    used_at,
    created_at
  )
  values(
    v_user_id,
    v_fastboot_id,
    v_code,
    now() + interval '10 minutes',
    0,
    null,
    now()
  )
  on conflict(user_id) do update
  set
    fastboot_id = excluded.fastboot_id,
    code = excluded.code,
    expires_at = excluded.expires_at,
    attempts = 0,
    used_at = null,
    created_at = now();

  return jsonb_build_object(
    'fastboot_id', v_fastboot_id,
    'code', v_code,
    'expires_at', now() + interval '10 minutes'
  );
end;
$$;

revoke all on function public.telegram_generate_link_code() from public;
grant execute on function public.telegram_generate_link_code() to authenticated;


create or replace function public.telegram_prepare_link(
  p_fastboot_id text,
  p_telegram_user_id bigint
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid;
begin
  select p.id
  into v_user_id
  from public.profiles p
  where upper(p.fastboot_id) = upper(trim(p_fastboot_id));

  if v_user_id is null then
    return jsonb_build_object('found', false);
  end if;

  if exists(
    select 1
    from public.telegram_accounts a
    where a.user_id = v_user_id
      and a.telegram_user_id <> p_telegram_user_id
      and a.is_active = true
  ) then
    return jsonb_build_object(
      'found', false,
      'message', 'Аккаунт уже привязан к другому Telegram'
    );
  end if;

  return jsonb_build_object('found', true);
end;
$$;


create or replace function public.telegram_confirm_link(
  p_fastboot_id text,
  p_code text,
  p_telegram_user_id bigint,
  p_telegram_chat_id bigint,
  p_username text default null,
  p_first_name text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.telegram_link_codes;
begin
  select c.*
  into v_row
  from public.telegram_link_codes c
  where upper(c.fastboot_id) = upper(trim(p_fastboot_id))
  for update;

  if not found then
    return jsonb_build_object(
      'success', false,
      'message', 'Сначала создайте код в личном кабинете'
    );
  end if;

  if v_row.used_at is not null then
    return jsonb_build_object(
      'success', false,
      'message', 'Код уже использован'
    );
  end if;

  if now() > v_row.expires_at then
    return jsonb_build_object(
      'success', false,
      'message', 'Срок действия кода истёк'
    );
  end if;

  if v_row.attempts >= 5 then
    return jsonb_build_object(
      'success', false,
      'message', 'Слишком много попыток. Создайте новый код'
    );
  end if;

  if v_row.code <> trim(p_code) then
    update public.telegram_link_codes
    set attempts = attempts + 1
    where user_id = v_row.user_id;

    return jsonb_build_object(
      'success', false,
      'message', 'Неверный код'
    );
  end if;

  delete from public.telegram_accounts
  where telegram_user_id = p_telegram_user_id
    and user_id <> v_row.user_id;

  insert into public.telegram_accounts(
    user_id,
    telegram_user_id,
    telegram_chat_id,
    telegram_username,
    telegram_first_name,
    is_active,
    linked_at,
    updated_at
  )
  values(
    v_row.user_id,
    p_telegram_user_id,
    p_telegram_chat_id,
    nullif(trim(coalesce(p_username, '')), ''),
    nullif(trim(coalesce(p_first_name, '')), ''),
    true,
    now(),
    now()
  )
  on conflict(user_id) do update
  set
    telegram_user_id = excluded.telegram_user_id,
    telegram_chat_id = excluded.telegram_chat_id,
    telegram_username = excluded.telegram_username,
    telegram_first_name = excluded.telegram_first_name,
    is_active = true,
    linked_at = now(),
    updated_at = now();

  update public.telegram_link_codes
  set used_at = now()
  where user_id = v_row.user_id;

  insert into public.telegram_notifications(
    user_id,
    destination,
    topic_key,
    event_type,
    message_text
  )
  values(
    v_row.user_id,
    'admin',
    'users',
    'telegram_linked',
    '<b>Telegram привязан</b>' || E'\n\n' ||
    'FASTBOOT ID: <code>' || v_row.fastboot_id || '</code>' || E'\n' ||
    'Telegram ID: <code>' || p_telegram_user_id::text || '</code>'
  );

  return jsonb_build_object(
    'success', true,
    'fastboot_id', v_row.fastboot_id
  );
end;
$$;


create or replace function public.telegram_resolve_user(
  p_telegram_user_id bigint
)
returns uuid
language sql
security definer
set search_path = public
as $$
  select a.user_id
  from public.telegram_accounts a
  where a.telegram_user_id = p_telegram_user_id
    and a.is_active = true
  limit 1;
$$;


create or replace function public.telegram_get_dashboard(
  p_telegram_user_id bigint
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := public.telegram_resolve_user(p_telegram_user_id);
  v_wallet public.wallets;
  v_ai_active boolean := false;
  v_ai_profit numeric := 0;
  v_ai_fees numeric := 0;
  v_ai_count bigint := 0;
  v_next_withdrawal timestamptz;
begin
  if v_user_id is null then
    return null;
  end if;

  select *
  into v_wallet
  from public.wallets
  where user_id = v_user_id;

  select coalesce(a.is_active, false)
  into v_ai_active
  from public.ai_bot_accounts a
  where a.user_id = v_user_id;

  select
    coalesce(sum(coalesce(r.net_pnl_amount, r.pnl_amount, 0)), 0),
    coalesce(sum(coalesce(r.platform_fee_amount, 0)), 0),
    count(*)
  into v_ai_profit, v_ai_fees, v_ai_count
  from public.user_ai_trade_results r
  where r.user_id = v_user_id;

  select max(f.created_at) + interval '14 days'
  into v_next_withdrawal
  from public.funding_requests f
  where f.user_id = v_user_id
    and f.type = 'withdraw'
    and f.status not in ('rejected','cancelled');

  return jsonb_build_object(
    'spot_balance', coalesce(v_wallet.spot_balance, 0),
    'bot_balance', coalesce(v_wallet.bot_balance, 0),
    'trading_balance', coalesce(v_wallet.trading_balance, 0),
    'total_balance',
      coalesce(v_wallet.spot_balance, 0)
      + coalesce(v_wallet.bot_balance, 0)
      + coalesce(v_wallet.trading_balance, 0),
    'withdraw_available', coalesce(v_wallet.spot_balance, 0),
    'next_withdrawal_at', v_next_withdrawal,
    'ai_active', v_ai_active,
    'ai_net_profit', v_ai_profit,
    'ai_fees', v_ai_fees,
    'ai_trades_count', v_ai_count
  );
end;
$$;


create or replace function public.telegram_get_ai_history(
  p_telegram_user_id bigint,
  p_limit integer default 10
)
returns setof public.user_ai_trade_results
language sql
security definer
set search_path = public
as $$
  select r.*
  from public.user_ai_trade_results r
  where r.user_id = public.telegram_resolve_user(p_telegram_user_id)
  order by coalesce(r.created_at, r.closed_at) desc, r.id desc
  limit greatest(1, least(coalesce(p_limit, 10), 50));
$$;


create or replace function public.telegram_get_referral_dashboard(
  p_telegram_user_id bigint
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := public.telegram_resolve_user(p_telegram_user_id);
  v_account public.referral_accounts;
  v_count bigint := 0;
  v_level text := 'Start';
  v_percent numeric := 5;
begin
  if v_user_id is null then
    return null;
  end if;

  select *
  into v_account
  from public.referral_accounts
  where user_id = v_user_id;

  select count(*)
  into v_count
  from public.referral_accounts
  where referrer_id = v_user_id;

  if v_count >= 100 then
    v_level := 'Platinum';
    v_percent := 40;
  elsif v_count >= 50 then
    v_level := 'Gold';
    v_percent := 25;
  elsif v_count >= 10 then
    v_level := 'Silver';
    v_percent := 15;
  end if;

  return jsonb_build_object(
    'referral_code', v_account.referral_code,
    'level_name', v_level,
    'reward_percent', v_percent,
    'total_referrals', v_count,
    'total_earned', coalesce(v_account.total_earned, 0),
    'available_balance', coalesce(v_account.available_balance, 0)
  );
end;
$$;


create or replace function public.telegram_create_deposit_request(
  p_telegram_user_id bigint,
  p_amount numeric,
  p_txid text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := public.telegram_resolve_user(p_telegram_user_id);
  v_id uuid;
begin
  if v_user_id is null then
    raise exception 'Telegram не привязан';
  end if;

  if p_amount < 10 then
    raise exception 'Минимальное пополнение — 10 USDT';
  end if;

  if length(trim(p_txid)) < 20 then
    raise exception 'Некорректный TXID';
  end if;

  if exists(
    select 1
    from public.funding_requests
    where lower(txid) = lower(trim(p_txid))
  ) then
    raise exception 'Этот TXID уже использован';
  end if;

  insert into public.funding_requests(
    user_id,type,amount,asset,network,txid,wallet_address,status,details
  )
  values(
    v_user_id,'deposit',p_amount,'USDT','TRC20',trim(p_txid),
    'TVwAj44gxbPFTDH3KifsmqjfCtF54tj4DC',
    'pending','Telegram deposit request'
  )
  returning id into v_id;

  return v_id;
end;
$$;


create or replace function public.telegram_create_withdrawal_request(
  p_telegram_user_id bigint,
  p_amount numeric,
  p_wallet_address text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := public.telegram_resolve_user(p_telegram_user_id);
  v_wallet public.wallets;
  v_last timestamptz;
  v_id uuid;
begin
  if v_user_id is null then
    raise exception 'Telegram не привязан';
  end if;

  if p_amount < 50 then
    raise exception 'Минимальный вывод — 50 USDT';
  end if;

  if length(trim(p_wallet_address)) <> 34
     or left(trim(p_wallet_address), 1) <> 'T' then
    raise exception 'Некорректный TRC20 адрес';
  end if;

  select *
  into v_wallet
  from public.wallets
  where user_id = v_user_id
  for update;

  if coalesce(v_wallet.spot_balance, 0) < p_amount then
    raise exception 'Недостаточно средств на основном счёте';
  end if;

  if exists(
    select 1
    from public.funding_requests
    where user_id = v_user_id
      and type = 'withdraw'
      and status = 'pending'
  ) then
    raise exception 'У вас уже есть заявка на вывод';
  end if;

  select max(created_at)
  into v_last
  from public.funding_requests
  where user_id = v_user_id
    and type = 'withdraw'
    and status not in ('rejected','cancelled');

  if v_last is not null and now() < v_last + interval '14 days' then
    raise exception 'Следующий вывод доступен %',
      to_char(v_last + interval '14 days', 'DD.MM.YYYY');
  end if;

  insert into public.funding_requests(
    user_id,type,amount,asset,network,wallet_address,status,details
  )
  values(
    v_user_id,'withdraw',p_amount,'USDT','TRC20',
    trim(p_wallet_address),'pending','Telegram withdrawal request'
  )
  returning id into v_id;

  return v_id;
end;
$$;


create or replace function public.telegram_admin_platform_stats()
returns jsonb
language sql
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'users_count', (select count(*) from public.profiles),
    'active_ai_count',
      (select count(*) from public.ai_bot_accounts where is_active = true),
    'spot_total',
      (select coalesce(sum(spot_balance),0) from public.wallets),
    'bot_total',
      (select coalesce(sum(bot_balance),0) from public.wallets),
    'trading_total',
      (select coalesce(sum(trading_balance),0) from public.wallets),
    'all_balance',
      (
        select coalesce(
          sum(spot_balance + bot_balance + trading_balance),
          0
        )
        from public.wallets
      ),
    'platform_fees',
      (
        select coalesce(sum(platform_fee_amount),0)
        from public.user_ai_trade_results
      ),
    'pending_deposits',
      (
        select count(*)
        from public.funding_requests
        where type='deposit' and status='pending'
      ),
    'pending_withdrawals',
      (
        select count(*)
        from public.funding_requests
        where type='withdraw' and status='pending'
      )
  );
$$;


create or replace function public.telegram_claim_notifications(
  p_limit integer default 30
)
returns setof public.telegram_notifications
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with selected as (
    select n.id
    from public.telegram_notifications n
    where n.status = 'pending'
      and n.available_at <= now()
    order by n.created_at
    for update skip locked
    limit greatest(1, least(coalesce(p_limit,30),100))
  )
  update public.telegram_notifications n
  set
    status = 'processing',
    claimed_at = now(),
    attempts = attempts + 1
  from selected
  where n.id = selected.id
  returning n.*;
end;
$$;


create or replace function public.telegram_finish_notification(
  p_notification_id uuid,
  p_status text,
  p_error_message text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.telegram_notifications
  set
    status = p_status,
    sent_at = case when p_status='sent' then now() else sent_at end,
    error_message = p_error_message
  where id = p_notification_id;
end;
$$;


create or replace function public.telegram_notify_new_profile()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.telegram_notifications(
    user_id,destination,topic_key,event_type,message_text
  )
  values(
    new.id,
    'admin',
    'users',
    'user_registered',
    '<b>Новый пользователь</b>' || E'\n\n' ||
    'ID: <code>' || coalesce(new.fastboot_id,'—') || '</code>' || E'\n' ||
    'Username: ' || coalesce(new.username,'—') || E'\n' ||
    'Email: ' || coalesce(new.email,'—')
  );

  return new;
end;
$$;

drop trigger if exists telegram_profile_created
on public.profiles;

create trigger telegram_profile_created
after insert on public.profiles
for each row execute function public.telegram_notify_new_profile();


create or replace function public.telegram_notify_funding()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_fastboot_id text;
  v_topic text;
begin
  select fastboot_id
  into v_fastboot_id
  from public.profiles
  where id = new.user_id;

  v_topic := case
    when new.type='deposit' then 'deposits'
    else 'withdrawals'
  end;

  insert into public.telegram_notifications(
    user_id,destination,topic_key,event_type,message_text,payload
  )
  values(
    new.user_id,
    'admin',
    v_topic,
    'funding_request_created',
    case
      when new.type='deposit' then '<b>Новая заявка на пополнение</b>'
      else '<b>Новая заявка на вывод</b>'
    end || E'\n\n' ||
    'ID: <code>' || coalesce(v_fastboot_id,'—') || '</code>' || E'\n' ||
    'Сумма: <b>' || new.amount::text || ' USDT</b>' || E'\n' ||
    'Сеть: ' || coalesce(new.network,'TRC20'),
    to_jsonb(new)
  );

  return new;
end;
$$;

drop trigger if exists telegram_funding_created
on public.funding_requests;

create trigger telegram_funding_created
after insert on public.funding_requests
for each row execute function public.telegram_notify_funding();


create or replace function public.telegram_notify_ai_result()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_chat_id bigint;
  v_fastboot_id text;
  v_net numeric;
begin
  select a.telegram_chat_id, p.fastboot_id
  into v_chat_id, v_fastboot_id
  from public.telegram_accounts a
  join public.profiles p on p.id=a.user_id
  where a.user_id=new.user_id
    and a.is_active=true;

  v_net := coalesce(new.net_pnl_amount, new.pnl_amount, 0);

  if v_chat_id is not null then
    insert into public.telegram_notifications(
      user_id,destination,chat_id,event_type,message_text,payload
    )
    values(
      new.user_id,
      'user',
      v_chat_id,
      'ai_trade_closed',
      '<b>✅ AI-сделка закрыта</b>' || E'\n\n' ||
      '<b>' || new.pair || '</b> · ' || new.side || E'\n' ||
      'Результат: <b>' ||
      case when v_net > 0 then '+' else '' end ||
      v_net::text || ' USDT</b>' || E'\n' ||
      'Доходность: ' || new.pnl_percent::text || '%' || E'\n' ||
      'Комиссия: ' || coalesce(new.platform_fee_amount,0)::text || ' USDT',
      to_jsonb(new)
    );
  end if;

  insert into public.telegram_notifications(
    user_id,destination,topic_key,event_type,message_text,payload
  )
  values(
    new.user_id,
    'admin',
    'trading',
    'ai_trade_closed',
    '<b>AI-сделка пользователя</b>' || E'\n\n' ||
    'ID: <code>' || coalesce(v_fastboot_id,'—') || '</code>' || E'\n' ||
    '<b>' || new.pair || '</b> · ' || new.side || E'\n' ||
    'Результат: <b>' || v_net::text || ' USDT</b>',
    to_jsonb(new)
  );

  return new;
end;
$$;

drop trigger if exists telegram_ai_result_created
on public.user_ai_trade_results;

create trigger telegram_ai_result_created
after insert on public.user_ai_trade_results
for each row execute function public.telegram_notify_ai_result();


revoke all on function public.telegram_prepare_link(text,bigint) from public;
revoke all on function public.telegram_confirm_link(text,text,bigint,bigint,text,text) from public;
revoke all on function public.telegram_resolve_user(bigint) from public;
revoke all on function public.telegram_get_dashboard(bigint) from public;
revoke all on function public.telegram_get_ai_history(bigint,integer) from public;
revoke all on function public.telegram_get_referral_dashboard(bigint) from public;
revoke all on function public.telegram_create_deposit_request(bigint,numeric,text) from public;
revoke all on function public.telegram_create_withdrawal_request(bigint,numeric,text) from public;
revoke all on function public.telegram_admin_platform_stats() from public;
revoke all on function public.telegram_claim_notifications(integer) from public;
revoke all on function public.telegram_finish_notification(uuid,text,text) from public;
