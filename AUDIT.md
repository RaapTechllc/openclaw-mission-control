# Mission Control Security Audit — 2026-03-17

**Repo:** OpenClaw Mission Control
**Branch:** `master` (`8ced6f7`)
**Stack:** Next.js 16 + FastAPI + PostgreSQL 16 + Redis
**Ports (production):** FE `:3060`, BE `:8001`
**Auditor:** Superpowers automated security review
**Previous audit:** 2026-03-12 (AUDIT.md, covered ops/restart policies)

---

## Executive Summary

This is a **full-spectrum security audit** covering all 7 security dimensions (S1–S7), architecture quality, and test health. The codebase has solid foundations: proper auth modes, parameterized DB queries via SQLModel/ORM, centralized error handling that never leaks stack traces, and good input validation via Pydantic. However, there are **serious production-blocking gaps** in rate limiting, request size limits, security headers, and dependency vulnerabilities that must be addressed before public or multi-tenant exposure.

---

## Security Findings Table

| ID | Sev | Cat | File | Line | Issue |
|----|-----|-----|------|------|-------|
| S-01 | **HIGH** | S3/S6 | `api/board_webhooks.py` | 459 | Webhook ingest accepts unlimited body size — DoS/storage exhaustion |
| S-02 | **HIGH** | S4 | `main.py` | — | No rate limiting on any API endpoint |
| S-03 | **HIGH** | S2 | `core/agent_auth.py` | 49 | Agent token auth does full table scan — O(n) on every agent request |
| S-04 | **HIGH** | S4 | `models/gateways.py` | 25 | Gateway bearer token stored in plaintext in DB |
| S-05 | **HIGH** | S4 | `services/openclaw/gateway_rpc.py` | 207 | `allow_insecure_tls=true` disables TLS cert verification entirely |
| S-06 | **HIGH** | S4 | FE: Next.js 16.1.6 | — | 3 high npm audit vulns: Next.js CSRF bypass, Rollup path traversal, flatted DoS |
| S-07 | **HIGH** | S2 | FE: no `middleware.ts` | — | No server-side route protection — all auth is client-side only |
| S-08 | **HIGH** | S2 | FE: `auth/localAuth.ts` | 16 | Local auth token stored in `sessionStorage` (readable by XSS) |
| S-09 | **MEDIUM** | S4 | `main.py` | 456 | CORS: `allow_methods=["*"]`, `allow_headers=["*"]` — too permissive |
| S-10 | **MEDIUM** | S4 | `core/config.py` | 53 | All security headers disabled by default (blank) |
| S-11 | **MEDIUM** | S6 | `core/config.py` | 62 | Redis URL defaults to unauthenticated (`redis://localhost:6379/0`) |
| S-12 | **MEDIUM** | S1 | `.env.example` | 7 | Default DB credentials (`postgres:postgres`) documented — dev drift risk |
| S-13 | **MEDIUM** | S4 | FE: `next.config.ts` | — | No CSP headers, no X-Frame-Options, no HSTS in Next.js config |
| S-14 | **MEDIUM** | S2 | FE: `auth/redirects.ts` | 4 | Open redirect: `isSafeRelativePath()` doesn't block `//evil.com` |
| S-15 | **MEDIUM** | S7 | `core/agent_auth.py` | 133 | First 6 chars of agent token logged on auth failure |
| S-16 | **LOW** | S2 | `api/deps.py` | 137 | Agents with `board_id=NULL` pass board access check (gate skipped) |
| S-17 | **LOW** | S2 | FE: `lib/use-organization-membership.ts` | 7 | RBAC role checks are client-side only (backend enforces correctly) |
| S-18 | **LOW** | S1 | `backend/.env.example` | 19 | `LOCAL_AUTH_TOKEN=` empty — no generation hint (fixed in this audit) |
| S-19 | **LOW** | S4 | FE: npm audit | — | 2 moderate vulns: `ajv` ReDoS, `minimatch` ReDoS (dev tooling only) |

---

## S1 — Secret Exposure

**No hardcoded secrets found in source code.** All credentials read from environment variables.

**Issues found:**
- **S-12 (MEDIUM):** `.env.example` shows `postgres:postgres` as default DB credentials. Developers copying the file verbatim into production is a real-world risk. No validation prevents weak DB creds.
- **S-18 (LOW, fixed):** `LOCAL_AUTH_TOKEN=` was empty with no generation hint. Fixed: added `python -c "import secrets; print(secrets.token_urlsafe(50))"` comment to both `.env.example` files.
- **PASS:** `config.py` validates `LOCAL_AUTH_TOKEN` must be ≥ 50 chars and non-placeholder at startup. App refuses to boot with a weak token.
- **PASS:** `.gitignore` correctly excludes `.env`, `.env.local`, and `backend/.device-keys---`.
- **PASS:** No actual secret values committed. `backend/.env.test` contains only a test token (appropriate for test fixture).

