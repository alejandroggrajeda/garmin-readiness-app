# Garmin fixtures — REAL RECORDED RESPONSES (2026-08-02)

Every `*.json` file in this directory is a **real response recorded from a
live Garmin Connect account**, via one authenticated `GarminConnectGateway`
session (single `login()` call, no retries) on **2026-08-02**, fetching one
round of data per endpoint for that same date. This replaces the synthetic
placeholder set created in PR2 (`no-me-gusta-la-app-de-garmin-connect`) at a
time when no real credentials were available yet.

Large per-second/per-minute time-series arrays inside the real payloads
(`sleepLevels`, `sleepMovement`, `sleepHeartRate`, `sleepStress`,
`sleepBodyBattery`, `wellnessEpoch*List`, `hrvReadings`, `stressValuesArray`,
etc.) were truncated to at most 12 entries per array purely to keep these
files a reasonable size in the repo — every kept value is still a real,
unmodified sample point, just fewer of them. Nothing consumed by
`app/sync/normalize.py` lives inside a truncated array (it only reads
scalar fields — see "Discrepancies vs. the old synthetic fixtures" below),
so truncation has no effect on any test outcome.

Each file is keyed by ISO date string (`YYYY-MM-DD`) so more sample days
can be appended without restructuring, and is loaded via
`tests/fixtures/garmin_loader.py::load_garmin_fixtures()`.

## Discrepancies vs. the old synthetic fixtures (signal worth keeping)

Found while comparing the real recorded shapes against the synthetic
generator's assumptions in `app/garmin/fake.py` (PR2). None of these
required a code fix — `app/sync/normalize.py` already tolerates all of
them defensively (`.get(...) or {}` guards) — but they're worth knowing:

1. **`sleep.json` is far richer than assumed.** The real `fetch_sleep`
   payload has ~20 top-level keys (`hrvData`, `sleepLevels`,
   `sleepBodyBattery`, `restingHeartRate`, ...) in addition to
   `dailySleepDTO`, versus the synthetic generator's `dailySleepDTO`-only
   shape. `dailySleepDTO.sleepTimeSeconds` and
   `dailySleepDTO.sleepScores.overall.value` — the two fields
   `normalize.py` actually reads — are present with identical key names
   and types in the real response, so no functional impact.
2. **Inconsistent `userProfilePK` casing across endpoints/sub-objects.**
   The real API returns `userProfilePK` (capital `PK`) at the top of
   `stress.json` and inside `dailySleepDTO`, but `userProfilePk`
   (lowercase `k`) in `hrv.json`'s top level and in `sleep.json`'s nested
   `sleepNeed`/`nextSleepNeed` objects. Neither casing is read by any
   current code path, but a future consumer of this field must not assume
   one casing is universal.
3. **`training_status.json` came back fully `null`** for this account/date
   (`mostRecentTrainingStatus: null`, `mostRecentVO2Max: null`,
   `mostRecentTrainingLoadBalance: null`) — a real, valid "no training
   load data yet" state Garmin can return, not present in the synthetic
   generator (which always fabricated a populated
   `latestTrainingStatusData."1".acuteTrainingLoadDTO` tree). The real
   top-level key is `userId`, not `userProfilePK`. `normalize.py`'s
   `(training_status.get("mostRecentTrainingStatus") or {})` guard handles
   this cleanly (fields stay unset), but this recording could not validate
   the nested `acuteTrainingLoadDTO` shape against real *populated* data —
   that assumption remains unverified against a live payload. Re-record
   this endpoint once training-load data exists for the account.
4. **`body_battery.json` (the actual `BODY_BATTERY` endpoint) matches the
   synthetic assumption exactly** — `bodyBatteryValuesArray` entries are
   real `[timestamp, level]` 2-tuples, which is what
   `normalize.py`'s `len(v) == 2` filter expects. Note: the *unrelated*
   `bodyBatteryValuesArray` embedded inside `stress.json` (a different
   endpoint) uses a 4-element tuple
   (`[timestamp, status, level, version]`) instead — cosmetically similar
   field name, different endpoint, different shape; `normalize.py` never
   reads it, so no bug, but don't assume the two arrays are interchangeable.
5. **`activities.json` recorded a rest day** (`[]`) — already an exercised
   case in `test_fetch_activities_includes_realistic_rest_days`.

## Follow-up

- Re-record `training_status.json` on a date with actual training-load
  data to validate the nested shape currently only exercised by the
  synthetic generator.
- If real values are needed with full time-series resolution (not
  truncated), re-run the one-shot recording script against
  `GarminConnectGateway` directly rather than reading these fixtures.
