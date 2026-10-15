# Bloom · Maternal health support

Responsive maternal health support application with FastAPI, PostgreSQL and a mobile-friendly web interface. Users can choose pregnancy month 1-9, view published monthly guidance, opt into email guidance using their registration address, and run a bundled pretrained research assessment without a model API key, token or external request. In-app elevated-risk notices remain available.

Resend integration is implemented, but live email requires privately configured credentials and a verified sender. The default pretrained CatBoost model runs inside the application. Its inference has no model-service fee or token requirement; hosting and email providers still have their own limits. It is a research classifier, not a clinically validated assessment or a longitudinal LSTM replacement. See [hosted model review](docs/hosted-model-review.md).

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

Alternatively set `POSTGRES_PASSWORD` and run `docker compose up --build`. Create an administrator with `python -m backend.create_admin`, or `docker compose exec app python -m backend.create_admin`. Public registration creates mother accounts only. Administrators create draft content and explicitly publish it after review; nine source-based monthly summaries are seeded as published under the project owner's explicit approval. This records publication approval, not an independent clinical review. Existing content is preserved. Admin drafts still require publication.

## Mobile support

The same interface adapts to phones and tablets. For phone testing, open `http://YOUR_COMPUTER_LAN_IP:8000` on the same network and permit the port in your firewall. HTTPS hosting enables the service worker and home-screen installation where supported. A manifest and shell-only service worker are included. Health records are not cached or stored in browser local storage, and saving requires a network connection. Mobile support is a responsive web app, not a separate native Android/iOS application. In-app notices and opt-in Resend email delivery are implemented; native push and SMS are not implemented.

## Original LSTM compatibility (disabled)

Artifacts stay in `Results/`. The supplied `proposed_lstm.pt` has a single LSTM layer with input size 1, hidden size 50, dropout 0.20 and three output classes. The saved scaler identifies scikit-learn **1.9.0**; the training report identifies PyTorch **2.14.1**. Requirements preserve those versions. If your package mirror does not offer them, obtain the original training environment rather than silently loading the pickle with an incompatible scikit-learn version.

Feature order: Age (years), BodyTempF (°F), HeartRate (bpm), SystolicBP (mmHg), DiastolicBP (mmHg), BMI (kg/m²), HbA1c (%), FastingGlucose (mg/dL). The bundled pretrained model requires six measurements from one visit; BMI and HbA1c are optional records and are not transmitted. The original local artifact expects all eight. Invalid units, missing/nonfinite values, implausible ranges, future timestamps and systolic pressure at or below diastolic pressure are rejected. Bounds are input plausibility checks, not clinical referral thresholds. Out-of-training-range values are flagged without clipping or refitting.

The training code serializes eight **static features as synthetic timesteps** into `[batch, 8, 1]`. Compatibility tests preserve that behavior; live assessments use the bundled six-input pretrained model instead. It does not reinterpret visits as model timesteps, invent missing-value masks, or claim longitudinal prediction. True temporal prediction requires a separately trained and validated longitudinal model. Categories use argmax because clinical probability thresholds were not supplied. Registry entries record both artifact hashes, schema, decision rule and research status. Predictions retain their model version and source observation.

The report gives 76.0% held-out accuracy for this LSTM. This research prototype is not a clinically validated diagnostic device. Clinically reviewed content, referral rules, prospective validation and operating procedures must be supplied before patient-facing deployment.

## Verification

```powershell
.venv\Scripts\python -m pytest tests/test_app.py tests/test_updates.py tests/test_bundled_model.py tests/test_postgres.py -q
```

Tests cover real artifact inference, probability parity, record validation, account isolation, chronological history, content review gating, notifications and admin permissions. Tests use an isolated in-memory SQLite database. PostgreSQL should additionally be exercised in the target deployment environment.

GitHub CI also runs `tests/test_postgres.py` against a disposable `bloom_ci` PostgreSQL service. It checks registration and login with an incompatible pre-existing `public.users` table and verifies that its original contents are preserved. The PostgreSQL test is skipped locally unless `POSTGRES_TEST_URL` is provided for that disposable database.

