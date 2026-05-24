# IIM Calcutta Alumni — Telegram Group with Directory-Backed Verification

**Status:** Design — approved for planning
**Date:** 2026-05-24
**Owner:** acharya.abhishek04@gmail.com

---

## 1. Overview

Build a verified-membership Telegram supergroup for IIM Calcutta alumni. Joining is gated by a verification bot that proves the joiner is in the official IIM C alumni directory (`Joka_Directory_Final.xlsx`, 38,494 records). Verified members are bound 1:1 to a directory record so a single alumni identity can only be claimed by one Telegram account, ever.

The group itself is a single Telegram supergroup with Topics enabled (forum-style threads inside one chat space). Verification is operated by a small admin team (the owner plus 2–3 trusted volunteer admins) through a small web dashboard. The system is built and deployed on free-tier infrastructure end-to-end.

## 2. Goals

- A new joiner who is an IIM C alum can verify themselves in under 2 minutes via email OTP or LinkedIn sign-in, with no human in the loop in the common case.
- The system never allows a non-alum to join the supergroup.
- An alumni record can be claimed by exactly one Telegram account at a time; re-claim requires explicit admin action with an audit trail.
- The 38k-row directory's PII is never exposed publicly, and every admin view of a record is logged.
- The admin team can drain the manual-review queue (estimated up to ~2,700 lifetime cases) without bespoke tooling; the dashboard is humane to use.

## 3. Non-Goals (v1 exclusions)

The following are deliberately deferred to keep v1 shippable:

- **A member-facing portal** (profile management, directory browsing, opt-into-sub-groups). Slot left in the design but not built.
- **LinkedIn profile scraping** for follower count / education parsing. Out of scope: against LinkedIn ToS and fragile. Human-in-loop in the admin queue covers the same need.
- **Multiple Telegram groups** (per-batch, per-program, per-city). v1 is a single supergroup with Topics.
- **SMS OTP**. Mobile coverage in the directory is 27% — not worth the integration cost for v1.
- **Native mobile app** of any kind.
- **Real-time analytics / cohort dashboards.**
- **Automated directory refreshes** from any upstream source. v1 takes an Excel re-import as a manual, audit-logged event.

## 4. Directory: Data Context

The source dataset is `Joka_Directory_Final.xlsx`, sheet `All Students`, 38,494 rows × 27 columns. Field-coverage measured at design time:

| Field | Coverage | Use in v1 |
|---|---|---|
| Name | 98.9% | Display + lookup |
| Email | 93.3% | Primary OTP channel; LinkedIn email match |
| Reg Number | 81.4% | Primary lookup key |
| Status (`Alumni`/`Student`/NULL) | 61.5% | Informational only — not a filter (too many NULLs) |
| Batch Year | 63.3% | Display name + secondary lookup |
| Personal Email | 26.8% | Secondary OTP / LinkedIn match channel |
| Mobile | 26.7% | Not used in v1 (no SMS OTP) |
| LinkedIn URL | 8.3% | Informational; not used for matching |

**Implication:** email-based matching is the workhorse. LinkedIn-URL-based matching is too sparse to be a primary path.

## 5. Authorization & PII Posture

The directory is **unofficial** — it circulates among alumni but is not blessed by the institute's alumni office at the time of v1 launch. The entire design is defensive in consequence:

- The `.xlsx` file is **never** committed to git. `*.xlsx` is `.gitignore`'d. The repo has been freshly `git init`'d to ensure no prior history contains the file.
- The bot **never echoes directory data back to users** in DMs. The only acknowledgement of a record being found is a masked email (`s••••@gmail.com`) at the OTP step.
- The bot **never leaks directory data into the group**. The only thing visible is each member's canonical display name string (e.g., `Suresh Iyer (PGP 2015)`).
- The admin dashboard is the **only surface** where full PII is visible, and every view is logged in `pii_access_log`.
- No public HTTP API exists. The dashboard renders server-side HTML; no JSON endpoints are exposed.

## 6. System Architecture

