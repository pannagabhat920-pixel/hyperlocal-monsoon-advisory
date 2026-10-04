# Pannaga Operational Runbook

This runbook provides step-by-step procedures for deploying, maintaining, monitoring, and troubleshooting the Pannaga Hyperlocal Monsoon & Break Prediction System.

---

## 1. System Topology & Architecture

| Service | Technology | Port / URI | Health Check |
|---|---|---|---|
| **Backend API** | FastAPI / Python 3.11 (`uv`) | `http://localhost:8000` | `GET /healthz`, `GET /readyz` |
| **Frontend PWA** | Next.js 14 / TypeScript (`pnpm`) | `http://localhost:3000` | `GET /` |
| **Database** | PostgreSQL 15 + PostGIS 3.4 | `localhost:5432` | `pg_isready -U postgres` |
| **Cache & Broker**| Redis 7 Alpine | `localhost:6379` | `redis-cli ping` |
| **Worker Queue** | Celery 5.3 + Flower (optional) | Background container | `celery inspect ping` |
| **Scheduler** | Celery Beat | Background container | Heartbeat logs |

---

## 2. Daily & Sub-Seasonal Operational Workflows

### 2.1 Daily Data Ingestion (`02:00 IST`)
- **Celery Task:** `app.tasks.ingest_indices_task`
- **Actions:** Fetches NOAA CPC Oceanic Niño Index (ONI), Pentad RMM Madden-Julian Oscillation (MJO), and NOAA PSL Dipole Mode Index (IOD).
- **Graceful Degradation:** If upstream NOAA/BoM HTTP endpoints time out, the system retains the previous valid day's indices and flags `all_live=False`.

### 2.2 Weekly Forecast & Advisory Generation (`Monday 04:00 IST`)
- **Celery Task:** `app.tasks.run_weekly_pipeline_task`
- **Actions:**
  1. Queries Open-Meteo ensemble forecasts for all seeded Gram Panchayat centroids.
  2. Runs feature builder and ML simulator / XGBoost ensemble.
  3. Executes `AgronomicRule` engine to generate draft advisories for all active farmer profiles.
  4. Populates officer approval queues at `GET /api/v1/officer/queue`.
  5. Refreshes PostGIS spatial materialized view `mv_panchayat_weekly_forecasts`.

### 2.3 Officer Approval & Broadcast Workflow
1. Agricultural Extension Officers authenticate via mobile OTP at `/login`.
2. Inspect `PENDING` advisories in their assigned administrative blocks at `/officer`.
3. Review meteorological indicators and regional language translation previews.
4. Click **Approve & Generate TTS** (`POST /api/v1/officer/advisories/{id}/approve`).
   - Generates and caches Bhashini TTS WAV audio in `/app/media/audio`.
5. Execute **Dry-Run Preview** (`POST /api/v1/officer/broadcast`, `confirm: false`).
   - Verifies target farmer count, channel consent, and 72-hour cooldown rules.
6. Click **Confirm & Broadcast** (`POST /api/v1/officer/broadcast`, `confirm: true`).
   - If `data_source = SIMULATED`, all dispatches are tagged `BLOCKED_SIMULATED` and zero external SMS/WhatsApp calls are made.
   - If `data_source = LIVE`, Celery worker dispatches via Twilio / Gupshup provider with exponential backoff.

---

## 3. Incident Response & Troubleshooting

### Incident A: Farmer or Officer Unable to Log In (Rate-Limit 429)
- **Symptom:** `HTTP 429 Too Many Requests: Too many OTP requests. Try again in X seconds.`
- **Cause:** More than 3 OTP requests were made for the same phone number within a 10-minute window.
- **Resolution:**
  ```bash
  # Check active rate limit keys in Redis
  docker exec -t infra-redis-1 redis-cli keys "otp_rate:*"

  # Clear rate limit for the target phone number
  docker exec -t infra-redis-1 redis-cli del "otp_rate:+919999900002"
  ```

### Incident B: Simulated Data Reaching Production Alert
- **Symptom:** Farmer receives a simulated test message in production.
- **Cause:** Non-negotiable safety check failure.
- **Remediation:**
  1. Verify `backend/app/services/messaging_gateway.py`:
     ```python
     if advisory.data_source in (DataSource.SIMULATED, DataSource.HINDCAST):
         return log_blocked_notification(NotificationStatus.BLOCKED_SIMULATED)
     ```
  2. Verify environment variable `ENV=production` is set. In production, dev OTP `000000` is strictly rejected by `validate_dev_otp_policy()`.

### Incident C: Frontend TypeScript / OpenAPI Contract Drift
- **Symptom:** `pnpm gen:api:check` fails during CI or deploy.
- **Cause:** Backend schema was modified without updating the generated client.
- **Remediation:**
  ```bash
  cd frontend
  pnpm gen:api
  pnpm typecheck
  pnpm test
  ```

### Incident D: WebGL Crash on Low-End Devices
- **Symptom:** User device reports WebGL unsupported or context lost.
- **Behavior:** `components/map/TerrainMap3D.tsx` automatically detects WebGL failure and falls back to `ChoroplethMap2D.tsx`.
- **Verification:** High-contrast pattern fills (stripes, crosses, dots) and numeric thresholds ensure information accessibility without reliance on color alone.

---

## 4. Database Maintenance & PostGIS Migration

### Run Database Migrations
```bash
docker compose -f infra/docker-compose.yml exec backend uv run alembic upgrade head
```

### Re-seed Synthetic Boundary & Climatology Data
```bash
docker compose -f infra/docker-compose.yml exec backend uv run python scripts/seed_data.py
```

### Database Backup
```bash
docker exec -t infra-postgis-1 pg_dump -U postgres pannaga_db | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Database Restore
```bash
gunzip -c backup_20261004.sql.gz | docker exec -i infra-postgis-1 psql -U postgres -d pannaga_db
```

---

## 5. Health Checks & Monitoring Endpoints

- **Liveness probe:** `GET http://localhost:8000/healthz`
  - Returns `{"status": "ok"}`
- **Readiness probe:** `GET http://localhost:8000/readyz`
  - Validates PostgreSQL connection, PostGIS extension active, Redis reachable, and last ingest timestamp within acceptable threshold.
