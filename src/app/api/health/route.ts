import { NextResponse } from 'next/server';
import { sql } from '@/lib/db';

export async function GET() {
    try {
        const result = await sql`SELECT 1 as status`;
        return NextResponse.json({ status: 'healthy', db: result[0].status === 1 ? 'connected' : 'unknown' });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        return NextResponse.json(
            { status: 'error', message },
            { status: 500 }
        );
    }
}
