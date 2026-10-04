import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { searchConnection } from "@/lib/connections.functions";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Degrees of GitHub — Find developer connection paths" },
      { name: "description", content: "Discover the shortest evidence-backed path between two GitHub developers or a developer and an organization." },
      { property: "og:title", content: "Degrees of GitHub" },
      { property: "og:description", content: "Shortest evidence-backed connection paths between GitHub developers." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

type Result = Awaited<ReturnType<typeof searchConnection>>;

function Index() {
  const search = useServerFn(searchConnection);
  const [start, setStart] = useState("");
  const [target, setTarget] = useState("");
  const [kind, setKind] = useState<"user" | "org">("user");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      setResult(await search({ data: { start, target, kind } }));
    } catch (err) {
      setResult({ found: false, calls: 0, explored: 0, message: (err as Error).message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen grid-bg">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-primary">// six degrees</p>
        <h1 className="mt-3 font-display text-5xl font-bold leading-tight md:text-6xl">
          How are they <span className="text-primary">connected</span>?
        </h1>
        <p className="mt-4 max-w-xl text-muted-foreground">
          Trace the shortest chain between developers through repositories they actually worked on. Every link comes with evidence.
        </p>

        <form onSubmit={run} className="mt-10 space-y-4 rounded-xl border bg-card p-6 shadow-glow">
          <Field label="Starting user" value={start} onChange={setStart} placeholder="torvalds" />
          <div>
            <div className="mb-2 flex gap-2">
              {(["user", "org"] as const).map((k) => (
                <button type="button" key={k} onClick={() => setKind(k)}
                  className={`rounded-md px-3 py-1 font-mono text-xs transition ${kind === k ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground hover:bg-accent"}`}>
                  {k === "user" ? "target: user" : "target: organization"}
                </button>
              ))}
            </div>
            <Field label={kind === "user" ? "Target user" : "Target organization"} value={target} onChange={setTarget}
              placeholder={kind === "user" ? "gaearon" : "vercel"} />
          </div>
          <button disabled={loading || !start || !target}
            className="w-full rounded-md bg-primary py-3 font-mono text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-40">
            {loading ? "tracing graph…" : "find connection →"}
          </button>
        </form>

        {loading && <p className="mt-8 animate-pulse font-mono text-sm text-muted-foreground">Walking repositories and contributors… this can take 10–30 seconds.</p>}

        {result && !result.found && (
          <div className="mt-8 rounded-xl border border-destructive/40 bg-destructive/10 p-5 text-sm">{result.message}</div>
        )}

        {result?.found && (
          <section className="mt-10">
            <div className="mb-4 flex items-baseline justify-between font-mono text-xs text-muted-foreground">
              <span className="text-primary">{result.path.length - 1} degree{result.path.length - 1 === 1 ? "" : "s"} of separation</span>
              <span>{result.calls} API calls · {result.explored} nodes</span>
            </div>
            <ol className="space-y-0">
              {result.path.map((p, i) => (
                <li key={i}>
                  {p.via && (
                    <div className="ml-6 border-l-2 border-dashed border-primary/50 py-3 pl-8">
                      <a href={`https://github.com/${p.via.repo}`} target="_blank" rel="noreferrer"
                        className="font-mono text-sm text-primary hover:underline">⑂ {p.via.repo}</a>
                      <span className="ml-2 text-xs text-muted-foreground">{p.via.reason}</span>
                    </div>
                  )}
                  <a href={`https://github.com/${p.login}`} target="_blank" rel="noreferrer"
                    className="flex items-center gap-4 rounded-lg border bg-card p-3 transition hover:border-primary">
                    <img src={p.avatar} alt="" className="h-12 w-12 rounded-full border" />
                    <span className="font-display text-lg font-semibold">{p.login}</span>
                    {(i === 0 || i === result.path.length - 1) && (
                      <span className="ml-auto font-mono text-xs text-muted-foreground">{i === 0 ? "start" : "target"}</span>
                    )}
                  </a>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </main>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="block">
      <span className="mb-1 block font-mono text-xs text-muted-foreground">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-md border bg-input px-3 py-2 font-mono outline-none focus:border-primary" />
    </label>
  );
}
