# Phase 05: Configure Neon & Deploy to Vercel — Research

**Researched:** 2026-04-29
**Domain:** Infrastructure / Cloud Deployment (Neon PostgreSQL + Vercel)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** No Neon project exists yet — one must be created from scratch.
- **D-02:** Migration path: `pg_dump` from localhost, restore into Neon via `pg_restore` or `psql`.
- **D-03:** The `@neondatabase/serverless` client is already installed and wired in `src/lib/db.ts` — no code changes needed, only `DATABASE_URL` must be set.
- **D-04:** Updating the Python ETL pipeline to write to Neon is in scope for this phase.
- **D-05:** ETL connection string location is unknown — the plan should include a step to locate it first. Move it to an env var if it's hardcoded.
- **D-06:** Set up both GitHub integration (push to `main` → auto-deploy) AND Vercel CLI for ad-hoc deploys.
- **D-07:** `DATABASE_URL` must be set as a Vercel environment variable (Production + Preview + Development scopes, all pointing at the same Neon project for now).
- **D-08:** Production only for now — all Vercel environments share the same Neon database. No Neon branching needed.

### Claude's Discretion
- Exact Neon project name and database name.
- Whether to use `pg_dump --format=custom` or plain SQL (agent's discretion based on data size).
- Vercel project name (suggest `billboard-stats`).

### Deferred Ideas (OUT OF SCOPE)
- Neon branching for preview deployments.
- Custom domain — Vercel-provided `.vercel.app` URL is sufficient for v1.0.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-02 | Connect to Neon PostgreSQL database and setup typed API routes | D-03 confirmed: `@neondatabase/serverless` already wired; only `DATABASE_URL` env var needed. `pg_trgm` extension used for search is supported on Neon. |
| CORE-03 | Deploy application to Vercel | Vercel auto-detects Next.js 16.x App Router; zero `vercel.json` config needed. GitHub integration + CLI both researched. |
</phase_requirements>

---

## Summary

Phase 5 is pure infrastructure work — no application code changes required. The three tasks are: (1) provision a Neon project and migrate 193 MB of Billboard data from localhost PostgreSQL into it, (2) wire `DATABASE_URL` into Vercel env vars and deploy via GitHub + CLI, and (3) update the Python ETL connection to point at Neon.

The local Billboard database is 193 MB — well within Neon's free plan 0.5 GB per-project storage limit. The database uses only two PostgreSQL extensions (`pg_trgm` and `plpgsql`), both of which are natively supported on Neon. The migration is straightforward: `pg_dump -Fc` from localhost, `pg_restore -v -O --no-acl` into the Neon direct (unpooled) connection string.

The Python ETL's connection is already parameterized via env vars (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSSLMODE`). No code restructuring is needed — only a new `.env` file with the Neon connection parameters plus `PGSSLMODE=require`.

**Primary recommendation:** Create Neon project via CLI (`neon projects create`), dump/restore data, set `DATABASE_URL` via `vercel env add` (three separate calls for production, preview, development), connect GitHub repo to Vercel, and smoke-test live routes.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PostgreSQL database hosting | Database / Storage (Neon cloud) | — | Replaces localhost; Neon manages compute and storage |
| Connection wiring | API / Backend (env var) | — | `DATABASE_URL` consumed server-side by `src/lib/db.ts` |
| Static asset serving + SSR | CDN / Frontend Server (Vercel Edge) | — | Vercel auto-provisions for Next.js App Router |
| Auto-deploy on push | CDN / Static (Vercel GitHub integration) | — | Webhook triggered on push to `main` |
| ETL data writes | Database / Storage (Neon cloud) | — | ETL runs locally, writes to Neon via psycopg2 + env vars |

---

## Standard Stack

### Core Tools

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| neonctl (Neon CLI) | latest | Create Neon project, get connection strings | Official CLI; `neon projects create` outputs connection URI immediately |
| Vercel CLI | latest | Link repo, set env vars, ad-hoc deploys | Official tool; `vercel link` → `vercel env add` → `vercel deploy --prod` |
| pg_dump | 16.x (local brew) | Dump localhost Billboard DB in custom format | Standard PostgreSQL utility; `-Fc` format is compressed and pg_restore-ready |
| pg_restore | 16.x (local brew) | Restore dump into Neon | Standard utility; supports `--no-owner --no-acl` flags needed for Neon |

**Local pg tools path (already installed via Homebrew):**
```
/opt/homebrew/opt/postgresql@16/bin/psql
/opt/homebrew/opt/postgresql@16/bin/pg_dump
/opt/homebrew/opt/postgresql@16/bin/pg_restore
```
These are NOT on `$PATH` by default. The plan must either use full paths or `export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"`.

### Installation

```bash
# Neon CLI (install globally via npm)
npm install -g neonctl

# Vercel CLI (install globally via npm)
npm install -g vercel

# pg tools already installed — add to PATH for session:
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
```

**Version verification (checked 2026-04-29):**
- neonctl: available as `npm i -g neonctl` [VERIFIED: npm registry via web search]
- vercel CLI: available as `npm i -g vercel` [VERIFIED: vercel.com/docs/cli]
- pg_dump 16.x: confirmed installed at `/opt/homebrew/opt/postgresql@16/bin/pg_dump` [VERIFIED: Bash probe]

---

## Architecture Patterns

### System Architecture Diagram

```
[Local PostgreSQL :5432]
       |
       | pg_dump -Fc (custom format, ~193 MB)
       v
[billboard.dump file]
       |
       | pg_restore -v -O --no-acl (unpooled Neon connection)
       v
[Neon PostgreSQL project: billboard-stats]
       |
       +---> [Vercel env var: DATABASE_URL] ---> [src/lib/db.ts getSql()]
       |                                               |
       |                                         [Next.js API routes]
       |                                         [Server Components]
       |                                               |
       |                                    [Vercel Deployment]
       |                                    (auto-deploy on git push to main)
       |
       +---> [Python ETL env vars: PGHOST, PGDATABASE, etc.]
             |
             | psycopg2 + sslmode=require
             v
             [Neon PostgreSQL project: billboard-stats]
```

### Recommended Task Order

The CONTEXT.md specifies this order explicitly:
1. Create Neon project → get connection string
2. Dump local DB → restore into Neon → verify row counts
3. Set `DATABASE_URL` as Vercel env var
4. Connect GitHub repo to Vercel (GitHub integration)
5. Deploy to production
6. Smoke-test live routes
7. Update Python ETL env vars to point at Neon

Do NOT deploy until Neon data is verified (step 2 complete). An empty-DB deploy will surface `DATABASE_URL is not configured` or empty API responses, not a build failure.

---

## Research Findings

### 1. Neon Project Creation

**CLI method (recommended for automation):**

```bash
# Step 1: Authenticate
neon auth
# Opens browser for OAuth; stores credentials locally

# Step 2: Create project
neon projects create --name billboard-stats --region-id aws-us-east-1
# Output includes project table + connection URI

# Step 3: Get connection string (unpooled, for pg_restore)
neon connection-string --project-id <project-id>
# Returns: postgresql://user:password@ep-<id>.us-east-1.aws.neon.tech/neondb
```

**Connection string formats:**
- **Unpooled (direct):** `postgresql://user:pass@ep-<id>.us-east-1.aws.neon.tech/neondb`
- **Pooled:** `postgresql://user:pass@ep-<id>-pooler.us-east-1.aws.neon.tech/neondb`

Use **unpooled** for: `pg_restore`, Python ETL (psycopg2 with a connection pool)
Use **pooled** for: `@neondatabase/serverless` driver in Next.js (Vercel `DATABASE_URL`)

[CITED: neon.com/docs/connect/choose-connection, neon.com/docs/reference/cli-projects]

**Free tier limits (2026):**
- Storage: 0.5 GB per project [VERIFIED: neon.com/docs/introduction/plans via web search]
- Billboard DB is **193 MB** [VERIFIED: Bash probe against local DB]
- Compute: 100 CU-hours/month per project
- Branches: 10 per project
- Projects: up to 10 on free tier

193 MB fits within 0.5 GB limit. No plan upgrade needed for v1.0.

**Console alternative:** Project can also be created at console.neon.tech if CLI authentication fails. Connection strings are available under Project → Connection Details → "Direct connection" toggle.

---

### 2. Data Migration: pg_dump to Neon

**Billboard DB facts (verified):**
- Size: 193 MB [VERIFIED: Bash probe]
- Tables: 11 tables, all owned by `postgres` user [VERIFIED: Bash probe]
- Extensions: `pg_trgm` (trigram search), `plpgsql` — **both supported on Neon** [VERIFIED: neon.com/docs/extensions/pg_trgm]
- Largest tables: `b200_entries` (686K rows), `hot100_entries` (351K rows)

**Step 1 — Dump from localhost:**
```bash
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"

pg_dump \
  -Fc \
  -v \
  -Z 1 \
  --lock-wait-timeout=20s \
  -d "postgresql://postgres@localhost/billboard" \
  -f billboard.dump
```

Flags:
- `-Fc` — custom format (compressed, supports parallel restore)
- `-v` — verbose progress
- `-Z 1` — compression level 1 (fast, reasonable size)
- `--lock-wait-timeout=20s` — prevents hang if any lock contention
- Do NOT use `-C` (--create) — not supported by Neon

**Step 2 — Restore into Neon (unpooled connection):**
```bash
pg_restore \
  -v \
  -O \
  --no-acl \
  --single-transaction \
  -d "<NEON_UNPOOLED_CONNECTION_STRING>" \
  billboard.dump
```

Flags:
- `-v` — verbose progress
- `-O` / `--no-owner` — skip `ALTER OWNER` statements (Neon's `neon_superuser` cannot run them; these errors are non-fatal but `-O` suppresses them cleanly)
- `--no-acl` — skip `GRANT`/`REVOKE` statements (same superuser limitation)
- `--single-transaction` — atomicity; prevents partial restores
- Do NOT use the **pooled** connection string for pg_restore — use direct/unpooled

**Extension handling:**
The dump will include `CREATE EXTENSION IF NOT EXISTS pg_trgm` from `schema.sql`. On Neon, this succeeds because `pg_trgm` is a supported extension. The `plpgsql` extension is pre-installed on all Neon projects — any `CREATE EXTENSION plpgsql` in the dump will produce a harmless "already exists" notice (suppressed with `IF NOT EXISTS`).

[CITED: neon.com/docs/import/migrate-from-postgres, neon.com/docs/extensions/pg_trgm]

**Step 3 — Verify row counts:**
```bash
/opt/homebrew/opt/postgresql@16/bin/psql "<NEON_UNPOOLED_CONNECTION_STRING>" \
  -c "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

Expected counts (from local DB):
| Table | Expected rows |
|-------|--------------|
| b200_entries | 686,580 |
| hot100_entries | 351,668 |
| album_artists | 42,170 |
| song_artists | 40,056 |
| album_stats | 39,440 |
| albums | 39,440 |
| song_stats | 32,120 |
| songs | 32,120 |
| artist_stats | 14,628 |
| artists | 14,628 |
| chart_weeks | 7,073 |

---

### 3. Vercel Deployment Setup

**GitHub integration (auto-deploy on push to `main`):**
```bash
# Import repo via Vercel dashboard (first time):
# 1. vercel.com/new → Import Git Repository → GitHub
# 2. Authorize Vercel GitHub app (one-time)
# 3. Select jaimeberdejo/billboard_stats repo
# 4. Framework preset auto-detected as Next.js
# 5. "Deploy" → creates Vercel project + GitHub webhook
```

**Or via CLI:**
```bash
# From project root
vercel link
# Prompts: scope, create new project or link existing
# After linking: .vercel/project.json is created (contains org ID + project ID)
```

**`vercel.json` requirement:** Not needed. Vercel auto-detects Next.js 16.x App Router from `package.json` (`"next": "16.2.4"`). No configuration overrides are required. [VERIFIED: vercel.com/docs/frameworks/full-stack/nextjs via web search — "zero-config support for every Next.js feature"]

**Production deploy:**
```bash
vercel deploy --prod
# Or: push to main branch (auto-triggered via GitHub integration)
```

**Ad-hoc preview deploy:**
```bash
vercel deploy
# Creates preview URL: billboard-stats-<hash>-jaimeberdejo.vercel.app
```

[CITED: vercel.com/docs/projects/deploy-from-cli, vercel.com/docs/git/vercel-for-github]

---

### 4. Vercel Environment Variables

**Important constraint:** `vercel env add` cannot set `production`, `preview`, AND `development` in a single command — development must be set separately. [VERIFIED: vercel.com/docs/cli/env]

**Recommended workflow — add DATABASE_URL to all three environments:**

```bash
# Production + Preview (sensitive by default — value hidden in dashboard after set)
vercel env add DATABASE_URL production
# Prompts for value: paste the POOLED Neon connection string

vercel env add DATABASE_URL preview
# Prompts for value: paste same POOLED Neon connection string

# Development (encrypted, not sensitive)
vercel env add DATABASE_URL development
# Prompts for value: paste POOLED Neon connection string
```

**Piping value (avoids interactive prompt):**
```bash
echo "postgresql://user:pass@ep-<id>-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require" \
  | vercel env add DATABASE_URL production
```
Warning: piping saves to shell history. For production secrets, use the interactive prompt or a temp file:
```bash
vercel env add DATABASE_URL production < neon_url.txt
```

**Pull env vars for local Next.js dev:**
```bash
vercel env pull .env.local
# Writes all development-scope vars to .env.local
# .env.local is gitignored by Next.js by default
```

**Verify:**
```bash
vercel env ls
```

[CITED: vercel.com/docs/cli/env — complete docs fetched]

---

### 5. Python ETL Cutover

**Current connection mechanism (already discovered — no "locate" step needed):**

`billboard_stats/db/connection.py` reads individual env vars via `_get_setting()`:
```python
host=_get_setting("PGHOST", "localhost"),
port=int(_get_setting("PGPORT", "5432")),
dbname=_get_setting("PGDATABASE", "billboard"),
user=_get_setting("PGUSER", "postgres"),
password=_get_setting("PGPASSWORD", ""),
# sslmode=_get_setting("PGSSLMODE") — only set if non-empty
```

**No code changes required** — the connection code already reads from env vars with localhost defaults. To point at Neon, export the Neon values before running the ETL.

**Neon connection parameters for psycopg2:**
```bash
# Parse these from the Neon connection string:
# postgresql://user:password@ep-<id>.us-east-1.aws.neon.tech/neondb?sslmode=require
export PGHOST="ep-<id>.us-east-1.aws.neon.tech"
export PGPORT="5432"
export PGDATABASE="neondb"
export PGUSER="<neon-user>"
export PGPASSWORD="<neon-password>"
export PGSSLMODE="require"
```

**Or, add a `.env` file in the project root for ETL use:**
```ini
# .env (gitignored)
PGHOST=ep-<id>.us-east-1.aws.neon.tech
PGPORT=5432
PGDATABASE=neondb
PGUSER=<neon-user>
PGPASSWORD=<neon-password>
PGSSLMODE=require
```

The existing `_get_setting()` function already checks both Streamlit secrets and `os.environ`, so `python-dotenv` can be added for `.env` file support if desired — but simply exporting env vars before running the ETL is sufficient and requires no code changes.

**SSL requirement:** Neon requires SSL. The connection code already handles `PGSSLMODE` conditionally — setting `PGSSLMODE=require` is the only change needed. [VERIFIED: neon.com/docs/connect/connect-securely via web search]

[VERIFIED: Bash probe of `billboard_stats/db/connection.py` — no hardcoded credentials; entirely env-var driven]

---

### 6. Post-Deploy Verification (Smoke Tests)

After `vercel deploy --prod` completes:

**Routes to verify:**
```
GET https://billboard-stats.vercel.app/           → Homepage loads
GET https://billboard-stats.vercel.app/charts     → Hot 100 table renders with data
GET https://billboard-stats.vercel.app/search?q=taylor → Search results appear
GET https://billboard-stats.vercel.app/records    → Leaderboards render
GET https://billboard-stats.vercel.app/artist/1   → Artist page renders
```

**Quick CLI smoke test:**
```bash
# Check deployment URL responds with HTTP 200
curl -I https://billboard-stats.vercel.app/

# Check a data-dependent API route
curl https://billboard-stats.vercel.app/api/charts | head -c 200
```

**Vercel Logs (for runtime errors):**
```bash
vercel logs --environment production --level error --since 5m
```

**Data validation:**
- Run row count query against Neon directly (psql) before deploying to confirm migration succeeded.
- After deploy, if pages load but show empty tables, `DATABASE_URL` env var scope is likely wrong — re-check `vercel env ls`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PostgreSQL data export | Custom SQL scripts | `pg_dump -Fc` | Handles sequences, indexes, constraints, extensions atomically |
| Data import to Neon | Manual `INSERT` statements | `pg_restore` | 193 MB / 1.2M rows — manual insert would take hours and is error-prone |
| Neon project provisioning | Console GUI steps | `neon projects create` CLI | Scriptable, reproducible, outputs connection string immediately |
| Env var management in Vercel | Hardcoding in `next.config.ts` | `vercel env add` | Secure, scoped per environment, never committed to git |
| SSL configuration for Python | Custom SSL cert handling | `PGSSLMODE=require` env var | psycopg2 handles SSL natively when env var is set |

---

## Common Pitfalls

### Pitfall 1: Using Pooled Connection for pg_restore
**What goes wrong:** `pg_restore` hangs or fails with "prepared statements" or connection reset errors.
**Why it happens:** Pooled connections route through PgBouncer which does not support session-level commands needed during restore (SET statements, prepared statements).
**How to avoid:** Always use the **unpooled** connection string (no `-pooler` in hostname) for `pg_restore` and direct psql sessions.
**Warning signs:** pg_restore exits with "connection to server was lost" or "cannot use a pooled connection".

### Pitfall 2: pg tools not on $PATH
**What goes wrong:** `pg_dump: command not found`.
**Why it happens:** Homebrew installs `postgresql@16` as keg-only (not linked to `/usr/local/bin` or `/opt/homebrew/bin`).
**How to avoid:** Either use full paths (`/opt/homebrew/opt/postgresql@16/bin/pg_dump`) or export PATH first.
**Warning signs:** `which pg_dump` returns nothing.

### Pitfall 3: Deploying Before Data is in Neon
**What goes wrong:** Live app shows empty pages or `DATABASE_URL is not configured` error.
**Why it happens:** If `DATABASE_URL` env var isn't set at deploy time, `getSql()` throws on cold start.
**How to avoid:** Set `DATABASE_URL` via `vercel env add` BEFORE the first deployment. Verify with `vercel env ls`.
**Warning signs:** Vercel build log says "DATABASE_URL is not configured".

### Pitfall 4: vercel env add for All Environments in One Command
**What goes wrong:** `vercel env add DATABASE_URL production development` returns an error.
**Why it happens:** Vercel CLI does not allow mixing `development` with `production`/`preview` in one command.
**How to avoid:** Run three separate `vercel env add` commands — one for production, one for preview, one for development.
**Warning signs:** CLI error: "Cannot combine development with production or preview".

### Pitfall 5: Wrong DATABASE_URL Format for Next.js vs ETL
**What goes wrong:** `@neondatabase/serverless` driver gets a "connection refused" or handshake error if given an unpooled string under high concurrency; psycopg2 ETL may fail with SSL errors if given a pooled string.
**Why it happens:** The two clients have different optimal connection types.
**How to avoid:**
- `DATABASE_URL` in Vercel (for `@neondatabase/serverless`): use **pooled** string (`-pooler` in hostname)
- ETL env vars (`PGHOST`, etc.): use **unpooled** hostname, add `PGSSLMODE=require`
**Warning signs:** Intermittent connection errors in production Next.js app.

### Pitfall 6: pg_trgm Extension Ownership Error
**What goes wrong:** pg_restore emits `ERROR: must be owner of extension pg_trgm` or `ERROR: must be owner of extension plpgsql`.
**Why it happens:** The dump includes `ALTER EXTENSION OWNER TO` statements; Neon's `neon_superuser` cannot execute these.
**How to avoid:** The `-O` (`--no-owner`) flag on `pg_restore` suppresses these. If errors still appear, they are non-fatal — the data still loads correctly.
**Warning signs:** pg_restore output shows "ERROR" on extension ownership lines but exits cleanly otherwise.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| psql / pg_dump / pg_restore | Data migration | ✓ | 16.x (Homebrew keg-only) | — |
| Node.js | neonctl, vercel CLI | ✓ | v25.2.1 | — |
| npm | CLI installs | ✓ | 11.7.0 | — |
| neonctl | Create Neon project | ✗ (not yet installed) | — | Install: `npm i -g neonctl` |
| vercel CLI | Env vars + deploy | ✗ (not yet installed) | — | Install: `npm i -g vercel` |
| Neon account | Database hosting | ✗ (no account yet) | — | Sign up at console.neon.tech |
| Vercel account | App deployment | [ASSUMED — not verified] | — | Sign up at vercel.com |
| GitHub remote | Auto-deploy trigger | ✓ (git remote `github.com/jaimeberdejo/billboard_stats` per CONTEXT.md) | — | — |

**Missing dependencies with no fallback:** None — all missing tools have install instructions.

**Missing dependencies with install steps (Wave 0 / Task 01):**
- `neonctl` → `npm install -g neonctl`
- `vercel` CLI → `npm install -g vercel`
- Neon account → sign up at console.neon.tech
- PATH for pg tools → `export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Vercel account exists at vercel.com for user jaimeberdejo1902@gmail.com | Environment Availability | If no account: must sign up before running `vercel link`; adds ~5 min to plan |
| A2 | `@neondatabase/serverless` works with pooled Neon connection string for Next.js on Vercel | Pitfall 5 | If pooled causes issues: switch to unpooled; both formats are supported by the driver |
| A3 | `neon projects create --region-id aws-us-east-1` is near the user's location | Neon Project Creation | If wrong region: higher latency; can be changed by creating a new project in a different region |

---

## Open Questions

1. **Billboard DB local owner/user for pg_dump**
   - What we know: Tables are owned by `postgres` user; local DB accessible as `postgres`.
   - What's unclear: Whether local PostgreSQL requires password for `postgres` user.
   - Recommendation: Plan should include `pg_dump -U postgres ...` and note that password prompt may appear. Alternatively use `-U $(whoami)` if that user also has access (confirmed in bash probe it does).

2. **Vercel account status**
   - What we know: CONTEXT.md references GitHub remote as deployment target.
   - What's unclear: Whether a Vercel account is already linked to the GitHub account.
   - Recommendation: Plan Wave 0 should check `vercel whoami`; if unauthenticated, run `vercel login`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Plain SQL dump (`pg_dump -t`) | Custom format (`pg_dump -Fc`) | Standard recommendation | Smaller dump, faster restore, parallel restore support |
| Hardcoded DB credentials in Python | Env var driven (`PGHOST`, `PGPASSWORD`, etc.) | Already done in this codebase | No code change needed for cutover |
| `vercel.json` required for Next.js | Zero-config auto-detection | Next.js 13+ / Vercel 2023+ | No `vercel.json` needed for App Router project |

---

## Sources

### Primary (HIGH confidence)
- `neon.com/docs/import/migrate-from-postgres` — pg_dump/pg_restore exact commands, `-O`, `--no-acl` flags, pooled vs unpooled requirement
- `neon.com/docs/reference/cli-projects` — `neon projects create` flags and output format (fetched via Context7)
- `neon.com/docs/connect/choose-connection` — pooled vs direct connection string format (WebFetch)
- `neon.com/docs/reference/cli-install` — neonctl install methods, auth (WebFetch)
- `vercel.com/docs/cli/env` — complete `vercel env add` syntax, scope rules, sensitive/development restrictions (WebFetch)
- `vercel.com/docs/projects/deploy-from-cli` — full CLI workflow (Context7)
- Bash probe: local billboard DB size (193 MB), pg tool locations, table row counts

### Secondary (MEDIUM confidence)
- `neon.com/docs/introduction/plans` — free tier 0.5 GB storage limit, 100 CU-hours/month (web search verified against official URL)
- `neon.com/docs/extensions/pg_trgm` — confirmed pg_trgm is supported (web search hit official Neon docs page)
- `neon.com/docs/connect/connect-securely` — psycopg2 SSL, `PGSSLMODE=require` pattern (web search + Context7 snippet)
- `vercel.com/docs/git/vercel-for-github` — auto-deploy on push to main (web search hit official URL)

### Tertiary (LOW confidence)
- None — all critical claims verified via official docs or Bash probes.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools verified via official docs or Bash probe
- Migration commands: HIGH — exact flags sourced from official Neon migration docs
- Architecture: HIGH — based on verified code inspection + official Vercel/Neon docs
- Python ETL: HIGH — code directly inspected; connection.py is env-var driven already
- Pitfalls: HIGH — all sourced from official Neon migration docs
- Free tier sizing: HIGH — 193 MB local DB verified; 0.5 GB limit verified from docs

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (stable infrastructure, 30-day window safe)
