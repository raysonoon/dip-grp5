import { createClient } from "@supabase/supabase-js";

const environment = import.meta.env ?? globalThis.process?.env ?? {};
const supabaseUrl = String(environment.VITE_SUPABASE_URL ?? "").trim();
const supabasePublishableKey = String(
  environment.VITE_SUPABASE_PUBLISHABLE_KEY
    ?? "",
).trim();

function missingConfiguration() {
  throw new Error(
    "VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY must be configured",
  );
}

export const supabase = supabaseUrl && supabasePublishableKey
  ? createClient(supabaseUrl, supabasePublishableKey)
  : {
      auth: new Proxy({}, {
        get(target, property) {
          if (property in target) return target[property];
          return missingConfiguration();
        },
      }),
    };