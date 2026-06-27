import { type NextRequest } from "next/server";

import { getEntityComparison, type EntityKind } from "@/lib/analytics";

const CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=86400";

const ENTITY_KIND_ALLOWLIST = new Set<EntityKind>(["artist", "song", "album"]);

function parsePositiveInteger(
  value: string | null,
  minimum = 1,
  maximum = Number.MAX_SAFE_INTEGER,
): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    return null;
  }
  return parsed;
}

function isValidEntityKind(value: string | null): value is EntityKind {
  return value !== null && ENTITY_KIND_ALLOWLIST.has(value as EntityKind);
}

/**
 * GET /api/analytics/compare?entityKind=artist&aId=1&bId=2
 *
 * Compares two SAME-kind entities. Both ids are interpreted as the single
 * validated `entityKind`. Validation (allowlist + bounded positive ints) runs
 * BEFORE any query; ids are bound as $N inside analytics.ts (never interpolated).
 */
export async function GET(request: NextRequest): Promise<Response> {
  const { searchParams } = request.nextUrl;

  const entityKind = searchParams.get("entityKind");
  if (!isValidEntityKind(entityKind)) {
    return Response.json(
      { error: 'Invalid or missing "entityKind" parameter. Must be artist, song, or album.' },
      { status: 400 },
    );
  }

  const aId = parsePositiveInteger(searchParams.get("aId"));
  const bId = parsePositiveInteger(searchParams.get("bId"));
  if (!aId || !bId) {
    return Response.json(
      { error: 'Invalid or missing "aId"/"bId" parameters. Both must be positive integers.' },
      { status: 400 },
    );
  }

  try {
    const payload = await getEntityComparison(entityKind, aId, bId);
    return Response.json(payload, { headers: { "Cache-Control": CACHE_CONTROL } });
  } catch {
    return Response.json(
      { error: "Could not load analytics. Please try again later." },
      { status: 500 },
    );
  }
}
