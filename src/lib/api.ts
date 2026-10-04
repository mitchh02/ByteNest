/**
 * Talks to the GitConnectd backend (FastAPI + MariaDB).
 *
 * Login: signIn/signUp save a token in localStorage; every later request sends it
 * as "Authorization: Bearer <token>", which is how the backend knows who you are.
 *
 * Backend address: set VITE_API_URL in the frontend's .env, e.g.
 *   VITE_API_URL=http://localhost:8000
 * It defaults to http://localhost:8000 if not set.
 */

const API_URL: string =
  (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_API_URL ??
  "http://localhost:8000";

const TOKEN_KEY = "six_degrees_token";

// ---------------------------------------------------------------------------
// Types (match what the backend returns)
// ---------------------------------------------------------------------------

export type User = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  job_title: string | null;
  company: string | null;
  bio: string | null;
  location: string | null;
  is_hiring: boolean | number;
};

export type AuthResponse = { token: string; user: User };

export type PathPerson = Pick<User, "id" | "first_name" | "last_name" | "job_title" | "company">;

export type PathResult = {
  target_id: number;
  path: number[];          // user ids, seeker first
  hops: number;
  score: number;           // 0 to 1, higher is stronger
  reasons: string[];       // why each pair knows each other, one per hop
  people: PathPerson[];    // same order as path
  job: { id: number; title: string; company: string; posted_by: number } | null;
};

export type IntroHop = {
  id: number;
  hop_index: number;
  from_user_id: number;
  to_user_id: number;
  message: string;
  status: "pending" | "accepted" | "declined";
};

export type IntroRequest = {
  id: number;
  seeker_id: number;
  target_id: number;
  job_id: number | null;
  path: number[];
  current_hop: number;
  status: "pending" | "completed" | "declined";
  hops: IntroHop[];
};

export type InboxItem = {
  id: number;
  request_id: number;
  hop_index: number;
  from_user_id: number;
  message: string;
  seeker_id: number;
  target_id: number;
  job_id: number | null;
};

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

export function getToken(): string | null {
  if (typeof window === "undefined") return null;   // not in a browser (server render)
  return window.localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// The one function every request goes through
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    // FastAPI puts the error message in "detail" (a list for validation errors)
    const detail = body?.detail;
    const message =
      typeof detail === "string" ? detail :
      Array.isArray(detail) ? detail[0]?.msg ?? "Invalid input" :
      `Request failed (${res.status})`;
    if (res.status === 401) setToken(null);   // token expired or invalid: sign out
    throw new ApiError(res.status, message);
  }
  return body as T;
}

const post = <T>(path: string, data: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(data) });

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function signIn(email: string, password: string): Promise<User> {
  const res = await post<AuthResponse>("/auth/login", { email, password });
  setToken(res.token);
  return res.user;
}

export async function signUp(data: {
  email: string; password: string; first_name: string; last_name: string;
}): Promise<User> {
  const res = await post<AuthResponse>("/auth/signup", data);
  setToken(res.token);
  return res.user;
}

/** The signed-in user, or null if nobody is signed in (or the token expired). */
export async function getMe(): Promise<User | null> {
  if (!getToken()) return null;
  try {
    return await request<User>("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

export function signOut() {
  setToken(null);
}

// ---------------------------------------------------------------------------
// Search and intros
// ---------------------------------------------------------------------------

export function searchPaths(seekerId: number, query: string, limit = 3, searchType: "role" | "manager" = "role") {
  const params = new URLSearchParams({ seeker_id: String(seekerId), q: query, limit: String(limit), search_type: searchType });
  return request<{ query: string; results: PathResult[] }>(`/search?${params}`);
}

export function createIntro(data: { seeker_id: number; path: number[]; job_id?: number; pitch?: string }) {
  return post<IntroRequest>("/intros", data);
}

export function getIntro(requestId: number) {
  return request<IntroRequest>(`/intros/${requestId}`);
}

export function getInbox(userId: number) {
  return request<InboxItem[]>(`/inbox/${userId}`);
}

export function respondToIntro(requestId: number, userId: number, accept: boolean) {
  return post<IntroRequest>(`/intros/${requestId}/respond`, { user_id: userId, accept });
}
