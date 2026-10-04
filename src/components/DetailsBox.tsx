import { useState } from "react";
import { z } from "zod";

const schema = z.object({
  phone: z.string().trim().regex(/^\+?[0-9 ()-]{7,20}$/, "Enter a valid phone number"),
  email: z.string().trim().email("Enter a valid email").max(255),
  github: z.string().trim().regex(/^[A-Za-z0-9-]{1,39}$/, "Enter a valid GitHub username"),
});

export function DetailsBox() {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [github, setGithub] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const r = schema.safeParse({ phone, email, github });
    setMsg(r.success ? { ok: true, text: "Looks good!" } : { ok: false, text: r.error.issues[0]!.message });
  };

  const input = "w-full rounded-md border bg-input px-3 py-2 font-mono outline-none focus:border-primary";
  return (
    <form onSubmit={submit} className="mt-10 space-y-4 rounded-xl border bg-card p-6 shadow-glow">
      <h2 className="font-display text-xl font-semibold">Your details</h2>
      <label className="block">
        <span className="mb-1 block font-mono text-xs text-muted-foreground">Phone number</span>
        <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 555 123 4567" className={input} />
      </label>
      <label className="block">
        <span className="mb-1 block font-mono text-xs text-muted-foreground">Desired email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" className={input} />
      </label>
      <label className="block">
        <span className="mb-1 block font-mono text-xs text-muted-foreground">GitHub account</span>
        <input value={github} onChange={(e) => setGithub(e.target.value)} placeholder="octocat" className={input} />
      </label>
      {msg && (
        <p className={`rounded-md p-3 text-sm ${msg.ok ? "bg-primary/10 text-primary" : "bg-destructive/10 text-destructive"}`}>{msg.text}</p>
      )}
      <button className="w-full rounded-md bg-primary py-3 font-mono text-sm font-semibold text-primary-foreground transition hover:opacity-90">
        submit →
      </button>
    </form>
  );
}
