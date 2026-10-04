import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/auth")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Sign in — Degrees of GitHub" },
      { name: "description", content: "Sign in or create an account to use Degrees of GitHub." },
      { property: "og:title", content: "Sign in — Degrees of GitHub" },
      { property: "og:description", content: "Sign in or create an account to use Degrees of GitHub." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AuthPage,
});

const schema = z.object({
  email: z.string().trim().email("Enter a valid email").max(255),
  password: z.string().min(6, "Password must be at least 6 characters").max(72),
});

function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate({ to: "/", replace: true });
    });
    const { data } = supabase.auth.onAuthStateChange((_e, s) => {
      if (s) navigate({ to: "/", replace: true });
    });
    return () => data.subscription.unsubscribe();
  }, [navigate]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    const parsed = schema.safeParse({ email, password });
    if (!parsed.success) return setMsg({ ok: false, text: parsed.error.issues[0]!.message });
    setBusy(true);
    if (mode === "in") {
      const { error } = await supabase.auth.signInWithPassword(parsed.data);
      if (error) setMsg({ ok: false, text: error.message });
    } else {
      const { data, error } = await supabase.auth.signUp({
        ...parsed.data,
        options: { emailRedirectTo: window.location.origin },
      });
      if (error) setMsg({ ok: false, text: error.message });
      else if (!data.session) setMsg({ ok: true, text: "Account created! Check your email to confirm, then sign in." });
    }
    setBusy(false);
  };

  return (
    <main className="min-h-screen grid-bg flex items-center justify-center px-6">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-glow">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-primary">// degrees of github</p>
        <h1 className="font-display text-3xl font-bold">{mode === "in" ? "Sign in" : "Create account"}</h1>
        <label className="block">
          <span className="mb-1 block font-mono text-xs text-muted-foreground">Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email"
            className="w-full rounded-md border bg-input px-3 py-2 font-mono outline-none focus:border-primary" />
        </label>
        <label className="block">
          <span className="mb-1 block font-mono text-xs text-muted-foreground">Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "in" ? "current-password" : "new-password"}
            className="w-full rounded-md border bg-input px-3 py-2 font-mono outline-none focus:border-primary" />
        </label>
        {msg && (
          <p className={`rounded-md p-3 text-sm ${msg.ok ? "bg-primary/10 text-primary" : "bg-destructive/10 text-destructive"}`}>{msg.text}</p>
        )}
        <button disabled={busy}
          className="w-full rounded-md bg-primary py-3 font-mono text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-40">
          {busy ? "…" : mode === "in" ? "sign in →" : "create account →"}
        </button>
        <button type="button" onClick={() => { setMode(mode === "in" ? "up" : "in"); setMsg(null); }}
          className="w-full font-mono text-xs text-muted-foreground hover:text-primary">
          {mode === "in" ? "No account? Create one" : "Have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