## Deployment

PostgreSQL deployments use a dedicated `bloom` schema, created automatically on startup. Existing tables in `public` are preserved and are not used by Bloom. This prevents collisions with older applications' `users` tables. The connected role needs permission to create the schema and its tables. Existing data is not automatically migrated between schemas. Local SQLite development continues to use its usual table layout. SQL error logging hides bound parameter values.

### Vercel

1. Import the GitHub repository into Vercel with the project root set to the repository root. `pyproject.toml` selects `backend.main:app` explicitly; do not select the separate `app/` implementation.
2. Connect a PostgreSQL database through Vercel Marketplace (for example Neon). The app accepts `DATABASE_URL` or `POSTGRES_URL` (with `DATABASE_URL` taking priority). Keep required SSL query parameters. Both `postgres://` and `postgresql://` are normalized to the installed psycopg driver.
3. Set `APP_ENV=production` and `COOKIE_SECURE=true` for deployed environments. Use a separate PostgreSQL database for preview environments. SQLite is deliberately rejected on Vercel because function storage is not persistent.
4. The lightweight Vercel runtime does not load PyTorch or download external executable model artifacts. The default numerical model runs with the Python standard library; its JSON weights are bundled explicitly. Optional external assessment runs at the configured provider.
5. Deploy, then verify `/api/health`, registration, a pregnancy profile, and measurement storage. The default bundled assessment requires no external-model consent or model token. Measurement action checks run independently of the research classifier and explain whether to continue monitoring, recheck, contact maternity care or seek urgent help; no measurement is adjusted to fit a model. Optional external providers still require per-pregnancy consent. Create the administrator against the deployed database from a trusted local environment using `python -m backend.create_admin`; credentials belong in environment settings, not GitHub.

The configuration preserves the same-origin frontend/API and FastAPI security middleware. No database credentials or cloud access tokens are included. Vercel account access and a configured database are required to complete a live deployment.

Vercel's default `pyproject.toml` runtime installs the web/backend packages only. Scientific inference dependencies are an optional `model` extra for the blocked original local model; `requirements.txt` still includes them for local artifact tests. A validated model activation must also enable these dependencies in the deployment environment and recheck bundle limits.

