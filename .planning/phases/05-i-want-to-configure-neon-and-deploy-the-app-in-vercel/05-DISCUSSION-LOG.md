# Phase 05: Configure Neon & Deploy to Vercel - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-29
**Phase:** 05-i-want-to-configure-neon-and-deploy-the-app-in-vercel
**Areas discussed:** Neon database status, ETL cutover scope, Vercel deployment approach, Preview environments

---

## Neon Database Status

| Option | Description | Selected |
|--------|-------------|----------|
| No Neon project yet | Need to create a new Neon project, schema setup, and migrate data | ✓ |
| Neon project exists, no data | Project created, but schema/data not migrated | |
| Neon project exists, data migrated | Fully ready, just need to wire DATABASE_URL | |

**User's choice:** No Neon project yet — start from scratch.

| Option | Description | Selected |
|--------|-------------|----------|
| Local PostgreSQL (localhost) | Running locally — will need pg_dump + restore | ✓ |
| Remote PostgreSQL (another host) | Already on cloud — can dump/restore directly | |
| I have a dump file ready | .sql or .dump file ready to restore | |

**User's choice:** Data lives on localhost — will need pg_dump then restore into Neon.

---

## ETL Cutover Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, include it | Update ETL connection string to Neon as part of Phase 5 | ✓ |
| No, defer it | Skip ETL for now, only wire the web app | |

**User's choice:** Include ETL cutover in this phase.

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded in the script | Connection string is in Python code | |
| .env file / environment variable | Already reads from env var | |
| Not sure | Will need to check the ETL code | ✓ |

**User's choice:** Unknown — plan should include a step to locate and update the ETL connection string.

---

## Vercel Deployment Approach

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub integration | Auto-deploy on push to main | |
| Vercel CLI (manual) | `vercel --prod` for each deploy | |
| Both | GitHub integration + CLI configured | ✓ |

**User's choice:** Both — GitHub integration for CI/CD plus Vercel CLI for ad-hoc deploys.

---

## Preview Environments

| Option | Description | Selected |
|--------|-------------|----------|
| Production only for now | All environments share same Neon database | ✓ |
| Neon branching for previews | Each preview gets isolated Neon branch | |

**User's choice:** Production only — share one Neon database across all Vercel environments for now.

---

## Claude's Discretion

- Neon project name, database name
- Migration dump format (custom vs plain SQL)
- Vercel project name

## Deferred Ideas

- Neon branching for preview environments
- Custom domain setup
