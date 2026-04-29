# Phase 05: Configure Neon & Deploy to Vercel — Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 4 (touched/verified, no new files created)
**Analogs found:** 4 / 4 (all files exist; this phase reads/updates them, not creates them)

---

## File Classification

| File | Role | Data Flow | Action | Match Quality |
|------|------|-----------|--------|---------------|
| `src/lib/db.ts` | utility / db-client | request-response | Read-only confirm — zero changes needed | self (canonical source) |
| `.env.example` | config | — | Update: add `?sslmode=require` suffix and ETL var block | self (canonical source) |
| `billboard_stats/db/connection.py` | service / db-client | CRUD | Read-only confirm — already env-var driven | self (canonical source) |
| `package.json` | config | — | No change needed (`@neondatabase/serverless@^1.1.0` already present) | self |

This phase introduces **no new source files**. Every file below is being confirmed or minimally updated.

---

## Pattern Assignments

### `src/lib/db.ts` (utility, request-response)

**Action:** Confirm only — no edits. `DATABASE_URL` is already read from `process.env`.

**Full file** (lines 1-11):
```typescript
import { neon } from "@neondatabase/serverless";

export function getSql() {
  const databaseUrl = process.env.DATABASE_URL;

  if (!databaseUrl) {
    throw new Error("DATABASE_URL is not configured.");
  }

  return neon(databaseUrl);
}
```

**Key facts for planner:**
- `process.env.DATABASE_URL` is the single env var consumed by the entire Next.js app.
- The error message `"DATABASE_URL is not configured."` is the exact string that will appear in Vercel logs if the env var is missing at deploy time — useful for smoke-test diagnosis.
- No pooling config is set here — `@neondatabase/serverless` handles its own connection management. The **pooled** Neon connection string (hostname contains `-pooler`) must be used as `DATABASE_URL` for this driver under Vercel's serverless concurrency.

---

### `.env.example` (config)

**Action:** Update the existing file to reflect the real Neon URL format (with `sslmode=require`) and add ETL vars.

**Current content** (line 1):
```ini
DATABASE_URL=postgresql://user:password@host.neon.tech/neondb
```

**Target content after update:**
```ini
# Next.js app — use the POOLED connection string from Neon console
# (hostname contains -pooler, e.g. ep-<id>-pooler.us-east-1.aws.neon.tech)
DATABASE_URL=postgresql://user:password@ep-<id>-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require

# Python ETL — use UNPOOLED host + individual vars (PGSSLMODE=require is mandatory for Neon)
PGHOST=ep-<id>.us-east-1.aws.neon.tech
PGPORT=5432
PGDATABASE=neondb
PGUSER=<neon-user>
PGPASSWORD=<neon-password>
PGSSLMODE=require
```

**Convention:** `.gitignore` line 34 already covers `.env*` — `.env.example` is committed (no wildcard match because `example` is a suffix not a prefix in git's glob). `.env.local` (written by `vercel env pull`) is already gitignored.

---

### `billboard_stats/db/connection.py` (service, CRUD)

**Action:** Confirm only — no code changes. Connection is already fully env-var driven.

**Full file** (lines 1-92) — key excerpt, env-var reading pattern (lines 11-38):
```python
def _get_setting(key: str, default: str = "") -> str:
    """Read a config value from Streamlit secrets (if available) or env vars."""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def get_pool() -> pool.ThreadedConnectionPool:
    """Return the shared connection pool, creating it on first call."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        conn_kwargs = dict(
            minconn=1,
            maxconn=10,
            host=_get_setting("PGHOST", "localhost"),
            port=int(_get_setting("PGPORT", "5432")),
            dbname=_get_setting("PGDATABASE", "billboard"),
            user=_get_setting("PGUSER", "postgres"),
            password=_get_setting("PGPASSWORD", ""),
        )
        sslmode = _get_setting("PGSSLMODE")
        if sslmode:
            conn_kwargs["sslmode"] = sslmode
        _connection_pool = pool.ThreadedConnectionPool(**conn_kwargs)
    return _connection_pool
```

**Key facts for planner:**
- `PGSSLMODE` is already handled conditionally (lines 35-37) — setting `PGSSLMODE=require` in env is the **only** action needed to enable SSL for Neon.
- Defaults: `PGHOST=localhost`, `PGDATABASE=billboard`, `PGUSER=postgres` — these must be overridden via env vars or a `.env` file when pointing at Neon.
- `_get_setting()` checks Streamlit secrets first, then `os.environ` — no `python-dotenv` is installed. The plan must use `export` commands or a manual `.env` sourcing step (e.g., `set -a && source .env && set +a`) rather than relying on automatic `.env` loading.
- Use the **unpooled** Neon hostname in `PGHOST` (no `-pooler` suffix) — psycopg2's ThreadedConnectionPool manages its own pooling at the application level.

---

### `package.json` (config)

**Action:** No changes needed.

**Relevant lines** (confirmed present):
```json
"dependencies": {
  "@neondatabase/serverless": "^1.1.0",
  "next": "16.2.4"
}
```

**Vercel CLI note:** `npm install -g vercel` and `npm install -g neonctl` are **global** installs — `package.json` is not modified. These tools are one-time developer machine setup steps, not project dependencies.

---

## Shared Patterns

### Env Var Conventions

**Source:** `.gitignore` (line 34) + `.env.example` (line 1)
**Apply to:** All steps that write or reference env files

```
# Pattern: .env* is gitignored globally
.env*

# Pattern: .env.example IS committed (it's a template, not a secret)
# .env.local — written by `vercel env pull`, never committed
# .env       — ETL env file, never committed (matched by .env*)
```

**Implication for plan:** The updated `.env.example` is safe to commit. Any actual secret files (`.env`, `.env.local`) are already protected by the existing gitignore rule.

### DATABASE_URL Split: Pooled vs Unpooled

**Apply to:** Every step that sets or uses a connection string

| Consumer | Connection Type | Hostname Pattern |
|----------|----------------|-----------------|
| `@neondatabase/serverless` (Next.js / Vercel) | **Pooled** | `ep-<id>-pooler.us-east-1.aws.neon.tech` |
| `pg_restore` (data migration) | **Unpooled** | `ep-<id>.us-east-1.aws.neon.tech` |
| `psql` (verification queries) | **Unpooled** | `ep-<id>.us-east-1.aws.neon.tech` |
| `psycopg2` ETL (`PGHOST`) | **Unpooled** | `ep-<id>.us-east-1.aws.neon.tech` |

This split is the single most important gotcha in this phase (RESEARCH.md Pitfall 5).

### Vercel Env Var Scoping

**Source:** RESEARCH.md §4 (Vercel Environment Variables)
**Apply to:** All `vercel env add` steps

```bash
# Three separate commands — cannot combine development with production/preview
vercel env add DATABASE_URL production
vercel env add DATABASE_URL preview
vercel env add DATABASE_URL development
```

Use `vercel env ls` to verify all three are set before deploying.

### pg Tools PATH

**Source:** RESEARCH.md §1 / Pitfall 2
**Apply to:** All pg_dump, pg_restore, psql steps

```bash
# Must be set for the session — pg tools are keg-only (not on default $PATH)
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
```

---

## No Analog Found

None. All files touched in this phase already exist in the codebase and were read directly. No file requires a pattern from an external analog.

---

## Metadata

**Analog search scope:** Project root, `src/lib/`, `billboard_stats/db/`
**Files scanned:** 6 (`db.ts`, `connection.py`, `.env.example`, `next.config.ts`, `package.json`, `.gitignore`)
**Pattern extraction date:** 2026-04-29
