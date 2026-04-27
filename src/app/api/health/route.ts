import { NextResponse } from "next/server";
import { getSql } from "@/lib/db";

export async function GET() {
  if (!process.env.DATABASE_URL) {
    return NextResponse.json(
      {
        status: "error",
        db: "unconfigured",
        message: "DATABASE_URL is not configured.",
      },
      { status: 503 },
    );
  }

  try {
    const sql = getSql();
    const result = await sql`SELECT 1 AS status`;

    return NextResponse.json({
      status: "healthy",
      db: result[0]?.status === 1 ? "connected" : "unknown",
    });
  } catch {
    return NextResponse.json(
      {
        status: "error",
        db: "unreachable",
        message: "Database query failed.",
      },
      { status: 500 },
    );
  }
}
