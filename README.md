# Bloom · Maternal health support

**Model activation is blocked by a source-data unit discrepancy.** The saved scaler's training ranges are HbA1c 30–50 and fasting glucose 3.6–8.9, inconsistent with the dataset's percent and mg/dL labels. The app saves observations but returns a clear 503 explanation for assessments. It does not guess conversions. Verify source units with the dataset author, correct and validate preprocessing (or retrain), and replace the guard in `backend/inference.py` as part of a tested model release. Raw `predict_artifact` inference is available only for compatibility tests and is not exposed through the API. Notification and probability workflows are tested with explicitly simulated predictions.

Responsive web application with a FastAPI REST backend, PostgreSQL-compatible storage and inference using the supplied trained PyTorch model. Includes registration, pregnancy episodes and dating, complete measurement entry, chronological history, probability estimates, in-app referral notifications, reviewed guidance, model registry and administration audit.

## Run locally

Use Python 3.12. From this folder in PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. Register an account and add a pregnancy. SQLite is the development default; no demonstration patient records are seeded. REST documentation is at `/docs`.

To use PostgreSQL, set `DATABASE_URL` before startup:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://maternal:YOUR_PASSWORD@localhost:5432/maternal'
```

Alternatively set `POSTGRES_PASSWORD` and run `docker compose up --build`. Create an administrator with `python -m backend.create_admin`, or `docker compose exec app python -m backend.create_admin`. Public registration creates mother accounts only. Administrators create draft content and explicitly publish it after review; no unreviewed clinical guidance is seeded.

## Mobile support

The same interface adapts to phones and tablets. For phone testing, open `http://YOUR_COMPUTER_LAN_IP:8000` on the same network and permit the port in your firewall. HTTPS hosting enables the service worker and home-screen installation where supported. A manifest and shell-only service worker are included. Health records are not cached or stored in browser local storage, and saving requires a network connection. Mobile support is a responsive web app, not a separate native Android/iOS application. Notifications are delivered in the app; SMS, email and background push providers are not configured.

## Model compatibility

Artifacts stay in `Results/`. The supplied `proposed_lstm.pt` has a single LSTM layer with input size 1, hidden size 50, dropout 0.20 and three output classes. The saved scaler identifies scikit-learn **1.9.0**; the training report identifies PyTorch **2.14.1**. Requirements preserve those versions. If your package mirror does not offer them, obtain the original training environment rather than silently loading the pickle with an incompatible scikit-learn version.

Feature order: Age (years), BodyTempF (°F), HeartRate (bpm), SystolicBP (mmHg), DiastolicBP (mmHg), BMI (kg/m²), HbA1c (%), FastingGlucose (mg/dL). All are required from one visit. Invalid units, missing/nonfinite values, implausible ranges, future timestamps and systolic pressure at or below diastolic pressure are rejected. Bounds are input plausibility checks, not clinical referral thresholds. Out-of-training-range values are flagged without clipping or refitting.

The training code serializes eight **static features as synthetic timesteps** into `[batch, 8, 1]`. This application preserves that behavior. It does not reinterpret visits as model timesteps, invent missing-value masks, or claim longitudinal prediction. True temporal prediction requires a separately trained and validated longitudinal model. Categories use argmax because clinical probability thresholds were not supplied. Registry entries record both artifact hashes, schema, decision rule and research status. Predictions retain their model version and source observation.

The report gives 76.0% held-out accuracy for this LSTM. This research prototype is not a clinically validated diagnostic device. Clinically reviewed content, referral rules, prospective validation and operating procedures must be supplied before patient-facing deployment.

## Verification

```powershell
.venv\Scripts\python -m pytest tests/test_app.py -q
```

Tests cover real artifact inference, probability parity, record validation, account isolation, chronological history, content review gating, notifications and admin permissions. Tests use an isolated in-memory SQLite database. PostgreSQL should additionally be exercised in the target deployment environment.

## Deployment

### Vercel

1. Import the GitHub repository into Vercel with the project root set to the repository root. `pyproject.toml` selects `backend.main:app` explicitly; do not select the separate `app/` implementation.
2. Connect a PostgreSQL database through Vercel Marketplace (for example Neon). Set `DATABASE_URL` to its connection URL, keeping required SSL query parameters. Both `postgres://` and `postgresql://` are normalized to the installed psycopg driver.
3. Set `APP_ENV=production` and `COOKIE_SECURE=true` for deployed environments. Use a separate PostgreSQL database for preview environments. SQLite is deliberately rejected on Vercel because function storage is not persistent.
4. Enable Fluid compute and, if the dependency bundle exceeds the standard Python limit, enable Large Functions with `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`. PyTorch and scientific packages can make the function large. Verify the actual deployment build rather than assuming local Windows package sizes apply to Linux.
5. Deploy, then verify `/api/health`, registration, a pregnancy profile, and measurement storage. The model-unit guard remains active. Create the administrator against the deployed database from a trusted local environment using `python -m backend.create_admin`; credentials belong in environment settings, not GitHub.

The configuration preserves the same-origin frontend/API and FastAPI security middleware. No database credentials or cloud access tokens are included. Vercel account access and a configured database are required to complete a live deployment.

Vercel's default `pyproject.toml` runtime installs the web/backend packages only. Scientific inference dependencies are an optional `model` extra while the unit-verification guard disables predictions; `requirements.txt` still includes them for local artifact tests. A validated model activation must also enable these dependencies in the deployment environment and recheck bundle limits.

References: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [PostgreSQL](https://vercel.com/docs/postgres), [Large Functions](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3).

The source repository is https://github.com/kennygeemartin/maternal_health_progression. GitHub Pages serves static files and cannot run this FastAPI application or its database. Deploy the Dockerfile on a Python/container hosting service and provide a PostgreSQL database; the container respects the provider's `PORT` environment variable. Raw clinical datasets are excluded from GitHub. The three required model artifacts are included without the named training records.

Use separate databases, credentials and environment variables for dev/test/production. Production requires a PostgreSQL URL, `APP_ENV=production`, `COOKIE_SECURE=true`, and an HTTPS reverse proxy. Authentication uses scrypt password hashes and hashed, revocable HttpOnly sessions. Mutating requests require `X-Bloom-Request: 1`; cross-origin requests are not enabled. API responses use `Cache-Control: no-store`.

Before production, configure ingress rate limits, database backups, monitoring and a migration process. Table creation currently uses SQLAlchemy `create_all`; schema upgrades require explicit migrations. Guidance publishes are audited. Model replacement is an operator-managed artifact release; the interface exposes registry metadata but does not accept executable model uploads. Keep source under version control and run tests in CI. No cloud deployment has been configured.
