import { type NextRequest } from "next/server";

import { searchAll } from "@/lib/search";

export async function GET(request: NextRequest): Promise<Response> {
  const query = request.nextUrl.searchParams.get("q")?.trim() ?? "";

  if (query.length < 2) {
    return Response.json(
      { error: 'Search query cannot be shorter than 2 characters.' },
      { status: 400 },
    );
  }

  try {
    const payload = await searchAll(query);
    return Response.json(payload);
  } catch {
    return Response.json(
      { error: "Failed to load search results. Please try again later." },
      { status: 500 },
    );
  }
}