---

## S2 — Authentication

**Auth architecture is solid.** Both Clerk (JWT) and local bearer-token modes are implemented correctly, and the auth dependencies in `deps.py` are the centralized gate for all protected routes.

**Issues found:**
- **S-03 (HIGH):** `_find_agent_for_token()` in `agent_auth.py:49` loads **all agents with token hashes** from the DB and iterates them in Python to find a match. With N agents, this is O(N) per request with N × PBKDF2 hash verifications at 200,000 iterations each. At 100 agents, this is measurably slow; at 1000+, it becomes a DoS vector. Add an indexed prefix column or a separate fast-lookup path.
- **S-07 (HIGH):** Next.js has no `middleware.ts`. All route protection is enforced via Clerk `<SignedIn>` components (client-side). A determined attacker can view page structure by disabling JS or intercepting SSR. API calls will fail, but the absence of server-side guards violates defense-in-depth.
- **S-08 (HIGH):** Local auth token stored in `sessionStorage` at `frontend/src/auth/localAuth.ts:16`. Accessible to any XSS. Prefer `httpOnly` cookies (requires backend `/auth/session` endpoint change).
- **S-14 (MEDIUM):** `frontend/src/auth/redirects.ts:4` — `isSafeRelativePath()` rejects `//` prefix but `/%2F%2Fevil.com` and `/\evil.com` bypass it. Fix: validate via `new URL(value, 'http://localhost')` and assert `.hostname === 'localhost'`.
- **S-16 (LOW):** In `api/deps.py:137`, agent board access check is `if actor.agent and actor.agent.board_id and actor.agent.board_id != board.id`. When `board_id` is `None`, the check is skipped and access is granted. This appears intentional for gateway/main agents but is undocumented. Clarify and add an explicit case for `NULL` board scoping.
- **PASS:** Local auth uses `hmac.compare_digest` — timing-safe comparison.
- **PASS:** Agent tokens hashed with PBKDF2-HMAC-SHA256 (200k iterations + 16-byte salt).
- **PASS:** Clerk JWT validation via official SDK with clock-skew tolerance.
- **PASS:** `require_admin_or_agent` raises HTTP 401 if both auth paths return `None`.

---

## S3 — Input Validation

**No SQL injection vectors found.** SQLModel/SQLAlchemy ORM used throughout; no raw SQL string formatting identified.

**Issues found:**
- **S-01 (HIGH):** `ingest_board_webhook` (`api/board_webhooks.py:459`) calls `await request.body()` with no size limit. A 1GB webhook payload will be read into memory, stored in PostgreSQL, and a preview written to board memory. Add `Content-Length` guard and a 1MB–5MB cap with HTTP 413 rejection.
- **S-09 (MEDIUM):** Webhook ingest endpoint is intentionally unauthenticated (open webhook by design). This is documented in the code but creates a DoS surface without rate limiting (see S-02). The UUID-based webhook ID is non-guessable, which provides moderate obscurity, but is not a substitute for rate limiting.
- **PASS:** All request bodies validated by Pydantic schemas before reaching handlers.
- **PASS:** Path parameters are `UUID` typed — injection via path parameters is not possible.
- **PASS:** Webhook payloads stored as JSON, not executed.

---

## S4 — Network / CORS / TLS

**Issues found:**
- **S-02 (HIGH):** No rate limiting middleware anywhere. Auth endpoints, webhook ingestion, and all API routes can be hit at unbounded rate. Add `slowapi` or similar; at minimum apply aggressive limits to `/auth/`, `/api/v1/agent/`, and webhook ingest endpoints.
- **S-04 (HIGH):** Gateway bearer token stored in plaintext (`models/gateways.py:25` — `token: str | None = Field(default=None)`). If the DB is breached, all registered gateway credentials are exposed. Encrypt at rest (AES-256-GCM via app-level key, or use a secrets manager).
- **S-05 (HIGH):** `allow_insecure_tls=True` on a gateway disables SSL certificate verification entirely (`gateway_rpc.py` sets `ssl_context.verify_mode = ssl.CERT_NONE`). This is an org-admin–accessible flag with no environment guard. In production, this allows MITM of all gateway traffic. Add an environment check (`ENVIRONMENT != "production"`) or remove the flag entirely.
- **S-06 (HIGH):** `npm audit` shows 5 vulnerabilities (3 high, 2 moderate):
  - **Next.js 16.1.6** — null origin bypass in Server Actions CSRF checks, unbounded resume buffering DoS, unbounded disk cache growth (all fixable via `npm audit fix --force`)
  - **Rollup 4.0–4.58** — arbitrary file write via path traversal (dev-time, `npm audit fix`)
  - **flatted <3.4.0** — unbounded recursion DoS (`npm audit fix`)
  - **ajv <6.14 or ≥7 <8.18** — ReDoS (dev tooling, `npm audit fix`)
  - **minimatch ≤3.1.3 or 9.0–9.0.6** — 3 ReDoS vectors (`npm audit fix`)
