# Garmin fixtures — SYNTHETIC PLACEHOLDERS

Every `*.json` file in this directory is **synthetically generated**, not
recorded from a real Garmin Connect account. The user has not yet supplied
real Garmin credentials at the time this fixture set was created (PR2,
`no-me-gusta-la-app-de-garmin-connect`).

Shapes were built from the `garminconnect==0.3.8` package's own typed
response models (`garminconnect.typed.HrvData`, `SleepData`,
`BodyBatteryEntry`, `TrainingReadiness` — inspected directly from the
installed library) for `sleep.json`, `hrv.json`, and `body_battery.json`.
`stress.json` and `training_status.json` have no typed model in this
library version, so those two are a best-effort approximation of the
well-known Garmin Connect wellness-endpoint shape and should be treated as
lower-confidence than the other four.

Each file is keyed by ISO date string (`YYYY-MM-DD`) so more sample days
can be appended without restructuring, and is loaded via
`tests/fixtures/garmin_loader.py::load_garmin_fixtures()`.

## Follow-up (not a blocker for this PR)

Once the user provides real Garmin Connect credentials:

1. Run `GarminConnectGateway` once against the live API for a handful of
   real dates.
2. Save the *actual* returned payloads here, replacing these files (keep
   the same `{date: payload}` JSON shape so `garmin_loader.py` needs no
   changes).
3. Re-run `pytest tests/contract/` — `FakeGarminGateway`'s injected-fixture
   priority (see `app/garmin/fake.py::_lookup`) means real fixtures
   transparently take over from the synthetic generator for any date they
   cover.