Two deployable services sharing one Postgres database:

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  Telegram (user side)    │        │  Browser (admin side)    │
│  - DMs with bot          │        │  - Admin dashboard       │
│  - Joins supergroup      │        │  - Google SSO login      │
└────────────┬─────────────┘        └────────────┬─────────────┘
             │                                   │
             │ webhooks / long-poll              │ HTTPS (Caddy)
             ▼                                   ▼
   ┌──────────────────┐              ┌──────────────────────┐
   │  bot service     │              │  admin web service   │
   │  Python /        │              │  Python / FastAPI    │
   │  aiogram         │              │  + Jinja2 + HTMX     │
   │  - verify FSM    │              │  - queue / cases     │
   │  - OTP send      │              │  - members / audit   │
   │  - LinkedIn OIDC │              │  - admin mgmt        │
   │  - join policing │              │                      │
   │  - hourly recon  │              │                      │
   └────────┬─────────┘              └─────────┬────────────┘
            │                                   │
            └─────────────┬─────────────────────┘
                          ▼
                  ┌───────────────┐        ┌─────────────────┐
                  │  Postgres     │        │  Brevo (SMTP)   │
                  │  (Supabase)   │        │  OTP delivery   │
                  └───────────────┘        └─────────────────┘
```

**Service boundaries:**

- The **bot** is the only thing that talks to Telegram and the only thing that sends OTPs. It does not expose HTTP to end users beyond the LinkedIn OAuth callback URL.
- The **admin dashboard** is the only human surface for full PII. Auth: Google SSO + allow-list against the `admins` table.
- The **Postgres database** is shared. Each service holds a connection string with a database role scoped to its minimum needed permissions.

## 7. Verification Flow

Two co-equal paths, both terminating in the same `members`-row creation transaction.

```
                  ┌──────────────────────────────────┐
                  │  t.me/IIMCAlumBot greets user    │
                  │  "Verify with Email or LinkedIn?"│
                  └───────────┬──────────────────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
  ┌──────────────────────┐         ┌──────────────────────────┐
  │  PATH A — Email OTP  │         │  PATH B — LinkedIn       │
  │                      │         │                          │
  │ Ask: Reg# (or Name+  │         │ Bot DMs OAuth link →     │
  │ Batch+Program)       │         │ browser → LinkedIn OIDC  │
  │ ↓                    │         │ ↓                        │
  │ Look up in `alumni`  │         │ Receive {name, verified  │
  │ ↓                    │         │ email, profile_url, pic} │
  │ Mask + show email    │         │ ↓                        │
  │ "•••@gmail.com"      │         │ Auto-match verified email│
  │ ↓                    │         │ against alumni table     │
  │ Send 6-digit OTP     │         │ (Email OR Personal Email)│
  │ (10-min TTL, 1-use)  │         │ ↓                        │
  │ ↓                    │         │ Match? ── yes ──┐        │
  │ Verify code (≤3 try) │         │   │             │        │
  └─────────┬────────────┘         │   no            │        │
            │                      │   │             │        │
            │                      │   ▼             │        │
            │                      │ Queue for admin │        │
            │                      │ review with     │        │
            │                      │ LinkedIn URL +  │        │
            │                      │ pic prefilled   │        │
            │                      └───┬─────────────┘        │
            │                          │                      │
            │                          ▼                      ▼
            │                ┌───────────────────┐  ┌──────────────────┐
            │                │  Admin dashboard  │  │  AUTO-VERIFIED   │
            │                │  approves/rejects │  │                  │
            │                └─────────┬─────────┘  └────────┬─────────┘
            │                          │                     │
            └──────────────┬───────────┴─────────────────────┘
                           ▼
                  ┌─────────────────────────────────────┐
                  │  Acquire lock on alumni_id          │
                  │  (UNIQUE partial index on members.  │
                  │  alumni_id WHERE status='active'    │
                  │  prevents double-claim)             │
                  │  ↓                                  │
                  │  Ask display name                   │
                  │  (default: "Real Name (Prog Batch)")│
                  │  ↓                                  │
                  │  Issue one-time invite link         │
                  │  (member_limit=1, 24h TTL)          │
                  │  ↓                                  │
                  │  Record member row + audit log      │
                  └─────────────────────────────────────┘
