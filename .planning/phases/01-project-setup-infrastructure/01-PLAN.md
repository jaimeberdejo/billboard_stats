---
wave: 1
depends_on: []
files_modified:
  - package.json
  - postcss.config.mjs
  - tailwind.config.ts
  - src/app/layout.tsx
  - src/app/globals.css
  - src/app/page.tsx
  - src/lib/db.ts
  - .env.example
autonomous: true
---

# Phase 1: Project Setup & Infrastructure

Goal: Initialize Next.js project with Tailwind, Neon database connection, and Vercel deployment.

## Requirements Covered
- CORE-01: Setup Next.js App Router project with TypeScript and Tailwind
- CORE-02: Connect to Neon PostgreSQL database and setup typed API routes replacing Python services
- CORE-03: Deploy application to Vercel
- CORE-05: Implement tabular-nums font-variant and dense data-first design (Space Grotesk)

## Task 1: Initialize Next.js & Tailwind
```xml
<task>
<read_first>
- .planning/ROADMAP.md
</read_first>
<action>
Initialize a Next.js App Router project:
1. Since we are in an existing folder, create a new Next.js app in a temp folder using `npx -y create-next-app@latest temp-app --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm`, then move the files to the root, avoiding `.planning/` directory deletion.
2. Add `Space Grotesk` from `next/font/google` in `src/app/layout.tsx`.
3. Define the Billboard red (`#C8102E`) as `billboard` in `tailwind.config.ts`.
4. Apply the dense typographic defaults in `globals.css`, keeping `font-variant-numeric: tabular-nums;` globally set for data tables.
</action>
<acceptance_criteria>
- `package.json` contains `next`, `react`, `react-dom`, `tailwindcss`
- `src/app/layout.tsx` imports from `next/font/google` and configures Space Grotesk
- `src/app/globals.css` contains tabular-nums applied appropriately
</acceptance_criteria>
</task>
```

## Task 2: Neon DB Connection & API Basics
```xml
<task>
<read_first>
- package.json
</read_first>
<action>
1. Install neon serverless driver: `npm install @neondatabase/serverless`
2. Create `src/lib/db.ts` which exports a configured `neon` client utilizing the `DATABASE_URL` environment variable.
3. Create `.env.example` containing `DATABASE_URL=postgresql://user:pass@host/dbname`.
4. Create a basic API route at `src/app/api/health/route.ts` which runs a simple query (e.g., `SELECT version();` or `SELECT 1;`) via the Neon client to verify connection health.
</action>
<acceptance_criteria>
- `@neondatabase/serverless` is inside package.json
- `src/lib/db.ts` exists and initializes a db client
- `src/app/api/health/route.ts` exists and handles a GET request that invokes a query
- `.env.example` contains the `DATABASE_URL` key
</acceptance_criteria>
</task>
```

## Task 3: Vercel Deployment Preparations
```xml
<task>
<read_first>
- package.json
</read_first>
<action>
Ensure Next.js standard build and lint commands exist. Vercel deployment operates zero-config on standard scripts; verify `build` is intact. 
</action>
<acceptance_criteria>
- `package.json` scripts contain `"build": "next build"`
</acceptance_criteria>
</task>
```

## Verification
- `npm run build` must run and exit code 0.
- `npm run dev` followed by a request to `/api/health` should be tested manually once the developer assigns an active `DATABASE_URL` in `.env.local`.

## Must Haves
- Safe scaffolding (does not overwrite existing non-frontend codebase).
- Database interface initialized using serverless driver setup.
