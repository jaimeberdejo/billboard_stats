import { neon } from "@neondatabase/serverless";

if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL is not configured.");
}

const sql = neon(process.env.DATABASE_URL);

export function getSql() {
  return sql;
}
