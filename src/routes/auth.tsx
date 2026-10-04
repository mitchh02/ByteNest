import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { getMe, signIn, signUp } from "@/lib/api";

export const Route = createFileRoute("/auth")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Sign in — GitConnectd" },
      { name: "description", content: "Sign in or create an account to use GitConnectd." },
      { property: "og:title", content: "Sign in — GitConnectd" },
      { property: "og:description", content: "Sign in or create an account to use GitConnectd." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AuthPage,
});

const signInSchema = z.object({
  email: z.string().trim().email("Enter a valid email").max(255),
  password: z.string().min(6, "Password must be at least 6 characters").max(72),
});

// Creating an account also needs a name (the users table requires one)
const signUpSchema = signInSchema.extend({
  first_name: z.string().trim().min(1, "Enter your first name").max(100),
  last_name: z.string().trim().min(1, "Enter your last name").max(100),
});

function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // Already signed in? Skip this page.
  useEffect(() => {
    getMe()
      .then((user) => { if (user) navigate({ to: "/", replace: true }); })
      .catch(() => {});   // backend unreachable: stay here; submitting will show the error
  }, [navigate]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);

    const parsed = mode === "in"
      ? signInSchema.safeParse({ email, password })
      : signUpSchema.safeParse({ email, password, first_name: firstName, last_name: lastName });
    if (!parsed.success) return setMsg({ ok: false, text: parsed.error.issues[0]!.message });

    setBusy(true);
    try {
      if (mode === "in") {
        await signIn(parsed.data.email, parsed.data.password);
      } else {
        await signUp(parsed.data as z.infer<typeof signUpSchema>);
      }
      navigate({ to: "/", replace: true });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Something went wrong" });
    } finally {
      setBusy(false);
    }
  };

  const input = "w-full rounded-md border bg-input px-3 py-2 font-mono outline-none focus:border-primary";

  return (
    <main className="min-h-screen grid-bg flex items-center justify-center px-6">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-glow">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-primary">// gitconnectd</p>
        <h1 className="font-display text-3xl font-bold">{mode === "in" ? "Sign in" : "Create account"}</h1>

        {mode === "up" && (
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block font-mono text-xs text-muted-foreground">First name</span>
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)}
                autoComplete="given-name" className={input} />
            </label>
            <label className="block">
              <span className="mb-1 block font-mono text-xs text-muted-foreground">Last name</span>
              <input value={lastName} onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name" className={input} />
            </label>
          </div>
        )}

        <label className="block">
          <span className="mb-1 block font-mono text-xs text-muted-foreground">Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email"
            className={input} />
        </label>
        <label className="block">
          <span className="mb-1 block font-mono text-xs text-muted-foreground">Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "in" ? "current-password" : "new-password"}
            className={input} />
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