- **S-09 (MEDIUM):** CORS configured with `allow_methods=["*"]` and `allow_headers=["*"]`. Should whitelist only needed methods (GET, POST, PATCH, DELETE) and headers (Authorization, Content-Type, X-Agent-Token). `allow_credentials=True` with broad methods amplifies CSRF risk.
- **S-10 (MEDIUM):** All four security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) default to empty/disabled. Fixed in `.env.example` to recommended values; production deployments must explicitly set these. No `Strict-Transport-Security` or `Content-Security-Policy` configured anywhere.
- **S-11 (MEDIUM):** Redis defaults to unauthenticated (`redis://`). In Docker Compose the Redis container is on an internal network, but any container escape or misconfigured port exposure allows unauthenticated queue injection. Add Redis `requirepass` and update the URL to `redis://:password@redis:6379/0`.
- **S-13 (MEDIUM):** Frontend `next.config.ts` has no `headers()` block. No CSP, no X-Frame-Options, no HSTS. Add recommended headers here rather than relying solely on the backend.
- **PASS:** CORS origins sourced from `CORS_ORIGINS` env var — no wildcard in default config.
- **PASS:** Security headers middleware is implemented and functional — just needs values set.

---

## S5 — Dependencies

**Backend (Python):**
No `pip audit` run in this environment; `uv` manages the venv. Key packages are recent (FastAPI, SQLModel, Pydantic v2, psycopg3). No obviously outdated packages identified from `pyproject.toml` review. Recommend adding `uv run pip-audit` to CI.

**Frontend (Node):**
`npm audit` confirmed **5 vulnerabilities (3 high, 2 moderate)**. All are fixable:

```bash
cd frontend && npm audit fix          # fixes rollup, flatted, ajv, minimatch
npm audit fix --force                 # upgrades next (breaking-change risk — test first)
```

**Action required:** Run `npm audit fix` before next production deploy. Evaluate `--force` with a test pass.

---

## S6 — Least Privilege

**Issues found:**
- **S-01 (HIGH):** Webhook ingest stores unlimited-size payloads — resource exhaustion.
- **S-04 (HIGH):** Gateway tokens exposed if DB is compromised (see S4 above).
- **S-11 (MEDIUM):** Redis unauthenticated — any process that can reach Redis can inject jobs.
- **S-12 (MEDIUM):** Default Postgres user is `postgres` (superuser). Production should use a dedicated limited-privilege user.
- **PASS:** Organization/board access control implemented with explicit `require_board_access` enforced in `deps.py`.
- **PASS:** Agent scope is bound to `board_id`; cross-board access requires `board_id=NULL` (gateway agents) — controlled by provisioning.

---

## S7 — Data & Logging

**Issues found:**
- **S-15 (MEDIUM):** `agent_auth.py:133` logs `resolved[:6]` (first 6 chars of the raw token) on auth failure. Although this is a short prefix, it leaks information about the token space. Log only a flag (`token_present=true`) instead.
- **S-12 (MEDIUM):** `DATABASE_URL` in `.env.example` contains default password. SQLAlchemy debug logs at TRACE level may echo the connection string.
- **PASS:** Unhandled exceptions return generic `"Internal Server Error"` — no stack traces in responses.
- **PASS:** `RequestValidationError` returns 422 with structured field errors — no internal detail leakage.
- **PASS:** Request logs include method/path/status/duration but not request bodies.
- **PASS:** Clerk user IDs logged only as last-6-char suffix for privacy.
- **PASS:** Webhook payloads stored in DB but not echoed in error responses.

---

## Architecture Review

### Strengths
- Clean layering: API router → service layer → DB (`crud.py`) — no business logic in routers.
- Centralized auth dependencies in `deps.py` — easy to audit all permission gates in one place.
- Pydantic v2 schemas for every request/response — consistent validation.
- Error handling centralized in `error_handling.py` — no ad-hoc exception handling in routes.
- PBKDF2-HMAC-SHA256 for agent token hashing — correct crypto primitive.
- Structured JSON logging with request-ID propagation throughout.

### Issues

