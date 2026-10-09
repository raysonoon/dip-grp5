import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Mail, Lock, AlertCircle, ArrowLeft } from "lucide-react";
import { supabase } from "../lib/supabase.js";

type AuthMode = "signin" | "signup";

export default function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [authError, setAuthError] = useState("");
  const [submittedSuccess, setSubmittedSuccess] = useState(false);
  const [confirmationRequired, setConfirmationRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const dismissTimerRef = useRef<number | null>(null);

  const clearDismissTimer = () => {
    if (dismissTimerRef.current !== null) {
      window.clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
  };

  const returnRoute =
    (location.state as { from?: string } | null)?.from ?? "/";

  // Dismiss / Close Handler - returns user to the app page they were on
  const handleDismiss = () => {
    clearDismissTimer();
    navigate(returnRoute);
  };

  useEffect(() => clearDismissTimer, []);

  const validateEmail = (value: string) => {
    if (!value.trim()) return "Email is required.";
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(value)) return "Please enter a valid email address.";
    return "";
  };

  const validatePassword = (value: string) => {
    if (!value) return "Password is required.";
    if (mode === "signup" && value.length < 6) {
      return "Password must be at least 6 characters long.";
    }
    return "";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const eErr = validateEmail(email);
    const pErr = validatePassword(password);

    setEmailError(eErr);
    setPasswordError(pErr);

    if (eErr || pErr) return;

    if (mode === "signup" && !displayName.trim()) {
      setAuthError("Display name is required.");
      return;
    }

    clearDismissTimer();
    setAuthError("");
    setConfirmationRequired(false);
    setSubmitting(true);

    try {
      const result = mode === "signin"
        ? await supabase.auth.signInWithPassword({ email: email.trim(), password })
        : await supabase.auth.signUp({
            email: email.trim(),
            password,
            options: { data: { display_name: displayName.trim() } },
          });

      if (result.error) throw result.error;

      if (mode === "signup" && !result.data.session) {
        setConfirmationRequired(true);
        return;
      }

      setSubmittedSuccess(true);
      dismissTimerRef.current = window.setTimeout(() => {
        dismissTimerRef.current = null;
        setSubmittedSuccess(false);
        navigate(returnRoute);
      }, 800);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleModeSwitch = (newMode: AuthMode) => {
    clearDismissTimer();
    setMode(newMode);
    setEmailError("");
    setPasswordError("");
    setAuthError("");
    setSubmittedSuccess(false);
    setConfirmationRequired(false);
  };

  return (
        <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center bg-black/10 px-4 py-12 backdrop-blur-[2px]">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-xl">
          <div className="mb-6">
          <button
            type="button"
            onClick={handleDismiss}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back</span>
          </button>
        </div>
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-foreground">
            {mode === "signin" ? "Welcome back" : "Create an account"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "signin"
              ? "Sign in to access your NTUmmy account"
              : "Sign up to start sharing your favorite campus stalls"}
          </p>

          {/* Mode Switcher */}
          <div className="mt-6 flex rounded-xl bg-muted p-1 text-sm font-medium">
            <button
              type="button"
              onClick={() => handleModeSwitch("signin")}
              className={`flex-1 rounded-lg py-2 transition-all cursor-pointer ${
                mode === "signin"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => handleModeSwitch("signup")}
              className={`flex-1 rounded-lg py-2 transition-all cursor-pointer ${
                mode === "signup"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Sign Up
            </button>
          </div>
        </div>

        {authError && (
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{authError}</span>
          </div>
        )}

        {confirmationRequired ? (
          <div className="my-6 rounded-xl border border-primary/30 bg-primary/10 p-4 text-center text-sm font-medium text-foreground">
            Check your email to confirm your account before signing in.
          </div>
        ) : submittedSuccess ? (
          <div className="my-6 rounded-xl bg-emerald-500/15 border border-emerald-500/30 p-4 text-center text-sm font-medium text-emerald-600 dark:text-emerald-400">
            {mode === "signin"
              ? "Signed in successfully!"
              : "Account created successfully!"}
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            {mode === "signup" && (
              <div>
                <label className="block text-xs font-semibold text-foreground uppercase tracking-wider mb-1.5">
                  Display name
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-foreground uppercase tracking-wider mb-1.5">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (emailError) setEmailError("");
                  }}
                  placeholder="student@e.ntu.edu.sg"
                  className={`w-full rounded-xl border bg-background pl-10 pr-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all ${
                    emailError
                      ? "border-destructive focus:ring-1 focus:ring-destructive"
                      : "border-border focus:border-primary focus:ring-1 focus:ring-primary"
                  }`}
                />
              </div>
              {emailError && (
                <div className="mt-1.5 flex items-center gap-1 text-xs text-destructive">
                  <AlertCircle className="h-3.5 w-3.5" />
                  <span>{emailError}</span>
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-foreground uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (passwordError) setPasswordError("");
                  }}
                  placeholder="••••••••"
                  className={`w-full rounded-xl border bg-background pl-10 pr-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all ${
                    passwordError
                      ? "border-destructive focus:ring-1 focus:ring-destructive"
                      : "border-border focus:border-primary focus:ring-1 focus:ring-primary"
                  }`}
                />
              </div>
              {passwordError && (
                <div className="mt-1.5 flex items-center gap-1 text-xs text-destructive">
                  <AlertCircle className="h-3.5 w-3.5" />
                  <span>{passwordError}</span>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow hover:opacity-90 disabled:opacity-50 active:scale-[0.99] transition-all"
            >
              {submitting ? "Please wait..." : mode === "signin" ? "Sign In" : "Create Account"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}