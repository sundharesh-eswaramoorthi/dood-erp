# CHOLAVIN-ERP

ERP for an Indian B2B wholesale/distribution business. This repository is at
**Phase 0 — the walking skeleton**: the minimal end-to-end vertical slice that
proves the whole architecture is wired, so later phases (the stock/party ledgers
and the modules on top) drop into a working spine.

- **Plan:** the full implementation plan and the Phase-2 ledger design live as
  documents outside this repo.
- **Stack:** React + TypeScript + Vite + MUI · FastAPI + SQLAlchemy 2.0 +
  Pydantic v2 · PostgreSQL (system of record, RLS) · Redis (cache) · Celery
  (queue) · MongoDB (audit/activity, outbox-projected).

## What the skeleton proves

Adding a party exercises the entire spine in one request:

```
React (JWT) ─▶ FastAPI ─▶ require_permission + RLS-scoped session
                        ─▶ numbering_series (Postgres row-lock allocator)
                        ─▶ INSERT party  (RLS WITH CHECK)
                        ─▶ INSERT outbox_event      ── all one transaction
   commit ──▶ Celery drainer picks up the outbox row every ~3s
                        ─▶ MongoDB  audit_events   (the NoSQL home)
                        ─▶ Redis    recent_activity (the cache)
React ◀── GET /api/v1/activity  reads the Redis feed
```

## Run it

Prerequisites: Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Then:

- **Frontend:** http://localhost:5173  (login `admin` / `admin123`)
- **API docs:** http://localhost:8000/docs
- **Health:** http://localhost:8000/readyz

On start the `backend` service runs `alembic upgrade head` then seeds one org,
a branch + godown, the permission catalog, the five system roles, a super-user,
and the party numbering series.

### Quick API smoke test

```bash
# login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d 'username=admin&password=admin123' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# create a party (idempotent)
curl -s -X POST http://localhost:8000/api/v1/parties \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"name":"Sri Traders","party_type":"customer","phone":"9876543210"}'

# list parties (RLS-scoped) and the async activity feed
curl -s http://localhost:8000/api/v1/parties  -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/api/v1/activity -H "Authorization: Bearer $TOKEN"
```

## Tests

Property/invariant tests run against a throwaway `cholavin_test` database
(created + migrated + dropped automatically), driving random operation
sequences through the real engine and asserting the ledger invariants
(`on_hand == SUM(ledger)`, `reserved == SUM(active reservations)`,
`party net == SUM(debit) - SUM(credit)`), plus the oversell guard and the
append-only trigger.

```bash
docker compose exec backend pytest -q
```

## Layout

```
backend/            FastAPI app, models, Alembic migrations, Celery worker, seed
  app/core/         config, db (async + RLS session), security, deps, middleware
  app/models/       SQLAlchemy models
  app/modules/      auth · parties · activity · health
  app/services/     numbering (Postgres allocator) · outbox
  app/workers/      celery_app · tasks (outbox drainer)
  alembic/          migrations (0001 = phase-0 schema + party RLS)
frontend/           React + TS + Vite, MUI, TanStack Query, Zustand
docker-compose.yml  postgres · redis · mongo · backend · worker · frontend
```

## Roadmap (from the plan)

Phase 0 skeleton → 1 masters/party → **2 ledgers + stock core + integrity** →
3 purchase → 4 sales/billing/payments → 5 delivery + mobile → 6 accounts →
7 reports + dashboard → 8 migration/hardening/go-live → 9 e-invoice/e-way.