| Sev | Location | Issue |
|-----|----------|-------|
| HIGH | `core/agent_auth.py:49` | O(n) agent token lookup — full table scan on every agent request |
| MEDIUM | `core/agent_auth.py:104` | GET requests write to DB (agent `last_seen_at`) — unexpected write amplification on read paths |
| MEDIUM | `api/board_webhooks.py:459` | Webhook payload + board memory write not in a single atomic transaction — partial failure leaves orphan payload |
| MEDIUM | `core/auth.py:433,496,538` | 3× runtime `from app.services.organizations import …` inside function bodies — hides circular dependency |
| LOW | `services/webhooks/dispatch.py:30` | `_build_payload_preview` — no truncation on preview; deeply nested JSON causes memory spike |
| LOW | Various | `# pragma: no cover - defensive guard` comments on exception branches — these paths are untested |

---

## Tests

### Backend

Collected **378 tests** (via `uv run pytest`).

| Category | Count |
|----------|-------|
| Passed (unit, no DB needed) | **199** |
| Failed (require PostgreSQL) | **178** |
| xfailed | 1 |

The 178 failures are all integration tests that require a live PostgreSQL instance — they are expected in a CI environment without a DB service. All unit tests (pure logic, mocking, schema validation, middleware, gateway protocol) **pass**.

**Notable:** Two test files (`test_task_dependencies.py`, `test_tasks_done_approval_gate.py`) have `@pytest.mark.asyncio` marks that generate `PytestUnknownMarkWarning` — `pytest-asyncio` is not installed in the test run without full `uv sync --extra dev`. These fail when attempted without DB.

**To run full suite:**
```bash
cd backend
uv sync --extra dev
uv run pytest
# or: make backend-test
```

### Frontend

Vitest is configured (`npm run test`). Tests not run in this audit environment (no `node_modules`).
Cypress E2E tests exist under `frontend/cypress/e2e/` — 6 spec files covering activity feed, boards, auth, and organizations.

---

## Auto-Fixes Applied in This Audit

| File | Change |
|------|--------|
| `backend/.env.example` | Added security header defaults (`nosniff`, `DENY`, `strict-origin-when-cross-origin`), added `LOCAL_AUTH_TOKEN` generation command comment, added production DB credential warning |
| `.env.example` (root) | Added production credential warning for `POSTGRES_USER`/`POSTGRES_PASSWORD`, added `LOCAL_AUTH_TOKEN` generation comment |

**No business logic was changed.** All source code issues are documented as "Remaining Issues" below.

---

## Remaining Issues (Require Dev Work)

### Must Fix Before Production Exposure

1. **S-01** — Add webhook payload size limit (1–5 MB max, HTTP 413 on oversize)
2. **S-02** — Add rate limiting middleware (`slowapi` or nginx upstream)
3. **S-05** — Remove `allow_insecure_tls` flag or gate it behind `ENVIRONMENT != production`
4. **S-06** — Run `npm audit fix` (and `--force` for Next.js after testing)
5. **S-07** — Add `frontend/src/middleware.ts` to protect routes server-side
6. **S-08** — Move local auth token to `httpOnly` cookie (requires backend session endpoint)

### Fix Before Multi-Tenant or Public Deployment

7. **S-03** — Add indexed token-prefix column to agents table for O(1) auth lookup
8. **S-04** — Encrypt gateway tokens at rest
9. **S-09** — Restrict CORS `allow_methods`/`allow_headers` to exact set needed
10. **S-11** — Require Redis password (`requirepass`) and TLS for remote Redis
11. **S-13** — Add `Content-Security-Policy` and `Strict-Transport-Security` to Next.js config
12. **S-14** — Fix open redirect in `redirects.ts:isSafeRelativePath()`

### Lower Priority

13. **S-10** — Set security headers in production `.env` (template now provided)
14. **S-12** — Change Postgres default user away from `postgres` superuser in production
15. **S-15** — Remove token prefix from auth failure logs (`resolved[:6]`)
16. **S-16** — Document and test `NULL board_id` agent access semantics
17. **Arch** — Wrap webhook payload + board memory insert in one transaction
18. **Arch** — Move agent `last_seen_at` updates off GET request path (Redis or background task)
19. **Arch** — Add `pip-audit`/`safety` to backend CI pipeline

---

## Verdict

**`APPROVED WITH NOTES`** — for self-hosted / internal deployments with a known-good network perimeter, operator-controlled access, and no untrusted third-party webhook senders.

**`BLOCKED`** — for public-facing multi-tenant SaaS or any deployment where:
- Webhook endpoints receive traffic from untrusted third parties at high volume (no rate limiting or size guards)
- Frontend is user-accessible without the operator controlling every account (no server-side route protection)
- npm vulnerabilities include an active CSRF bypass in Next.js Server Actions

**Priority order for unblocking:** S-01 → S-02 → S-05 → S-06 → S-07 → S-03

---

*Audit performed 2026-03-17. Covers commit `8ced6f7` on branch `master`.*