References: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [PostgreSQL](https://vercel.com/docs/postgres), [Large Functions](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3).

The source repository is https://github.com/kennygeemartin/maternal_health_progression. GitHub Pages serves static files and cannot run this FastAPI application or its database. Deploy the Dockerfile on a Python/container hosting service and provide a PostgreSQL database; the container respects the provider's `PORT` environment variable. Raw clinical datasets are excluded from GitHub. The three required model artifacts are included without the named training records.

Use separate databases, credentials and environment variables for dev/test/production. Production requires a PostgreSQL URL, `APP_ENV=production`, `COOKIE_SECURE=true`, and an HTTPS reverse proxy. Authentication uses scrypt password hashes and hashed, revocable HttpOnly sessions. Mutating requests require `X-Bloom-Request: 1`; cross-origin requests are not enabled. API responses use `Cache-Control: no-store`.

Before production, configure ingress rate limits, database backups, monitoring and a migration process. Table creation currently uses SQLAlchemy `create_all`; schema upgrades require explicit migrations. Guidance publishes are audited. Model replacement is an operator-managed artifact release; the interface exposes registry metadata but does not accept executable model uploads. Keep source under version control and run tests in CI. The repository is configured for the existing Vercel project; a successful deployment must still be checked in that account.

## Activate email on Vercel

Set these four variables in Vercel Settings > Environment Variables for Production, then deploy the latest main branch:

| Variable | Value |
| --- | --- |
| `RESEND_API_KEY` | A privately generated Resend API key with sending permission |
| `EMAIL_FROM` | `Bloom <updates@your-verified-domain>` using a domain verified in Resend |
| `APP_PUBLIC_URL` | The application's production HTTPS URL, without a trailing slash |
| `CRON_SECRET` | A privately generated random value of at least 32 characters |

Keep all credentials out of GitHub and chat. Resend's default testing sender is unsuitable for emailing arbitrary registered users. Verify your sending domain first. See [Resend sending API](https://resend.com/docs/api-reference/emails/send-email).

In Pregnancy settings, select the month and enable emails. Bloom first sends a non-health mailbox verification link, valid for 24 hours. Opening it verifies the registration address and queues that month's published guidance. Changing month sends the new guidance after verification. Identical month/content messages are deduplicated. Email delivery states distinguish pending, provider accepted, failed, cancelled and operator review; provider acceptance does not confirm inbox delivery. The provider receives the destination address and message content.

The authenticated daily cron runs at 07:00 UTC (08:00 Lagos, subject to provider scheduling precision). It checks up to 25 opted-in episodes fairly and retries up to two queued messages per run; this is a testing-scale worker, not a high-volume or urgent-alert delivery guarantee. User actions also attempt immediate delivery. Users must update their selected month; the app does not automatically change a manually selected month. New published guidance can be queued by cron. Elevated research predictions generate an in-app notice and a generic email only when the user opted in and verified their address. Do not wait for email or prediction when symptoms require care. Opt-out stops future sends.

Resend idempotency keys and persisted claims reduce duplicates. A delivery attempt older than 23 hours requires operator review because the provider idempotency window may have expired. Failed deliveries never become fictitious successful notices. Credentials are not yet supplied, so actual inbox delivery has not been tested.

[Vercel cron authentication](https://vercel.com/docs/cron-jobs/manage-cron-jobs) uses `CRON_SECRET` automatically as a Bearer header. The worker rejects requests without the matching secret.

Temperature entry and display use Celsius. New records retain `BodyTempC` / `degC`; model preprocessing converts to Fahrenheit only for inference. Existing Fahrenheit records remain readable and display in Celsius. Per-field unit labels and help notes replace unit dropdowns.

## Token-free pretrained assessments

The default `RISK_MODEL_PROVIDER=bundled` runs the pinned [MIT-licensed pretrained model](https://github.com/viochris/Maternal-Health-Risk-Model-Research) inside FastAPI using numeric JSON and standard Python. Model weights and the original fitted scaler are preserved; nothing is retrained at startup. There is no model API key, token, remote cold start, per-prediction service fee, or public model quota. Vercel hosting, PostgreSQL and Resend retain their own usage limits; this does not promise unlimited free infrastructure. If Vercel already has `RISK_MODEL_PROVIDER=huggingface` or `rest`, change it to `bundled` and deploy the latest main branch.

Inference needs actual age, blood pressure, glucose, temperature and heart rate. It derives only the documented Celsius-to-Fahrenheit and mg/dL-to-mmol/L unit conversions. Optional BMI and HbA1c do not affect this classifier. Missing values are rejected rather than fabricated. The clean source dataset does not cover many normal fasting glucose readings. The app retains and evaluates valid readings outside its reference envelope, flags unreliable research scores, shows Review needed and queues a review notice; it does not claim those scores prove clinical safety. The field `outside_training_range` retains its API name but now refers to the documented cleaned source dataset envelope rather than proven per-fold training bounds.

The engine's outputs match native CatBoost to 1e-13 on 1,219 entirely synthetic cases, including random values and both sides of learned split boundaries. Fixtures require no scientific packages or external service at runtime. This verifies faithful model conversion, not medical validity. See [model provenance and limitations](docs/hosted-model-review.md).

## Shared visual identity

A full-width maternal-care picture header appears on login, registration and every application view. Healthcare blue and warm rose accents replace the earlier green palette; locally hosted Manrope and Source Sans 3 improve readability. See [interface design, asset prompt and contrast checks](docs/interface-design.md).

Action rules and sources: [Care assessment](docs/care-assessment.md). Warning symptoms can be recorded with each visit. Care summaries remain available even when research inference is unavailable.
