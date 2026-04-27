import { neon } from '@neondatabase/serverless';

// Export the neon connection if the URL exists, otherwise export a dummy connection for build time.
export const sql = process.env.DATABASE_URL
    ? neon(process.env.DATABASE_URL)
    : neon('postgresql://placeholder:placeholder@placeholder.neon.tech/placeholder');
