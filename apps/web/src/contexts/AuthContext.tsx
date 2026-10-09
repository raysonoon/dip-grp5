import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase.js";

type LocalUserRole = "user" | "admin";

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  localUserId: number | null;
  localUserRole: LocalUserRole | null;
  loading: boolean;
  profileError: Error | null;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [localUserId, setLocalUserId] = useState<number | null>(null);
  const [localUserRole, setLocalUserRole] = useState<LocalUserRole | null>(null);
  const [profileError, setProfileError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let requestId = 0;
    let loadedForUserId: string | null = null;

    async function sync(nextSession: Session | null) {
      const thisRequest = ++requestId;
      setSession(nextSession);

      // Signed out: reset everything.
      if (!nextSession) {
        loadedForUserId = null;
        setLocalUserId(null);
        setLocalUserRole(null);
        setProfileError(null);
        setLoading(false);
        return;
      }

      // Token refresh for the same user: keep the existing profile.
      if (nextSession.user.id === loadedForUserId) {
        setLoading(false);
        return;
      }

      // New user: clear anything left over from the previous one.
      setLoading(true);
      setLocalUserId(null);
      setLocalUserRole(null);
      setProfileError(null);

      try {
        const apiBaseUrl = String(import.meta.env.VITE_API_BASE_URL ?? "")
          .replace(/\/+$/, "");
        const response = await fetch(`${apiBaseUrl}/auth/me`, {
          headers: { Authorization: `Bearer ${nextSession.access_token}` },
        });
        if (!response.ok) {
          throw new Error(
            `Unable to load the local user profile (${response.status})`,
          );
        }
        const profile = await response.json();

        // Discard stale responses
        if (!active || thisRequest !== requestId) return;

        loadedForUserId = nextSession.user.id;
        setLocalUserId(typeof profile.id === "number" ? profile.id : null);
        setLocalUserRole(
          profile.role === "admin" || profile.role === "user"
            ? profile.role
            : null,
        );
      } catch (error) {
        if (!active || thisRequest !== requestId) return;
        console.error("Unable to load local user profile", error);
        setProfileError(
          error instanceof Error ? error : new Error(String(error)),
        );
      } finally {
        if (active && thisRequest === requestId) setLoading(false);
      }
    }

    // INITIAL_SESSION event fires on subscribe in supabase-js v2,
    // a separate getSession() call isn't needed.
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      void sync(nextSession); // not awaited, and no supabase calls inside
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const signOut = useCallback(async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      localUserId,
      localUserRole,
      loading,
      profileError,
      signOut,
    }),
    [session, localUserId, localUserRole, loading, profileError, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}