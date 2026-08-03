/**
 * Shapes mirror `backend/app/api/routes/readiness.py::_serialize_result` and
 * `backend/app/api/routes/sync.py` exactly (readiness-api spec + design.md's
 * "Interfaces / Contracts" table). Keep in sync with the backend response
 * shape if either side changes.
 */

export type ReadinessState = 'scored' | 'calibrating' | 'insufficient';

export type ReadinessBand = 'train_hard' | 'moderate' | 'easy' | 'rest';

export interface FactorContribution {
  name: string;
  available: boolean;
  z_value: number | null;
  weight: number;
  points: number | null;
}

export interface ReadinessToday {
  state: ReadinessState;
  score: number | null;
  band: ReadinessBand | null;
  factors: FactorContribution[];
  dominant_factor: string | null;
  reason: string;
  confidence: number;
  weights_version: string;
  days_until_scored: number | null;
  as_of: string;
  data_stale: boolean;
  last_synced_at: string | null;
}

export interface HistoryEntry {
  date: string;
  score: number | null;
  band: ReadinessBand | null;
  state: ReadinessState;
}

export type SyncTriggerResult =
  | { kind: 'accepted'; runId: string }
  | { kind: 'in_progress'; runId: string | null; startedAt: string | null }
  | { kind: 'auth_locked' }
  | { kind: 'cooldown'; retryAfterSeconds: number };

export type SyncRunStatus = 'running' | 'completed' | 'failed' | 'abandoned';

export interface SyncRun {
  id: string;
  status: SyncRunStatus;
  startedAt: string;
  heartbeatAt: string;
  completedAt: string | null;
  error: string | null;
}