```

### 7.1 Path A — Email OTP

1. User DMs the bot, picks "Verify with Email."
2. Bot asks for Reg Number. If user doesn't have it, fallback to (Name + Batch Year + Program).
3. Bot looks up the matching row in `alumni`. If 0 results → admin-review queue. If multiple results → bot asks for additional discriminator (Batch + Program).
4. Bot shows the masked email (`s••••@gmail.com`) and confirms before sending.
5. Bot sends 6-digit OTP via Brevo to the registered email. TTL 10 min, single-use.
6. User replies with code. Max 3 attempts. Wrong-third-time → admin-review queue.
7. On success, proceed to the shared "claim and bind" finalization step (§7.3).

### 7.2 Path B — LinkedIn sign-in

1. User DMs the bot, picks "Verify with LinkedIn."
2. Bot generates a `state` token (random 32 bytes) and a 15-min-TTL row in `linkedin_auth_sessions`. DMs an OAuth URL that opens a browser.
3. User completes LinkedIn OIDC. Callback endpoint on the bot service receives `{state, code}`. State verified; code exchanged for tokens. ID token verified server-side.
4. From the ID token + userinfo: extract `{name, verified_email, profile_url, profile_pic}`. Scopes used: `openid profile email`.
5. Auto-match `verified_email` against `alumni.email` and `alumni.personal_email` (case-insensitive, exact). If match → proceed to §7.3 immediately, no OTP needed (LinkedIn already proved email ownership).
6. If no email match → create a `verification_cases` row with the LinkedIn data prefilled and surface in the admin queue. Bot tells the user "Your profile has been queued for review — you'll hear back within 24 hours."

### 7.3 Shared finalization (claim + bind)

1. Open transaction.
2. `SELECT ... FOR UPDATE` on the `alumni` row → defends against concurrent claims.
3. Insert into `members` (alumni_id, telegram_user_id, display_name, status='active'). The partial UNIQUE indexes on `members.alumni_id` and `members.telegram_user_id` (both `WHERE status='active'`) make double-claim atomically impossible — a concurrent attempt gets `IntegrityError` mapped to a "already claimed" user-facing message.
4. Compute canonical display name. Default = `{Name} ({Program} {Batch})`, e.g., `Suresh Iyer (PGP 2015)`. If a legitimate name collision exists (two distinct alumni records with the same `{Name, Program, Batch}`), suffix with `· #B`, `· #C`.
5. Generate one-time invite link via Telegram `createChatInviteLink(member_limit=1, expire_date=now+24h)`. Insert into `invite_links`.
6. DM the link to the user. Write `audit_log` row (`action='member_created'`).
7. Commit.

### 7.4 Re-entry rules

- If a Telegram user with an `active` `members` row tries to start verification again → bot says "You're already verified as X."
- If a member who left the group re-verifies → reactivate the existing row (status `left` → `active`); do not insert a new row.
- If a member with `status='revoked'` re-verifies → bot says "Your binding was revoked. Contact an admin to restore access."

## 8. Data Model

PostgreSQL 16 with `citext` (case-insensitive emails) and `pg_trgm` (fuzzy name search) extensions.

