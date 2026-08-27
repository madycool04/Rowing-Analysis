# Rowing Performance Analytics

A full-stack performance analytics platform for competitive and serious recreational rowers.
It answers "how am I rowing?" — pacing, heart-rate response, efficiency, training load, and
long-term trends — before it ever gets to "how fast can I row 2K?" 2K prediction exists here as
one advanced feature among many, not the point of the product.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Database Design](#database-design)
- [Analytics Methodology](#analytics-methodology)
- [Data Quality Handling](#data-quality-handling)
- [ML & 2K Prediction Methodology](#ml--2k-prediction-methodology)
- [Validation Strategy](#validation-strategy)
- [Running with Docker](#running-with-docker)
- [Running Tests](#running-tests)
- [CSV Import](#csv-import)
- [API Overview](#api-overview)
- [Screenshots](#screenshots)
- [Future Improvements](#future-improvements)

## Overview

The product hierarchy, deliberately, is:

1. Workout analysis
2. Performance trends
3. Pacing analysis
4. HR analysis
5. Efficiency
6. Training load
7. Personal bests
8. 2K prediction

The application should feel useful even if you never touch the prediction feature.

## Features

- **Workout import**: Concept2 CSV upload (summary or detailed/split exports, auto-detected) or
  manual entry, for both continuous pieces and interval sessions.
- **Workout analysis**: pace, watts, pacing consistency (CV), pace fade, first/second-half
  comparison, interval decay with regression and a noisy-estimate warning under 5 intervals.
- **HR analytics**: configurable heart-rate zones, efficiency factor, cardiac decoupling (gated on
  a genuinely continuous ≥20-minute effort with ≥90% HR coverage), and HR drift (gated on stable
  pacing).
- **Training load**: Banister TRIMP when HR data supports it, a clearly-labeled duration × relative-
  intensity fallback otherwise, plus daily/7-day/28-day rolling load. Acute:chronic workload ratio
  is shown as descriptive information only — **never as an injury prediction**.
- **Personal bests**: 500m/1K/2K/5K/6K/10K, detected from both whole-workout distances and
  individual interval reps.
- **Trends**: performance progression, watts, HR, efficiency factor, training load, pacing
  consistency, and interval decay, all over time.
- **2K prediction**: Paul's Law and previous-2K baselines, three ML models evaluated against them
  via chronological walk-forward validation, a conformal uncertainty interval, and a plain-language
  explanation of what changed since the last estimate.

## Architecture

```
backend/          FastAPI + SQLAlchemy 2.x + PostgreSQL
  app/
    core/         config, JWT/password hashing
    db/           engine/session, declarative base
    models/       User, Athlete, Workout, Segment, Split, Prediction
    schemas/      Pydantic v2 request/response models
    api/routes/   auth, athletes, workouts, analytics, predictions
    services/     csv_parser, workout_import, analytics, hr_zones,
                  training_load, performance, ml/{baselines,features,train,predictor}
    utils/        pace/watts conversion, defensive parsing helpers
frontend/         Vite + React + TypeScript + Recharts
  src/
    api/          typed axios client
    context/      auth state, persistent login
    components/   charts, cards, layout
    pages/        Dashboard, Upload, WorkoutDetail, History, Trends,
                  Performance, TrainingLoad, Predict
```

**Core data model**: `Workout → Segment → Split`. A continuous piece is one WORK segment; an
interval session is alternating WORK/REST segments. There is no separate database logic for
intervals versus continuous efforts — the same schema and the same analytics code handle both,
because interval decay, PB detection, and training load all operate on segments, not on a
"workout type" label.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x (`Mapped`/`mapped_column`), Pydantic v2,
  PostgreSQL, JWT auth, pytest
- **Frontend**: React, TypeScript, Vite, React Router, Recharts, axios
- **ML**: scikit-learn (Ridge, RandomForest), XGBoost
- **Infra**: Docker, Docker Compose

## Database Design

```
users(id, email, hashed_password, created_at)
athletes(id, user_id, name, dob, sex, weight_kg, height_cm, resting_hr, max_hr,
         best_2k_seconds, training_level, hr_zone_config, created_at, updated_at)
workouts(id, athlete_id, source, category, title, date,
         total_distance_m, total_duration_s,
         has_hr, hr_coverage_pct, has_splits, split_granularity,
         has_power, has_distance, has_stroke_rate,
         avg_hr, avg_stroke_rate, raw_source_filename, created_at)
segments(id, workout_id, ordinal, type[WORK/REST/WARMUP/COOLDOWN/OTHER],
         start_time_s, duration_s, distance_m)
splits(id, segment_id, ordinal, distance_m, elapsed_time_s,
       pace_s_per_500, watts, stroke_rate, heart_rate, calories)
predictions(id, athlete_id, model_name, model_version, prediction_date,
            target_distance_m, predicted_time_s, lower_bound_s, upper_bound_s,
            confidence, features_used, created_at)
```

Notably, `avg_watts` and `avg_pace_s_per_500` are **not** stored columns — they're computed
properties on the `Workout` model, always derived exactly from `total_distance_m` /
`total_duration_s`. Storing them redundantly would risk drift; deriving them costs nothing.
`avg_hr` and `avg_stroke_rate` *are* stored, because they can't always be derived (a summary-only
CSV import or a manual entry has no split rows to average over).

## Analytics Methodology

**The one rule that matters most**: average pace is *always* `total_elapsed_time / total_distance`,
never an average of individual split paces. Because the pace–power relationship is cubic
(`W = 2.80 / (t500/500)³`), naive pace-averaging silently misrepresents effort whenever splits are
uneven length or uneven pace. Every aggregate in this codebase routes through one function
(`average_pace_per_500`) that enforces this.

Pacing evenness is measured as the coefficient of variation of **split watts**, not split pace, for
the same reason. Watts are the canonical stored performance value; pace is derived from watts (or
vice versa) for display.

Every analytics response follows a stable envelope:

```json
{ "metrics": {...}, "data_quality": {...}, "insights": [...] }
```

`data_quality` always explains *why* a metric is or isn't available (e.g. "Cardiac decoupling
requires at least 90% heart-rate coverage") rather than silently omitting it or returning a
misleading number.

## Data Quality Handling

At import time, every workout records `has_hr`, `hr_coverage_pct`, `has_splits`,
`split_granularity`, `has_power`, `has_distance`, and `has_stroke_rate`. Downstream analytics check
these before computing anything:

- No splits → only summary-level metrics; pacing/interval analysis explicitly marked unavailable.
- HR coverage below 90% → cardiac decoupling unavailable.
- Pacing CV above ~3% → HR drift unavailable ("HR drift not calculated because pace was not
  sufficiently stable").
- Fewer than 5 historical 2K tests → ML prediction is not presented as athlete-specific-reliable;
  baselines are used and the UI says so explicitly.

## ML & 2K Prediction Methodology

**Baselines**:
- *Previous 2K*: your most recent actual 2K effort.
- *Paul's Law*: `T2 = T1 × (D2/D1)^1.06`, extrapolated from your most recent 5K/6K/10K. This is a
  rowing-community empirical heuristic, not a physiological law — the README says this because the
  app itself says this, in the API response's own note field.

**ML models**: Ridge regression, Random Forest, and XGBoost, trained on 19 features (recent
pace at each reference distance, recent training volume, HR/efficiency/pacing/decay metrics from
the most recent qualifying workout, rolling training load, athlete weight). **The app does not
assume XGBoost — or any model — is best.** Model selection happens purely by walk-forward MAE; see
below.

**Leakage prevention**: every feature for a target 2K is computed using only workouts strictly
before that 2K's date. This is enforced in code (`build_feature_vector` filters on
`workout.date < target_date`) and covered by dedicated tests that construct a workout with an
implausibly fast time and confirm it never influences its own feature vector.

## Validation Strategy

2K prediction is evaluated with **chronological expanding-window walk-forward validation**, never a
random train/test split:

1. For each historical 2K test, in date order, build its features from only earlier data.
2. Predict it using both baselines and (if enough earlier 2Ks exist) each ML model, fit only on
   those earlier 2Ks.
3. Record the error.
4. Add this 2K to the training pool and move to the next one.

The report this produces includes MAE/RMSE per method and a `best_method` field chosen by lowest
MAE — **if no ML model beats the baselines, the app says so and uses the baseline.** This isn't a
hypothetical: with only a handful of historical 2Ks, this will usually be the actual outcome, and
that's treated as a correct, honest result rather than a failure to hide.

**Small-dataset protection**: with fewer than 5 historical 2K tests, `sufficient_data_for_ml` is
`False`, and the prediction UI explains that baseline methods are being used until more data
accumulates — it does not present an unreliable athlete-specific model fit as if it were solid.

**Uncertainty**: the live prediction endpoint calibrates a split-conformal margin from the *same*
walk-forward residuals used to select the method, so a method that validated poorly produces a
wider (more honest) interval automatically. Below 3 calibration samples, no numeric range is shown
at all — just "Prediction confidence: Low."

The system never claims "AI accurately predicts your 2K." It evaluates baselines and models with
chronological validation and reports the resulting uncertainty, honestly, including when the
answer is "not enough data yet."

## Running with Docker

```bash
cp .env.example .env
# edit .env: set a real SECRET_KEY and a real POSTGRES_PASSWORD before any real deployment
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/api/v1
- API docs (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/health

Docker Compose waits for PostgreSQL's healthcheck before starting the backend, and for the
backend's healthcheck before starting the frontend. Tables are created automatically on backend
startup (`create_all`) for this project's scope — there's no separate migrations step to run.

To generate a realistic demo dataset for a fresh account:

```bash
docker compose exec backend python scripts/generate_sample_data.py --email demo@example.com --password demo12345
```

This creates the user if it doesn't exist and generates ~10 varied workouts (2K/5K/6K/10K tests,
30-minute steady state, 4×1K, 5×500m, 3×2K, a threshold piece, and a warmup+intervals+cooldown
session) with realistic pace/watts/HR/stroke-rate data across even, positive-split, negative-split,
fly-and-die, and interval-fade pacing patterns.

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

Tests use an isolated in-memory SQLite database per test (via a `db_session` fixture with a
`get_db` dependency override) — the application itself always uses PostgreSQL; SQLite is purely a
test-speed convenience and no production code path uses in-memory storage.

## CSV Import

Upload a Concept2 export via the "Upload CSV" tab on the Add Workout page. Two shapes are
supported and auto-detected:

- **Summary** (one row, aggregate totals only) → imported with `has_splits: false`; only
  totals-based analytics are computed.
- **Detailed** (one row per split/interval) → imported with `has_splits: true`. Nonzero
  `Rest Time`/`Rest Distance` columns signal an interval session (alternating WORK/REST segments
  are created); otherwise all rows become splits within a single continuous WORK segment.

Missing HR, stroke rate, or watts columns degrade gracefully to `null` per split rather than
corrupting the import. Watts and pace are derived from each other via the exact Concept2 formula
whenever only one of the two is present in the source file. Malformed files return a
human-readable error rather than a stack trace or silently-wrong data.

Prefer to log a workout by hand instead? Use "Enter Manually" on the same page — supports single
continuous pieces or multi-segment sessions (with types WORK/REST/WARMUP/COOLDOWN/OTHER).

## API Overview

All endpoints are under `/api/v1`. Full interactive docs at `/docs` once the backend is running.

```
POST   /auth/register              Create account (auto-creates a default athlete)
POST   /auth/login
GET    /auth/me

GET    /athletes
GET    /athletes/{id}
PATCH  /athletes/{id}

POST   /workouts                   Manual entry
POST   /workouts/upload            Concept2 CSV import
GET    /workouts                   Paginated, filterable, sortable
GET    /workouts/{id}
DELETE /workouts/{id}

GET    /analytics/workout/{id}     Full per-workout analytics
GET    /analytics/trends
GET    /analytics/performance      Personal bests
GET    /analytics/training-load

GET    /predictions/2k
```

Every route that touches athlete-owned data enforces ownership at the query level — a workout,
athlete, or prediction belonging to another user returns `404`, not `403`, to avoid confirming
that the resource exists at all.

## Screenshots

_(placeholder — add screenshots of the Dashboard, Workout Detail, and Trends pages here)_

## Future Improvements

Deliberately out of scope for this version, per the original roadmap:

- **Phase 2**: Concept2 Logbook API integration, OAuth, richer workout import
- **Phase 3**: Stroke-level analytics — drive length, drive time, recovery time, peak force, stroke power
- **Phase 4**: Coach accounts, multiple athletes per coach, athlete-to-athlete comparison
- **Phase 5**: Training recommendations, workout planning, performance forecasting

Also worth doing before a real production deployment: rate limiting, Alembic migrations (currently
`create_all` on startup, fine for this project's scope but not for schema evolution in production),
and structured application logging/monitoring.
