import { type NextRequest } from "next/server";

import { interpretQuery } from "@/lib/nlq/interpret";

function parseQuestion(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

export async function GET(request: NextRequest): Promise<Response> {
  const question = parseQuestion(request.nextUrl.searchParams.get("q"));

  if (!question) {
    return Response.json(
      { error: 'Invalid or missing "q" parameter.' },
      { status: 400 },
    );
  }

  try {
    return Response.json(interpretQuery(question));
  } catch {
    return Response.json(
      { error: "Failed to interpret query. Please try again later." },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest): Promise<Response> {
  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return Response.json(
      { error: 'Invalid or missing "question" field.' },
      { status: 400 },
    );
  }

  const question =
    payload && typeof payload === "object" && "question" in payload
      ? parseQuestion((payload as { question?: unknown }).question)
      : null;

  if (!question) {
    return Response.json(
      { error: 'Invalid or missing "question" field.' },
      { status: 400 },
    );
  }

  try {
    return Response.json(interpretQuery(question));
  } catch {
    return Response.json(
      { error: "Failed to interpret query. Please try again later." },
      { status: 500 },
    );
  }
}
