# Plan 05-02 Summary

## Outcome

Completed the Vercel deployment setup for the Next.js app:

- Linked the repository to the Vercel project `billboard-stats`
- Connected the GitHub repository `jaimeberdejo/billboard_stats`
- Added `DATABASE_URL` in production, preview, and development scopes
- Deployed the app to production successfully
- Confirmed local development can pull Vercel env vars and run against Neon

## Deployment

- Vercel project: `billboard-stats`
- Production URL: `https://billboard-stats.vercel.app`
- Inspect URL: `https://vercel.com/jaimeberdejos-projects/billboard-stats/CTDNUMdF3Ar94gh3vcYH6jwBv57o`

## Verification

- `vercel link` — PASS
- `vercel env add DATABASE_URL production` — PASS
- `vercel env add DATABASE_URL preview` — PASS
- `vercel env add DATABASE_URL development` — PASS
- `vercel deploy --prod --archive=tgz` — PASS
- `vercel env pull .env.local` — PASS
- Local `npm run dev` + `GET /api/charts?chart=hot-100` against pulled env vars — PASS

## Notes

- Plain `vercel deploy --prod` hit the free-plan upload cap (`api-upload-free`), so deployment was retried successfully with `--archive=tgz`.
- The live charts experience is served at `/`; there is no standalone `/charts` route in this app.

## Deviations from Plan

The plan expected `/charts` to exist as a page route. In the implemented app, the charts UI is the home page (`/`), while the charts data API lives at `/api/charts`.
