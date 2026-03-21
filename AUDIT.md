# Mission Control Audit — 2026-03-12

Repo: `RaapTechllc/openclaw-mission-control`
Host: Docker VM `dvm@100.97.87.28`
Path: `/home/dvm/mission-control`
Branch: `master`

## Executive Summary

Mission Control is a working full-stack OpenClaw orchestration app built as:
- **Backend:** Python 3.12 + FastAPI + SQLModel/SQLAlchemy + Alembic + Redis/RQ
- **Frontend:** Next.js 16 + React 19 + TypeScript
- **Database:** PostgreSQL 16
- **Queue/worker:** Redis + a dedicated `webhook-worker` service
- **Auth:** Clerk or local bearer-token mode
- **Gateway integration:** direct OpenClaw Gateway WebSocket RPC from backend services

The codebase is healthy enough to run, but the deployment on the Docker VM had an operational gap: **only the webhook worker was configured to auto-restart**. That explains the observed partial state where `openclaw-mission-control-webhook-worker-1` was up while the frontend/backend were down.

I fixed that quick win by adding `restart: unless-stopped` to the core stack services and bringing the full compose app back up.

## Architecture

```text
                    +-----------------------------+
                    |     OpenClaw Gateway(s)     |
                    |  WS RPC / status / sessions |
                    +--------------+--------------+
                                   |
                                   | WebSocket RPC
                                   v
+----------------+      HTTP      +---------------------------+      SQL      +----------------+
| Next.js UI     | <------------> | FastAPI backend           | <-----------> | PostgreSQL 16  |
| React 19       |                | app.main                  |               | mission_control|
| port 3060 host |                | port 8001 host -> 8000 ct |               +----------------+
+----------------+                |                           |
                                  | auth, boards, tasks,     |
                                  | gateways, approvals,     |
                                  | skills, orgs, metrics    |
                                  +-------------+-------------+
                                                |
                                                | queue jobs / retries
                                                v
                                         +------+------+
                                         | Redis + RQ |
                                         | port 6381  |
                                         +------+-----+
                                                |
                                                v
                                   +---------------------------+
                                   | webhook-worker            |
                                   | async job dispatch        |
                                   +---------------------------+
```

## What I Verified

### Runtime / ports

Services defined by `docker compose config --services`:
- `db`
- `redis`
- `backend`
- `frontend`
- `webhook-worker`

Current compose state on Docker VM:
- Frontend: `0.0.0.0:3060 -> 3000`
- Backend: `0.0.0.0:8001 -> 8000`
- Postgres: `0.0.0.0:5437 -> 5432`
- Redis: `0.0.0.0:6381 -> 6379`
- Webhook worker: internal worker container, no published host port

Reachability checks:
- `http://127.0.0.1:3060` → `200 text/html`
- `http://127.0.0.1:8001/docs` → `200 text/html`
- `http://127.0.0.1:8001/openapi.json` → `200 application/json`
- `http://100.97.87.28:3060` from workstation → `200`
- `http://100.97.87.28:8001/healthz` from workstation → `{"ok":true}`

### Backend stack

From `backend/pyproject.toml` and app source:
- FastAPI backend
- SQLModel + SQLAlchemy async session layer
- Alembic migrations
- Redis-backed RQ queue
- Optional Clerk auth plus local bearer-token mode
- Health endpoints: `/health`, `/healthz`, `/readyz`

### Frontend stack

From `frontend/package.json`:
- Next.js 16.1.6
- React 19.2.4
- TypeScript
- TanStack Query + table
- Radix UI
- Cypress + Vitest test tooling

### Gateway integration

The backend talks to OpenClaw Gateway directly through WebSocket RPC.
Key evidence:
- `backend/app/services/openclaw/gateway_rpc.py`
- `backend/app/api/gateway.py`
- `backend/app/api/gateways.py`
- gateway command/status/session endpoints exposed under `/api/v1/gateways/*`

This means Mission Control is acting as a proper gateway-aware control plane, not polling shell scripts or scraping logs.

## What Was Working

- Codebase builds successfully in Docker.
- Backend boots cleanly and applies migrations on startup.
- Frontend builds successfully and serves production pages.
- Postgres and Redis both become healthy.
- Gateway API surface is live; unauthenticated requests correctly return `401` where auth is required.
- The webhook worker has been running consistently.

## What Was Broken / Risky

### 1) Partial stack survival after restart

**Observed state before intervention:** only `openclaw-mission-control-webhook-worker-1` was up.