```sql
-- 1. The directory. One row per Excel row. Re-importable.
CREATE TABLE alumni (
    user_id            TEXT PRIMARY KEY,           -- 'gopalv83' from Excel
    name               TEXT NOT NULL,
    email              CITEXT,
    personal_email     CITEXT,
    status             TEXT,                       -- 'Alumni' | 'Student' | NULL
    batch_year         INT,
    program            TEXT,                       -- 'PGDM', 'PGP', 'LDP', ...
    reg_number         TEXT,
    mobile             TEXT,
    home_city          TEXT,
    home_country       TEXT,
    company            TEXT,
    designation        TEXT,
    linkedin_url       TEXT,
    extra              JSONB NOT NULL DEFAULT '{}'::jsonb,
    imported_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX alumni_email_idx          ON alumni (email);
CREATE INDEX alumni_personal_email_idx ON alumni (personal_email);
CREATE INDEX alumni_reg_number_idx     ON alumni (reg_number);
CREATE INDEX alumni_name_trgm_idx      ON alumni USING gin (name gin_trgm_ops);
CREATE INDEX alumni_batch_program_idx  ON alumni (batch_year, program);

-- 2. In-flight verification attempts and their outcomes.
CREATE TABLE verification_cases (
    id                 BIGSERIAL PRIMARY KEY,
    telegram_user_id   BIGINT NOT NULL,
    method             TEXT NOT NULL,              -- 'email_otp' | 'linkedin' | 'manual'
    claimed_alumni_id  TEXT REFERENCES alumni(user_id),
    submitted_name     TEXT,
    submitted_reg      TEXT,
    submitted_batch    INT,
    submitted_program  TEXT,
    linkedin_url       TEXT,
    linkedin_email     CITEXT,
    linkedin_pic_url   TEXT,
    free_text_note     TEXT,
    status             TEXT NOT NULL,              -- 'pending' | 'approved' | 'rejected' | 'auto_approved'
    decided_by         TEXT,                       -- admin email; NULL if auto
    decided_at         TIMESTAMPTZ,
    decision_note      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX vc_status_idx  ON verification_cases (status, created_at);
CREATE INDEX vc_tg_user_idx ON verification_cases (telegram_user_id);

-- 3. Short-lived OTPs (Path A only).
CREATE TABLE otp_codes (
    id                 BIGSERIAL PRIMARY KEY,
    telegram_user_id   BIGINT NOT NULL,
    alumni_id          TEXT NOT NULL REFERENCES alumni(user_id),
    code_hash          TEXT NOT NULL,              -- bcrypt(code + pepper)
    attempts           INT NOT NULL DEFAULT 0,
    expires_at         TIMESTAMPTZ NOT NULL,
    consumed_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX otp_tg_active_idx ON otp_codes (telegram_user_id) WHERE consumed_at IS NULL;

-- 4. Short-lived LinkedIn OAuth state (Path B).
CREATE TABLE linkedin_auth_sessions (
    state              TEXT PRIMARY KEY,
    telegram_user_id   BIGINT NOT NULL,
    expires_at         TIMESTAMPTZ NOT NULL,
    consumed_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Verified, group-bound members. The uniqueness gate.
CREATE TABLE members (
    id                 BIGSERIAL PRIMARY KEY,
    alumni_id          TEXT NOT NULL REFERENCES alumni(user_id),
    telegram_user_id   BIGINT NOT NULL,
    display_name       TEXT NOT NULL,
    status             TEXT NOT NULL,              -- 'active' | 'revoked' | 'left' | 'erased'
    verified_via       TEXT NOT NULL,              -- 'email_otp' | 'linkedin' | 'admin'
    verification_case_id BIGINT REFERENCES verification_cases(id),
    joined_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at         TIMESTAMPTZ,
    revoked_reason     TEXT,
    -- display-name drift tracking (see §10.3)
    drift_incidents       INT NOT NULL DEFAULT 0,
    drift_last_sampled_at TIMESTAMPTZ,
    drift_reminded_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX members_one_active_per_alumni
    ON members (alumni_id) WHERE status = 'active';
CREATE UNIQUE INDEX members_one_active_per_tg
    ON members (telegram_user_id) WHERE status = 'active';

-- 6. Allow-listed admins.
CREATE TABLE admins (
    email              CITEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    role               TEXT NOT NULL,              -- 'admin' | 'super_admin'
    added_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    added_by           CITEXT
);

-- 7. Every admin action. Append-only.
CREATE TABLE audit_log (
    id                 BIGSERIAL PRIMARY KEY,
    actor_email        CITEXT NOT NULL,            -- 'system@bot' for automated actions
    action             TEXT NOT NULL,
    subject_type       TEXT NOT NULL,
    subject_id         TEXT NOT NULL,
    details            JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_actor_idx   ON audit_log (actor_email, created_at DESC);
CREATE INDEX audit_subject_idx ON audit_log (subject_type, subject_id, created_at DESC);

-- 8. Issued invite links so we can track / revoke.
CREATE TABLE invite_links (
    id                 BIGSERIAL PRIMARY KEY,
    telegram_user_id   BIGINT NOT NULL,
    alumni_id          TEXT NOT NULL REFERENCES alumni(user_id),
    invite_link        TEXT NOT NULL,
    expires_at         TIMESTAMPTZ NOT NULL,
    used_at            TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 9. PII view forensics.
CREATE TABLE pii_access_log (
    id                 BIGSERIAL PRIMARY KEY,
    admin_email        CITEXT NOT NULL,
    subject_type       TEXT NOT NULL,
    subject_id         TEXT NOT NULL,
    fields_viewed      TEXT[],
    view_context       TEXT,
    request_ip         INET,
    accessed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX pii_admin_idx   ON pii_access_log (admin_email, accessed_at DESC);
CREATE INDEX pii_subject_idx ON pii_access_log (subject_type, subject_id, accessed_at DESC);
```

