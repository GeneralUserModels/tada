/** Auth credentials — loaded from root .env in dev, shell env in CI/prod. */

export const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID ?? "";
export const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET ?? "";
export const SUPABASE_URL = process.env.SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY ?? "";
export const MICROSOFT_CLIENT_ID = process.env.MICROSOFT_CLIENT_ID ?? "";
