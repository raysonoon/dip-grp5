import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, Lock, AlertCircle, X } from "lucide-react";

type AuthMode = "signin" | "signup";

export default function SignInPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [submittedSuccess, setSubmittedSuccess] = useState(false);

  // Dismiss / Close Handler - returns user to previous page or home
  const handleDismiss = () => {
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/");
    }
  };

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const eErr = validateEmail(email);
    const pErr = validatePassword(password);

    setEmailError(eErr);
    setPasswordError(pErr);

    if (eErr || pErr) return;

    // Stub handler for Supabase integration
    console.log(`[Stub Submit] ${mode.toUpperCase()} attempt:`, { email, password });

    setSubmittedSuccess(true);
    setTimeout(() => {
      setSubmittedSuccess(false);
      handleDismiss();
    }, 1500);
  };

  const handleModeSwitch = (newMode: AuthMode) => {
    setMode(newMode);
    setEmailError("");
    setPasswordError("");
    setSubmittedSuccess(false);
  };

  return (
    /* Outer Backdrop: Clicking outside the card triggers handleDismiss */
    <div
      onClick={handleDismiss}
      className="flex min-h-[calc(100vh-10rem)] items-center justify-center px-4 py-12"
    >
      {/* Form Card Container: Stops click propagation so clicking inside doesn't close */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-xl"
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={handleDismiss}
          className="absolute right-4 top-4 rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          aria-label="Close page"
        >
          <X className="h-5 w-5" />
        </button>

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
              className={`flex-1 rounded-lg py-2 transition-all ${
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
              className={`flex-1 rounded-lg py-2 transition-all ${
                mode === "signup"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Sign Up
            </button>
          </div>
        </div>

        {submittedSuccess ? (
          <div className="my-6 rounded-xl bg-emerald-500/15 border border-emerald-500/30 p-4 text-center text-sm font-medium text-emerald-600 dark:text-emerald-400">
            {mode === "signin"
              ? "Signed in successfully!"
              : "Account created successfully!"}
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
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
              className="w-full rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow hover:opacity-90 active:scale-[0.99] transition-all"
            >
              {mode === "signin" ? "Sign In" : "Create Account"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}