**Schema notes:**

- `alumni.extra` (JSONB) holds the long tail of Excel columns (Hostel, Room Number, UG Degree/Institute, Internship firms, Hobbies) so directory re-imports don't break the schema.
- `CITEXT` emails make `Foo@Bar.com` and `foo@bar.com` interchangeable.
- OTPs are bcrypt-hashed with a separate `OTP_PEPPER` env var.
- The two partial UNIQUE indexes on `members` make the one-claim-per-record + one-account-per-person rules database-enforced. No application-layer race possible.
- `audit_log.details JSONB` is flexible — every action stores its own payload shape.

## 9. Admin Dashboard

FastAPI + Jinja2 templates + HTMX. Server-rendered HTML; no SPA, no JSON API.

**Auth:** Google SSO via `authlib`. Session is a signed HTTP-only cookie, 12-hour TTL. Login is gated by membership in the `admins` table.

**Roles:**
- `admin`: approve/reject cases, revoke members, view audit log.
- `super_admin`: everything `admin` can do, plus manage the admin list and trigger directory re-imports.
- There is always at least one `super_admin` (the owner, seeded via the `SEED_SUPER_ADMIN_EMAIL` env var at first deploy).

**Pages:**

| Route | Purpose |
|---|---|
| `/login` | Google OAuth handshake |
| `/` | Counts (pending, today's approvals, weekly trend) |
| `/queue` | Pending verification cases, sortable, paginated |
| `/queue/<case_id>` | Single case detail — full info, approve/reject |
| `/members` | Verified members search/browse |
| `/members/<member_id>` | Member detail + revoke button |
| `/alumni/search` | Search the directory (for resolving manual cases) |
| `/alumni/<user_id>` | Single alumni record (logs to `pii_access_log`) |
| `/audit` | Audit log viewer (filterable by actor, action, date) |
| `/admins` | Manage admin list (super_admin only) |
| `/health` | Liveness probe (no auth) |

**Key behaviors:**

- Every PII view writes to `pii_access_log` with `fields_viewed` and `view_context`.
- Approve / reject require a non-empty note (server-side validated). Written to `audit_log` and the `decision_note` field on the case.
- "Approve & bind" performs the full member-creation transaction; the unique constraints catch any double-claim race.
- "Request more info" sends a templated DM via the bot and returns the case to the queue.
- Name search uses `pg_trgm`; results capped at 50 rows per query, paginated.
- Audit log is read-only via the UI — no edit / delete.

## 10. Group Enforcement

The bot is added to the supergroup as an admin with only these privileges: `can_invite_users`, `can_restrict_members`. Least-privilege.

**Three enforcement loops:**

### 10.1 New-member webhook
On `chat_member` update, the bot checks the `members` table. If the new joiner is not bound (or is bound but `status != 'active'`), the bot kicks them and DMs `Please verify via @IIMCAlumBot first`. The kick uses `ban → unban` so the user can retry. If bound, the bot posts a welcome message with the canonical display name.

### 10.2 Hourly reconciliation
A cron-style job runs hourly to defend against drift:
- For every group member, if not in active `members` → kick + DM to re-verify.
- For every active `members` row whose `telegram_user_id` is no longer in the group → set `status='left'`.

### 10.3 Display-name drift (soft enforcement)
Telegram does **not** allow a bot to force-change a user's display name. So:
- The bot tracks per-member "drift incidents" — every message in the group where `msg.from_user.full_name != members.display_name`. Incidents are stored on a `members.drift_incidents INT NOT NULL DEFAULT 0` column (sampled — increment once per drifting message, but cap at 1 increment per member per hour to avoid spam).
- After **3 cumulative drift incidents** for a member, send a one-time reminder DM and stamp `members.drift_reminded_at = now()`.
- If `drift_reminded_at` is older than 24 hours AND the member is still drifting, kick + set `status='revoked'`, reason `display_name_drift`.
- The user can re-verify, which reactivates the row if it was just `left`, or requires admin intervention if `revoked`.

This is a **policy + nudge + eventual kick** loop, not hard enforcement. The owner has explicitly chosen this over the harder "all enforcement via `/whois` lookups" alternative.

## 11. Security & PII Handling

### 11.1 Repository hygiene
- `Joka_Directory_Final.xlsx` is removed from git. `*.xlsx` is in `.gitignore`. A sanitized 50-row fixture lives at `tests/fixtures/alumni_sample.xlsx`.
- `gitleaks` runs as a pre-commit hook to block secret commits.

### 11.2 Secret management
- All credentials in env vars: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL_BOT`, `DATABASE_URL_ADMIN`, `LINKEDIN_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `BREVO_API_KEY`, `SESSION_SECRET`, `OTP_PEPPER`, `SEED_SUPER_ADMIN_EMAIL`.
- `.env.example` is checked in; real `.env` is `.gitignore`'d. Production uses VM environment variables managed via `/etc/systemd/system/*.service.d/`.

### 11.3 Data minimization at every boundary
- **Bot → user DMs**: never echo directory data. Only masked email at OTP step.
- **Bot → group**: only the bound `display_name` appears in group-visible messages.
- **Admin dashboard**: full PII only on case-detail and member-detail pages. Lists show only Name + Batch + Program + masked email.
- **No public API**: dashboard is server-rendered HTML only.

### 11.4 Database roles
- `bot_app`: read-only on `alumni` for general lookups; UPDATE permitted **only via the `redact_alumni(user_id)` SECURITY DEFINER function** (used by the `/forget_me` erasure path — see §11.9); full DML on `verification_cases`, `otp_codes`, `linkedin_auth_sessions`, `members`, `invite_links`; insert-only on `audit_log` (`system@bot` actor).
- `admin_app`: read on `alumni`; full DML on operational tables; insert-only on `audit_log` and `pii_access_log`. Also permitted to call `redact_alumni()` for admin-initiated erasure.
- `migrator`: DDL on everything, owns the `redact_alumni()` function. Used only by Alembic migrations.
- Neither `bot_app` nor `admin_app` has raw DDL or superuser.

### 11.5 Rate limits

| Limit | Threshold | Behavior at limit |
|---|---|---|
| Verification starts per `telegram_user_id` | 5 / 24h | Bot DMs: "You've hit the limit. Try again in <X> hours, or contact an admin." Case logged. |
| OTPs issued per `alumni_id` | 3 / 24h | Bot DMs: "This email has had too many code requests recently. Try again in <X> hours." |
| OTP code submissions per OTP | 3 / lifetime of OTP | OTP marked `consumed_at`; verification case moved to admin-review queue with reason `otp_attempts_exhausted`. |

Implemented via columns on `otp_codes` and a small `rate_limits` table (no Redis needed at this scale). All limit-hit events write an `audit_log` row with `actor_email='system@bot'`.

### 11.6 OTP security
- 6-digit numeric, generated via `secrets.randbelow(10**6)`.
- Stored as `bcrypt(code + OTP_PEPPER)`.
- TTL 10 min, single-use.
- Delivered via Brevo; never via the operator's personal Gmail.

### 11.7 LinkedIn OAuth security
- Standard OIDC with `state` parameter (32 random bytes, stored in `linkedin_auth_sessions`) for CSRF defense.
- ID token nonce verified server-side.
- `redirect_uri` is the exact registered callback URL.
- Only `openid profile email` scopes requested.
- Email match against directory is exact (case-insensitive), not fuzzy — defends against `iiim@` → `iim@` typos being treated as matches.

### 11.8 Audit & defensibility
- `pii_access_log` row on every admin view of a record.
- `audit_log` row on every approve, reject, revoke, admin-add, directory re-import.
- Both tables are append-only at the app level. DELETE permission is held only by the owner via a separate role used for GDPR-style erasure requests.
- Timestamps in UTC. Logs flushed via Supabase point-in-time recovery (paid upgrade — noted for future).

### 11.9 Erasure (`/forget_me`)
For verified members, the bot command performs in one transaction:
1. Revoke binding (`status='erased'`).
2. Kick from group.
3. Redact the matching `alumni` row (`name='[redacted]'`, all PII columns nulled). `user_id` and `imported_at` preserved so future re-imports don't resurrect the row.
4. Audit-log the action.

For non-members, the same command works from a DM — confirm via OTP, then redact.

### 11.10 Infra security
- Caddy in front of the dashboard for automatic Let's Encrypt TLS.
- Logging filter scrubs anything matching email/phone regexes before writing to application logs.
- Daily Supabase backups; manual PG dump runbook documented for restore.

## 12. Tech Stack & Deployment

**Language & runtime**
- Python 3.12.

**Frameworks**
- `aiogram 3.x` (Telegram bot).
- `FastAPI` (admin dashboard).
- `Jinja2` + `HTMX` (dashboard UI; no SPA).
- `SQLAlchemy 2.x` + `Alembic` (ORM + migrations).
- `asyncpg` (Postgres driver).

**Auth & external services**
- `authlib` for Google OIDC and LinkedIn OIDC.
- `bcrypt` (via `passlib`) for OTP hashing.
- **Brevo** for transactional email (free tier: 300 emails/day).

**Database**
- **PostgreSQL 16 on Supabase free tier**. 500 MB storage cap (we expect well under 100 MB). Daily backups.
- Extensions: `citext`, `pg_trgm`.

**Hosting**
- **Oracle Cloud Always Free** — 1 ARM Ampere VM (Ubuntu 24.04 + Docker). Both services run as Docker containers via `docker compose`. Caddy on the host provides TLS for the dashboard.
- Two services: `iimc-alum-bot` (long-poll to Telegram + listens on a private port for the LinkedIn OAuth callback, proxied by Caddy at `/oauth/linkedin/callback`); `iimc-alum-admin` (FastAPI, served at the dashboard subdomain via Caddy).

**Cost: $0/month** at v1 traffic.

### 12.1 Repo layout

```
IIMC_Alum_Auth/
├── pyproject.toml                  # uv-managed
├── alembic.ini
├── alembic/
│   └── versions/
├── src/
│   ├── shared/
│   │   ├── config.py               # pydantic-settings
│   │   ├── db.py                   # async session factory
│   │   ├── models.py               # SQLAlchemy models (shared)
│   │   ├── audit.py                # audit_log + pii_access_log writers
│   │   ├── verification.py         # state machine + claim transaction
│   │   ├── email.py                # OTP send via Brevo
│   │   └── ratelimit.py
│   ├── bot/
│   │   ├── __main__.py             # aiogram entrypoint
│   │   ├── handlers/
│   │   │   ├── verify_email.py     # Path A FSM
│   │   │   ├── verify_linkedin.py  # Path B initiator
│   │   │   ├── group_events.py     # on_chat_member, on_message
│   │   │   └── erasure.py          # /forget_me
│   │   ├── reconciliation.py       # hourly cron
│   │   └── oauth_callback.py       # FastAPI mini-app for LinkedIn callback
│   └── admin/
│       ├── __main__.py             # uvicorn entrypoint
│       ├── routes/
│       │   ├── queue.py
│       │   ├── members.py
│       │   ├── alumni.py
│       │   ├── audit.py
│       │   └── admins.py
│       ├── auth.py                 # Google SSO + session middleware
│       ├── templates/              # Jinja2
│       └── static/
├── scripts/
│   ├── import_directory.py         # xlsx → alumni table
│   └── seed_admin.py               # seed first super_admin
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── alumni_sample.xlsx      # 50 fake rows
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .env.example
├── .gitignore                      # includes *.xlsx, .env
├── Dockerfile                      # multi-stage, single image
├── docker-compose.yml              # local dev: Postgres + bot + admin
├── deploy/
│   ├── Caddyfile
│   └── systemd/                    # service units for VM
└── README.md
```

**Why one image, two entrypoints:** the bot and dashboard share models, migrations, and the email sender. One Docker image, two `CMD`s (`python -m src.bot` vs `python -m src.admin`), simpler ops.

### 12.2 Local dev

`docker compose up` brings up Postgres, applies migrations, seeds the sample directory, starts both services with `--reload`. Make targets: `make dev`, `make test`, `make migrate`, `make seed`.

## 13. Testing Strategy

**Layer 1 — Unit tests** (`tests/unit/`)
Pure functions only. No DB, no network. <2s total runtime.
- Display-name canonicalization and collision suffixing.
- OTP hashing.
- Masked-email rendering (`s••••@gmail.com`).
- Fuzzy match scoring helpers.
- Audit-log payload builders.

**Layer 2 — Integration tests** (`tests/integration/`)
`testcontainers-python` brings up a real Postgres per test session. Tests wrap in transactions that roll back at teardown. The `tests/fixtures/alumni_sample.xlsx` (50 fake rows) is loaded once per session.

Covered:
- Every transition in the verification FSM (happy paths and every off-ramp).
- Uniqueness: two concurrent transactions claiming the same `alumni_id` — exactly one succeeds, the other gets a clean "already claimed" error.
- OTP lifecycle: send / hash / verify / expire / re-issue invalidates old.
- LinkedIn match: email found in `Email` column / found in `Personal Email` column / no match → admin queue with correct prefill.
- Admin actions: approve / reject / revoke / revoke+rebind all produce correct `members`, `audit_log` rows, and respect the unique constraints.
- `pii_access_log` written on every case-detail render with correct `fields_viewed`.
- `/forget_me` redacts atomically; rolls back cleanly on any failure.
- Rate limits: 6th verification attempt blocked; 4th OTP submission invalidates the code.

**Layer 3 — End-to-end tests** (`tests/e2e/`)
Mock Telegram and LinkedIn at the HTTP boundary via `respx`. Three scenarios:
- Full Email-OTP happy path: `/start` → reg# → OTP → code → display name → invite link → simulated join → welcome message.
- Full LinkedIn happy path: `/start` → "verify with LinkedIn" → OAuth callback → email auto-matches → invite link.
- Admin dashboard: Google login (mocked) → queue → open case → approve → asserts member row + audit row + bot triggered to issue invite.

**Out of scope for tests**
- Telegram delivery (we trust their API).
- Brevo delivery (we assert we called Brevo correctly).
- LinkedIn page rendering (admin's eyeball).
- DB backup/restore (Supabase's responsibility; documented runbook only).

**Tooling**
- `pytest` + `pytest-asyncio` + `pytest-cov` (target ≥85% on `src/shared/`, `src/bot/handlers/`, `src/admin/routes/`).
- `ruff` lint, `mypy --strict` types — both enforced via pre-commit and CI.
- `factory_boy` for test data.
- GitHub Actions: lint + types + unit + integration on every PR; e2e on `main`.

**Production observability**
- Structured JSON logs with correlation IDs per verification case.
- Sentry free tier for exceptions (5k events/month).
- `/health` endpoint on the dashboard returns DB ping + last bot poll timestamp. Uptime Robot pings it free.

## 14. Operational Runbooks (to be written during implementation)

- Directory re-import (replacement of `Joka_Directory_Final.xlsx` with a fresh version).
- Manual member revocation outside the dashboard (e.g., if the dashboard is down).
- Postgres restore from Supabase backup.
- Adding/removing an admin via direct DB access in a break-glass scenario.

## 15. Open Questions / Future Work

- **Official endorsement**: pursue endorsement from the IIM C alumni office post-launch. The design has a clean upgrade path — consent text can be tightened, the data provenance question becomes a one-line answer.
- **Member portal (v2)**: profile management, directory browsing for verified members, batch/city sub-group opt-ins.
- **Topic seeding**: the supergroup's initial Topics list (General, Jobs, Bangalore, Mumbai, Batch-2010s, Batch-2020s, etc.) is an ops decision before launch, not a design question.
- **Mobile-based fallback OTP (v2)**: only worthwhile if directory mobile coverage improves materially.

---

**End of design.**
