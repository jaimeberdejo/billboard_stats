# Deferred Items — Quick Task 260508-mbw

## Pre-existing TypeScript errors (out of scope)

`npx tsc --noEmit` reports four errors in unrelated Next.js page files. These existed at HEAD (`6ca6a559`, before any edits in this task) — confirmed by stashing the records.ts change and re-running tsc:

```
src/app/album/[id]/page.tsx(58,54): error TS2304: Cannot find name 'PageProps'.
src/app/artist/[id]/page.tsx(100,55): error TS2304: Cannot find name 'PageProps'.
src/app/page.tsx(38,43): error TS2304: Cannot find name 'PageProps'.
src/app/song/[id]/page.tsx(58,53): error TS2304: Cannot find name 'PageProps'.
```

`PageProps` is a Next.js-managed global type. The fix likely involves regenerating `.next/types/` or replacing `PageProps` with explicit prop types. Out of scope for this artist-placeholder bug fix.