**Root cause:**
- `webhook-worker` had `restart: unless-stopped`
- `frontend`, `backend`, `db`, and `redis` did **not**

So after host or Docker restarts, the worker could come back without the actual UI/API stack.

### 2) Repo has local drift on the VM

At audit time, the VM checkout was not clean:
- modified: `backend/app/services/openclaw/provisioning.py`
- untracked: `compose.override.yml`

This matters because it means the running VM is carrying deployment-specific or in-progress changes outside a clean git baseline.

### 3) Fork maintenance risk

This repo is a public fork. That is fine for RaapTech customization, but it creates a process risk if we don’t explicitly manage:
- upstream remotes
- rebase/merge cadence
- what is `RaapTech-specific` vs `upstreamable`

### 4) Frontend build warning to track

`npm ci` emitted an engine warning for `orval@8.3.0` requiring Node `>=22.18.0` while the frontend image used Node `20.20.1` during build.

The build still completed, so this is not a current outage, but it is a future fragility point.

## Quick Wins Applied

### Added auto-restart to core services

Updated `compose.yml` so these services now use `restart: unless-stopped`:
- `db`
- `redis`
- `backend`
- `frontend`

Then ran:
- `docker compose up -d`

Result:
- full stack now healthy and reachable
- all expected services are running: `db`, `redis`, `backend`, `frontend`, `webhook-worker`

## How It Connects to OpenClaw Gateway

Mission Control’s backend exposes gateway-aware API routes and uses OpenClaw Gateway RPC service code to:
- register and inspect gateways
- query status and sessions
- issue gateway-backed operations through backend endpoints

Operationally, that means Mission Control sits above the gateway layer as the operator UI/API, while OpenClaw Gateway remains the runtime connection point into remote nodes, agents, and session control.

## RaapTech Fleet Fit

Mission Control can act as a clean operator console for the RaapTech OpenClaw fleet:
- **Gateways:** central registration and runtime checks
- **Agents:** track main/lead/worker assignments per board
- **Boards/groups:** coordinate execution lanes across Damien / Atlas / TopG / Remi / Maxx
- **Approvals:** human-in-the-loop checkpoints for sensitive actions
- **Webhooks:** event ingestion from external systems or task automations
- **Skills:** visible inventory and install/sync surface for reusable agent capabilities

### Recommended RaapTech use case

Use Mission Control as the **human-facing orchestration layer**, not as the source of truth for infrastructure.

Suggested boundaries:
- Mission Control: boards, tasks, approvals, gateway visibility, agent operations
- GitHub: code truth, PRs, release history
- Docker/Portainer: container truth
- OpenClaw Gateway: live session/runtime truth
- Discord/Telegram: notification and handoff layer

## Recommended Improvements

### High priority

1. **Add upstream remote and define fork policy**
   - Keep `origin` = RaapTech fork
   - Add `upstream` = original project
   - Decide what patches are RaapTech-only vs upstream PR candidates

2. **Keep a production-ready compose profile**
   - restart policies on all core services
   - health-based dependency ordering for app services
   - explicit env docs for ports and auth

3. **Normalize VM config drift**
   - review `compose.override.yml`
   - review local modifications in `backend/app/services/openclaw/provisioning.py`
   - either commit intentional changes or remove them

4. **Put Mission Control behind a stable reverse proxy URL**
   - likely Caddy, Nginx, or Tailscale Serve
   - expose frontend cleanly
   - keep backend private if possible

### Medium priority

5. **Upgrade frontend build runtime to Node 22 LTS**
   - aligns with current toolchain expectations
   - removes `orval` engine mismatch warning

6. **Add smoke checks**
   - frontend root returns 200
   - backend `/healthz` returns 200
   - backend `/openapi.json` returns 200
   - authenticated gateway command/status check in CI or deploy script

7. **Add deployment docs for operators**
   - where env files live
   - what ports are expected
   - how auth is configured
   - how gateway registration works
   - what to do after reboot or upgrade

### Nice-to-have

8. **Add observability basics**
   - structured logs to Loki or another sink
   - uptime checks for 3060 + 8001
   - alert when only worker is alive and web/API are down

9. **Board templates for RaapTech roles**
   - Damien = execution/build
   - Atlas = architecture/specs
   - TopG = security gate
   - Remi = customer voice
   - Maxx = coordination / mission control main

## Files Touched During This Audit

- `compose.yml`
  - added `restart: unless-stopped` to core services
- `AUDIT.md`
  - created
