const GATEWAY = "https://connector-gateway.lovable.dev/github";

export type Evidence = { repo: string; reason: string };
export type PathStep = { login: string; avatar: string; via?: Evidence | undefined };
export type SearchResult =
  | { found: true; path: PathStep[]; calls: number; explored: number }
  | { found: false; calls: number; explored: number; message: string };

class Budget {
  calls = 0;
  constructor(public max: number) {}
}

async function gh(path: string, b: Budget): Promise<any> {
  if (b.calls >= b.max) return null;
  b.calls++;
  const lov = process.env["LOVABLE_API_KEY"];
  const key = process.env["GITHUB_API_KEY"];
  if (!lov || !key) throw new Error("GitHub connection is not configured");
  const res = await fetch(`${GATEWAY}/${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${lov}`,
      "X-Connection-Api-Key": key,
    },
  });
  if (res.status === 404) return null;
  if (res.status === 202 || res.status === 204) return [];
  if (!res.ok) {
    const body = await res.text();
    if (res.status === 403 && res.headers.get("x-ratelimit-remaining") === "0")
      throw new Error("GitHub rate limit reached. Try again in a few minutes.");
    throw new Error(`GitHub request failed [${res.status}]: ${body.slice(0, 200)}`);
  }
  return res.json();
}

type Node = string; // "u:login" | "r:owner/name"
const avatars = new Map<string, string>();

async function userRepos(login: string, b: Budget): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const repos = (await gh(`users/${login}/repos?per_page=30&sort=pushed&type=owner`, b)) ?? [];
  for (const r of repos) if (!r.fork && r.size > 0) out.set(r.full_name, "owner / maintainer");
  const events = (await gh(`users/${login}/events/public?per_page=100`, b)) ?? [];
  for (const e of events) {
    const reason =
      e.type === "PushEvent" ? "pushed commits"
      : e.type === "PullRequestEvent" ? "opened pull requests"
      : e.type === "PullRequestReviewEvent" ? "reviewed pull requests"
      : null;
    if (reason && e.repo?.name && !out.has(e.repo.name)) out.set(e.repo.name, reason);
  }
  return out;
}

async function repoContributors(full: string, b: Budget): Promise<string[]> {
  const list = (await gh(`repos/${full}/contributors?per_page=25`, b)) ?? [];
  if (!Array.isArray(list)) return [];
  return list
    .filter((c: any) => c.type === "User" && !String(c.login).endsWith("[bot]") && c.contributions >= 2)
    .map((c: any) => {
      avatars.set(c.login.toLowerCase(), c.avatar_url);
      return c.login as string;
    });
}

export async function findPath(start: string, target: string, kind: "user" | "org"): Promise<SearchResult> {
  const b = new Budget(45);
  const s = start.trim().toLowerCase();
  const t = target.trim().toLowerCase();

  const su = await gh(`users/${s}`, b);
  if (!su) return { found: false, calls: b.calls, explored: 0, message: `GitHub user "${start}" not found.` };
  avatars.set(s, su.avatar_url);

  // parent maps: node -> [parentNode, reason]
  const fromS = new Map<Node, [Node | null, string]>([[`u:${s}`, [null, ""]]]);
  const fromT = new Map<Node, [Node | null, string]>();
  const targetUsers = new Set<string>();

  if (kind === "user") {
    const tu = await gh(`users/${t}`, b);
    if (!tu) return { found: false, calls: b.calls, explored: 0, message: `GitHub user "${target}" not found.` };
    avatars.set(t, tu.avatar_url);
    fromT.set(`u:${t}`, [null, ""]);
    targetUsers.add(t);
  } else {
    const org = await gh(`orgs/${t}`, b);
    if (!org) return { found: false, calls: b.calls, explored: 0, message: `GitHub organization "${target}" not found.` };
    const members = (await gh(`orgs/${t}/public_members?per_page=50`, b)) ?? [];
    for (const m of members) {
      const l = m.login.toLowerCase();
      avatars.set(l, m.avatar_url);
      fromT.set(`u:${l}`, [null, `public member of ${t}`]);
      targetUsers.add(l);
    }
    const repos = (await gh(`orgs/${t}/repos?per_page=8&sort=pushed`, b)) ?? [];
    for (const r of repos) if (!r.fork) fromT.set(`r:${r.full_name.toLowerCase()}`, [null, `${t} repository`]);
  }

  const meet = (): Node | null => {
    for (const k of fromS.keys()) if (fromT.has(k)) return k;
    return null;
  };

  const expand = async (side: Map<Node, [Node | null, string]>, frontier: Node[]) => {
    const next: Node[] = [];
    for (const n of frontier.slice(0, 12)) {
      if (b.calls >= b.max) break;
      if (n.startsWith("u:")) {
        const repos = await userRepos(n.slice(2), b);
        for (const [r, reason] of [...repos].slice(0, 20)) {
          const k = `r:${r.toLowerCase()}`;
          if (!side.has(k)) { side.set(k, [n, reason]); next.push(k); }
        }
      } else {
        const devs = await repoContributors(n.slice(2), b);
        for (const d of devs) {
          const k = `u:${d.toLowerCase()}`;
          if (!side.has(k)) { side.set(k, [n, "contributor"]); next.push(k); }
        }
      }
      if (meet()) break;
    }
    return next;
  };

  let fs: Node[] = [`u:${s}`];
  let ft: Node[] = [...fromT.keys()];
  // Hop 0 check: start is a target member
  let m = meet();
  for (let i = 0; i < 8 && !m && b.calls < b.max; i++) {
    if (fs.length && (fs.length <= ft.length || !ft.length)) fs = await expand(fromS, fs);
    else if (ft.length) ft = await expand(fromT, ft);
    else break;
    m = meet();
  }

  if (!m)
    return {
      found: false, calls: b.calls, explored: fromS.size + fromT.size,
      message: "No connection found within this search's limits. Try a closer target or a more active starting user.",
    };

  // reconstruct node chain
  const left: { node: Node; reason: string }[] = [];
  let cur: Node | null = m;
  while (cur) { const [p, r]: [Node | null, string] = fromS.get(cur)!; left.unshift({ node: cur, reason: r }); cur = p; }
  const right: { node: Node; reason: string }[] = [];
  cur = fromT.get(m)![0];
  let prevReason = fromT.get(m)![1];
  while (cur) { const [p, r]: [Node | null, string] = fromT.get(cur)!; right.push({ node: cur, reason: prevReason }); prevReason = r; cur = p; }
  const chain = [...left, ...right];

  // collapse to developers with repo evidence
  const path: PathStep[] = [];
  let pendingRepo: Evidence | undefined;
  for (const { node, reason } of chain) {
    if (node.startsWith("r:")) {
      pendingRepo = { repo: node.slice(2), reason: reason || "shared contribution" };
    } else {
      const login = node.slice(2);
      path.push({ login, avatar: avatars.get(login) ?? `https://github.com/${login}.png`, via: pendingRepo });
      pendingRepo = undefined;
    }
  }
  if (kind === "org") {
    const last = path[path.length - 1];
    if (pendingRepo || !last || !targetUsers.has(last.login) && !pendingRepo) {
      path.push({ login: t, avatar: `https://github.com/${t}.png`, via: pendingRepo ?? { repo: t, reason: "organization" } });
    }
  }
  return { found: true, path, calls: b.calls, explored: fromS.size + fromT.size };
}
