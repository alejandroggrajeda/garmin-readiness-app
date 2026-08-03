import type {
  HistoryEntry,
  ReadinessToday,
  SyncRun,
  SyncTriggerResult,
} from './types';

/**
 * API key handling (Phase 7 task 7.4 / design.md "Single-user: no accounts,
 * one static X-API-Key"). This is a personal, single-user app with no
 * per-user auth system, so we deliberately avoid pulling in a secure-storage
 * dependency (`expo-secure-store` is not part of the PR1 scaffold and adding
 * it would be new, untested scope). Instead we use Expo's built-in
 * `EXPO_PUBLIC_*` env var inlining (supported since SDK 49): the key and API
 * base URL are supplied at build/dev time via `mobile/.env` (see
 * `mobile/.env.example`) and baked into the JS bundle, mirroring how the
 * backend's own `.env` holds the matching `API_KEY` secret. Documented
 * assumption — flagged in apply-progress as a deviation from "secure
 * storage" since design.md did not specify which of the two options to use.
 */
function getApiBaseUrl(): string {
  return process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
}

function getApiKey(): string {
  return process.env.EXPO_PUBLIC_API_KEY ?? '';
}

const DEFAULT_TIMEOUT_MS = 15000;
/** Render free tier cold start budget — design.md "Cold start" decision. */
const WAKE_TIMEOUT_MS = 90000;

async function apiFetch(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${getApiBaseUrl()}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey(),
        ...(options.headers as Record<string, string> | undefined),
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fires the unauthenticated `GET /healthz` warm-up ping (design.md's
 * "warm-up ping" mitigation for Render's cold start). Non-fatal by design:
 * callers only use this to drive a "waking server…" UI state, never to
 * block real data loading.
 */
export async function warmUp(): Promise<void> {
  try {
    await apiFetch('/healthz', {}, WAKE_TIMEOUT_MS);
  } catch {
    // Ignored — the subsequent authenticated calls carry their own errors.
  }
}

/** In-memory last-known-good snapshot (design.md: "rendering the locally
 * cached last-known score"). Not persisted to disk — see the module docstring
 * above re: no storage dependency in the PR1 scaffold; this survives app
 * foreground/background within the same process only. */
let cachedToday: ReadinessToday | null = null;

export function getCachedToday(): ReadinessToday | null {
  return cachedToday;
}

export async function getToday(): Promise<ReadinessToday> {
  const res = await apiFetch('/api/readiness/today');
  if (!res.ok) {
    throw new Error(`GET /api/readiness/today failed with status ${res.status}`);
  }
  const data = (await res.json()) as ReadinessToday;
  cachedToday = data;
  return data;
}

export async function getHistory(days = 30): Promise<HistoryEntry[]> {
  const res = await apiFetch(`/api/readiness/history?days=${days}`);
  if (!res.ok) {
    throw new Error(`GET /api/readiness/history failed with status ${res.status}`);
  }
  return (await res.json()) as HistoryEntry[];
}

export async function triggerSync(): Promise<SyncTriggerResult> {
  const res = await apiFetch('/api/sync', { method: 'POST' });
  const body = await res.json().catch(() => ({}) as Record<string, unknown>);

  switch (res.status) {
    case 202:
      return { kind: 'accepted', runId: body.run_id as string };
    case 409:
      return {
        kind: 'in_progress',
        runId: (body.run_id as string) ?? null,
        startedAt: (body.started_at as string) ?? null,
      };
    case 423:
      return { kind: 'auth_locked' };
    case 429:
      return { kind: 'cooldown', retryAfterSeconds: body.retry_after as number };
    default:
      throw new Error(`POST /api/sync failed with status ${res.status}`);
  }
}

export async function getSyncRun(runId: string): Promise<SyncRun> {
  const res = await apiFetch(`/api/sync/runs/${runId}`);
  if (!res.ok) {
    throw new Error(`GET /api/sync/runs/${runId} failed with status ${res.status}`);
  }
  const data = (await res.json()) as {
    id: string;
    status: SyncRun['status'];
    started_at: string;
    heartbeat_at: string;
    completed_at: string | null;
    error: string | null;
  };
  return {
    id: data.id,
    status: data.status,
    startedAt: data.started_at,
    heartbeatAt: data.heartbeat_at,
    completedAt: data.completed_at,
    error: data.error,
  };
}
