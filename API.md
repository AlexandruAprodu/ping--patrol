# SignalWatch — API & Messaging Contract v1.0 (FROZEN FOR THE PoC)

**Status:** FINAL implementation contract for the one-week proof of concept (v1.0). **Scope:** one developer, 4 domain microservices and a local test target. All HTTP/WebSocket/gRPC handlers and domain functions in this delivery are deliberately left as `...`. **This delivery contains no implementation and no tests.** Anything not specified below is outside v1.

This file is the **single source of truth** for HTTP REST, SSE, WebSocket, gRPC, RabbitMQ events, validation, errors, and status transitions. The corresponding code contracts are in `services/*/schemas.py`, `contracts/rules.proto` and this file. If you change a field here, change its schema and tests in the same commit.

## 0. Inventory — EVERY public/test HTTP route and realtime interface

| # | Owner | Method / interface | Path / RPC / event | Actor (who calls) | Purpose |
|---:|---|---|---|---|---|
| 1 | Monitoring | GET | `/health` | probe | Process liveness |
| 2 | Monitoring | POST | `/monitors` | operator/client | Create monitored HTTP target |
| 3 | Monitoring | GET | `/monitors` | viewer/client | List monitors |
| 4 | Monitoring | GET | `/monitors/{monitor_id}` | viewer/client | Read one monitor |
| 5 | Monitoring | DELETE | `/monitors/{monitor_id}` | operator/client | Remove monitor and stop scheduling |
| 6 | Monitoring | POST | `/monitors/{monitor_id}/check` | operator/client | Execute exactly one health check |
| 7 | Rules | GET | `/health` | probe | Process liveness (not rule evaluation) |
| 8 | Incidents | GET | `/health` | probe | Process liveness |
| 9 | Incidents | GET | `/incidents` | viewer/client | List/filter incidents |
| 10 | Incidents | GET | `/incidents/{incident_id}` | viewer/client; Alerts internally | Fetch canonical incident |
| 11 | Incidents | POST | `/incidents/{incident_id}/ack` | operator/client | Acknowledge active incident |
| 12 | Alerts | GET | `/health` | probe | Process liveness |
| 13 | Alerts | GET (SSE) | `/alerts/stream` | viewer/client | Receive incident notifications |
| 14 | Fake target | GET | `/health` | Monitoring | Controlled 200/500/503/timeout simulation |
| 15 | Fake target | GET | `/__test__/state` | test runner | Inspect test mode |
| 16 | Fake target | POST | `/__test__/mode` | test runner | Set test mode |
| 17 | Fake target | POST | `/__test__/reset` | test runner | Restore default test mode |
| 18 | Incidents | WebSocket | `/ws/incidents/{incident_id}` | operator/client | Bidirectional, ephemeral comments |
| 19 | Rules | gRPC unary | `RulesEngine/EvaluateCheck` | Monitoring internally | Evaluate failure streak |
| 20–23 | RabbitMQ | topic events | `rule.triggered`, `rule.recovered`, `incident.detected`, `incident.resolved` | services internally | Async state-change propagation |

**No endpoints beyond these are required.** In particular, **no** PATCH monitor, POST incident, manual resolve, auth, rules CRUD, notification persistence, pagination, historical checks, or frontend in v1. FastAPI may additionally expose automatically generated `/docs`, `/redoc`, and `/openapi.json`; these are **framework UI routes, not domain API contract**.

### 0.1 Roles / permissions (explicitly non-enforced)

| Conceptual role | Actions | Authentication / authorization in this PoC |
|---|---|---|
| Viewer | List/read monitors, incidents; subscribe SSE | None — conceptual only |
| Operator | All Viewer actions; create/delete/check monitors; acknowledge; WS comments | None — conceptual only |
| Service | gRPC and RabbitMQ calls; Alerts calls incident REST | Trusted internal Docker network |
| Test runner | Fake-target `__test__` routes | **Local only**, no auth |

**There is no RBAC, JWT, API key, or user account in v1.** “Operator” and “Viewer” name an endpoint's *intended caller*, **not** security boundaries. All published HTTP ports bind to `127.0.0.1`. Do not publish this PoC to the public internet.

### 0.2 Base URLs / protocols

| App | From host | Inside Docker Compose |
|---|---|---|
| Monitoring HTTP | `http://127.0.0.1:8001` | `http://monitoring:8000` |
| Rules HTTP health | `http://127.0.0.1:8002` | `http://rules:8000` |
| Rules gRPC | `127.0.0.1:50051` | `rules:50051` (insecure HTTP/2) |
| Incidents HTTP + WS | `http://127.0.0.1:8003`, `ws://127.0.0.1:8003` | `http://incidents:8000` |
| Alerts HTTP + SSE | `http://127.0.0.1:8004` | `http://alerts:8000` |
| Fake target HTTP | `http://127.0.0.1:8090` | `http://fake-target:8090` |
| RabbitMQ | Not published for AMQP | `rabbitmq:5672` |

**Common rules:** JSON encoded UTF-8; request `Content-Type: application/json` whenever a body is expected; `Accept: application/json` optional. Successful GETs return `200`. Created resource returns `201` with JSON body. DELETE returns `204` **without body**. All IDs are canonical UUID strings (e.g. `c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13`); path/query UUIDs must be syntactically valid, otherwise `422`. All datetimes: ISO-8601 UTC with a trailing `Z` (e.g. `2026-11-17T10:00:00Z`). Latencies are milliseconds, float >= 0. Unexpected JSON body properties are rejected with `422` on body-bearing endpoints. Results are JSON arrays, not paginated objects.

### 0.3 Failure contract — exact HTTP status rules

| HTTP | When used | Body |
|---|---|---|
| `200` | Query / check / acknowledge / fake control success | Named JSON schema below |
| `201` | Monitor created | `Monitor` |
| `204` | Monitor deleted | **Empty**, no JSON |
| `404` | Well-formed but unknown monitor/incident | `{"detail":"Monitor not found"}` or `{"detail":"Incident not found"}` |
| `409` | Attempt to ACK a RESOLVED incident | `{"detail":"Incident already resolved"}` |
| `422` | Invalid UUID, JSON, data type, field constraint or query enum | FastAPI validation object: `{"detail":[{"type":"...","loc":["body","..."],"msg":"...","input":"..."}]}`; actual fields depend on validation failure |
| `503` | Monitoring cannot reach Rules gRPC or cannot publish a transition to RabbitMQ | `{"detail":"Dependency unavailable"}` |
| `504` | Rules gRPC deadline exceeded during a manual check | `{"detail":"Rules evaluation timeout"}` |
| `500` | Unhandled defect | Generic FastAPI server error; **never leak credentials** |

A **monitored target** returning `500/503`, timing out, or refusing connection is **NOT an API 503/504**: `POST /monitors/{id}/check` still returns **200 with `healthy: false`**, unless *the platform's own* gRPC/broker dependency failed. Never confuse an unhealthy target with an unhealthy monitoring system.

In an HTTP endpoint annotated as “no request body,” send **no body**. No `PATCH`, custom error envelope, or partial update is defined. On `404`, lookups do not create resources. Responses may be eventually consistent after RabbitMQ events.

## 1. HTTP schemas — field-by-field

### 1.1 `MonitorCreate` (POST body)

| Field | Type | Required? | Validation | Meaning |
|---|---|---|---|---|
| `name` | string | yes | trim whitespace; length 1–100 after trimming | Human-readable name |
| `url` | string (HTTP URL) | yes | only `http://` or `https://`; no credentials | HTTP GET target |
| `interval_seconds` | integer | no; default **60** | 5–3600 inclusive | Scheduler interval |
| `failure_threshold` | integer | no; default **3** | 1–10 inclusive | Consecutive failures needed for alert |

No other fields are accepted. In dev Compose, use `http://fake-target:8090/health`, **not localhost**, because Monitoring runs inside a container.

```json
{
  "name": "Payments API",
  "url": "http://fake-target:8090/health",
  "interval_seconds": 3600,
  "failure_threshold": 3
}
```

### 1.2 `Monitor` (HTTP response)

All the fields of `MonitorCreate`, plus:

| Field | Type | Origin |
|---|---|---|
| `id` | string UUID | Server generated once |
| `created_at` | ISO-8601 UTC string | Server generated once |

```json
{
  "id": "c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13",
  "name": "Payments API",
  "url": "http://fake-target:8090/health",
  "interval_seconds": 3600,
  "failure_threshold": 3,
  "created_at": "2026-11-17T10:00:00Z"
}
```

No `enabled`, `last_status`, `updated_at` or latest check history in v1. A normalized URL may receive a trailing `/` if the URL had no path; tests use `/health`.

### 1.3 `CheckResult` (one check)

| Field | Type | Constraints / meaning |
|---|---|---|
| `monitor_id` | string UUID | Checked monitor |
| `checked_at` | ISO-8601 UTC string | End of check |
| `healthy` | boolean | true **only** if target responded HTTP **200–299** |
| `status_code` | integer or null | Actual target status (200–599); `null` for timeout, DNS, connection failure |
| `latency_ms` | number (float) | Measured target HTTP attempt duration, >= 0 |
| `transition` | string enum | `NONE` / `TRIGGERED` / `RECOVERED` |
| `consecutive_failures` | integer >=0 | Resulting rule-engine count |

```json
{
  "monitor_id": "c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13",
  "checked_at": "2026-11-17T10:00:20Z",
  "healthy": false,
  "status_code": 503,
  "latency_ms": 24.5,
  "transition": "TRIGGERED",
  "consecutive_failures": 3
}
```

For timeout, use `{"healthy":false,"status_code":null}`. Scheduler checks must follow the same semantics but do not expose separate endpoints.

### 1.4 `Incident` (HTTP response; also nested in SSE)

| Field | Type | Constraints / meaning |
|---|---|---|
| `id` | string UUID | Server generated |
| `monitor_id` | string UUID | Monitor that triggered it |
| `title` | string | Exactly `HTTP monitor unavailable` in v1 |
| `severity` | string | Exactly `critical` in v1 |
| `status` | enum string | `OPEN`, `ACKNOWLEDGED`, `RESOLVED` |
| `created_at` | ISO-8601 UTC string | Creation time |
| `updated_at` | ISO-8601 UTC string | Last status mutation; initially same as `created_at` |

```json
{
  "id": "2e27b8da-84ee-4c6d-b6cf-a05b9b688c90",
  "monitor_id": "c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13",
  "title": "HTTP monitor unavailable",
  "severity": "critical",
  "status": "OPEN",
  "created_at": "2026-11-17T10:00:20Z",
  "updated_at": "2026-11-17T10:00:20Z"
}
```

No assignee, comments in SQL, `resolved_by`, timestamps for individual transitions or manually selected severity in v1.

### 1.5 `Mode` (fake target controls)

| Field | Type | Required? | Validation |
|---|---|---|---|
| `status_code` | integer | no; default `200` | 200–599, except 204, 205 and 304 (which forbid response bodies) |
| `delay_ms` | integer | no; default `0` | 0–10000 |

Example: `{"status_code":503,"delay_ms":0}`. Test state is **global to the fake-target process**, so run tests serially.

## 2. Monitoring HTTP service — `localhost:8001`

### M1 — `GET /health`

- **Actor:** probe/test runner. **Purpose:** confirms that the FastAPI process is alive (not that Postgres, Rules, RabbitMQ, or targets are healthy).
- **Input:** no body, path, or query.
- **Success:** `200`, `{"status":"ok","service":"monitoring"}`.
- **Failure:** `500` if process cannot serve the request.

### M2 — `POST /monitors`

- **Actor:** operator. **Purpose:** persist one monitor; make it eligible for interval scheduling.
- **Input:** JSON `MonitorCreate` (see §1.1). No query parameters.
- **Success:** `201` `Monitor` (see §1.2). UUID generated by server. `created_at` UTC.
- **Failure:** `422` invalid body (including unsupported URL schemes and unexpected fields); `500` unexpected persistence error.
- **Side effects:** persist monitor; start/check scheduler on its configured interval. **Do not perform a health check automatically in the POST handler**; the interval begins after creation.

```bash
curl -i -X POST http://localhost:8001/monitors \
  -H 'Content-Type: application/json' \
  -d '{"name":"Payments API","url":"http://fake-target:8090/health","interval_seconds":3600,"failure_threshold":3}'
```

### M3 — `GET /monitors`

- **Actor:** viewer. **Purpose:** list all registered monitors.
- **Input:** no body, path or query; pagination **not** supported.
- **Success:** `200` `Monitor[]`; zero monitors = `[]`. Sort `created_at` ascending and `id` ascending as tie-breaker.
- **Failure:** `500` unexpected persistence error.

```json
[
  {
    "id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13",
    "name":"Payments API",
    "url":"http://fake-target:8090/health",
    "interval_seconds":3600,
    "failure_threshold":3,
    "created_at":"2026-11-17T10:00:00Z"
  }
]
```

### M4 — `GET /monitors/{monitor_id}`

- **Actor:** viewer. **Purpose:** fetch a single monitor.
- **Path input:** `monitor_id` — required UUID. No body/query.
- **Success:** `200` `Monitor` as §1.2.
- **Failure:** `422` malformed UUID; `404 {"detail":"Monitor not found"}` for valid absent UUID.

```bash
curl -i http://localhost:8001/monitors/c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13
```

### M5 — `DELETE /monitors/{monitor_id}`

- **Actor:** operator. **Purpose:** stop scheduling and delete monitor.
- **Path input:** `monitor_id` — required UUID. No body/query.
- **Success:** `204` **empty response**.
- **Failure:** `422` malformed UUID; `404 {"detail":"Monitor not found"}` for valid absent UUID.
- **Side effects:** no further scheduled checks for this monitor. Already-created incidents remain readable (historical records). Rules Engine may retain orphan in-memory counters until restart; cleaning them is outside v1. If a check is already in progress, it may finish; no **new** check may start after deletion.

### M6 — `POST /monitors/{monitor_id}/check`

- **Actor:** operator/test runner. **Purpose:** perform one real HTTP GET immediately, evaluate it via gRPC and return the resulting decision.
- **Path input:** `monitor_id` — required UUID. **No request body/query.**
- **Success:** `200` `CheckResult` (§1.3), including the actual target HTTP attempt result.
- **Failure:** `422` malformed UUID; `404` unknown monitor; `503 {"detail":"Dependency unavailable"}` if gRPC unavailable or required transition event cannot be sent; `504 {"detail":"Rules evaluation timeout"}` if gRPC deadline exceeded; `500` other backend defects.
- **Operation order:** load monitor → acquire **per-monitor** lock → async HTTP GET (timeout: env `CHECK_TIMEOUT_SECONDS`, default 1.0s) → unary gRPC `EvaluateCheck` with deadline 2.0s → on `TRIGGERED`/`RECOVERED` publish one RabbitMQ event → return. `NONE` publishes nothing. Healthy HTTP status = 2xx. Timeout/DNS/connection failures are evaluated as unhealthy with `status_code: null`, **not** propagated as HTTP 504.
- **Concurrency:** do not overlap manual/manual or manual/scheduler checks for the same monitor. Checks on *different* monitors may execute concurrently. Multiple replica scheduling is out of v1.

**Illustrative third failure:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"monitor_id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13","checked_at":"2026-11-17T10:00:20Z","healthy":false,"status_code":503,"latency_ms":24.5,"transition":"TRIGGERED","consecutive_failures":3}
```

**Expected sequence for threshold=3:** failed checks → `NONE` (count1), `NONE` (count2), `TRIGGERED` (count3), `NONE` (count4+). First successful check → `RECOVERED` (count0). Next successful check → `NONE` (count0).

## 3. Rules Engine — HTTP `localhost:8002`, gRPC `localhost:50051`

### R1 — `GET /health`

- **Actor:** probe. **Input:** none. **Output:** `200`, `{"status":"ok","service":"rules"}`. Checks HTTP listener liveness, **not** gRPC state integrity. **Failure:** `500` unexpected error.

### R2 — Unary `signalwatch.rules.v1.RulesEngine/EvaluateCheck`

- **Actor:** internal Monitoring gRPC client. **Transport:** plaintext gRPC, request/reply (Monitoring **awaits** result). **Source:** [`contracts/rules.proto`](contracts/rules.proto).

`CheckRequest` fields (wire field numbers locked):

| Field # | Name | Proto type | Required logical constraint |
|---:|---|---|---|
| 1 | `monitor_id` | `string` | Nonempty canonical UUID |
| 2 | `healthy` | `bool` | From HTTP check |
| 3 | `failure_threshold` | `int32` | 1–10 |
| 4 | `status_code` | `int32` | 200–599 if a response, **0 if no HTTP response** |
| 5 | `latency_ms` | `double` | >= 0 |

`CheckDecision` fields:

| Field # | Name | Proto type | Meaning |
|---:|---|---|---|
| 1 | `transition` | `Transition` enum | `NONE=1`, `TRIGGERED=2`, `RECOVERED=3` (`UNSPECIFIED=0` invalid response) |
| 2 | `consecutive_failures` | `int32` | New counter, >=0 |
| 3 | `alerting` | `bool` | True while failure state is firing |

**Rules algorithm (exact):** Each monitor has independent state `(consecutive_failures, alerting)`, initially `(0,false)`. Unhealthy increments count; exactly when count first reaches threshold and `alerting=false`, transition `TRIGGERED` and set `alerting=true`. Further failures remain `NONE` while alerting. Healthy resets count to 0; if previously alerting, transition `RECOVERED` and reset alerting; otherwise `NONE`. This state is **in-memory** (single Rules instance) and resets when restarted. Failure threshold changes do not occur in v1 because monitors cannot be edited.

**Errors:** `INVALID_ARGUMENT` for missing/invalid UUID, threshold outside 1–10, status outside 0 or 200–599, or negative latency. `UNAVAILABLE` if the Rules process is unreachable. Client deadline `2.0s`, then `DEADLINE_EXCEEDED`. Internal uncaught exceptions map to `INTERNAL`. This RPC has **no HTTP status code**.

**Side effects:** only in-memory rule-state mutation. **Rules Engine does NOT publish to RabbitMQ; Monitoring publishes upon returned transition**.

## 4. Incidents HTTP service — `localhost:8003`

### I1 — `GET /health`

- **Actor:** probe. **Input:** none. **Output:** `200`, `{"status":"ok","service":"incidents"}`. **Failure:** `500` unexpected error.

### I2 — `GET /incidents`

- **Actor:** viewer. **Purpose:** list incidents with optional filters.
- **Query fields:** `monitor_id` (optional UUID); `status` (optional enum `OPEN|ACKNOWLEDGED|RESOLVED`). Multiple filters combine with **AND**. No body or pagination. Additional unknown query fields are ignored (standard FastAPI behavior).
- **Success:** `200` array of `Incident` (§1.4); `[]` for no matches. Sort by `created_at` **descending** then `id` ascending.
- **Failure:** `422` malformed UUID or invalid status enum; `500` unexpected storage error.

```bash
curl -i 'http://localhost:8003/incidents?monitor_id=c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13&status=OPEN'
```

Example response: `[<Incident object from §1.4>]`; actual response is a JSON array of objects, not literal angle brackets.

### I3 — `GET /incidents/{incident_id}`

- **Actor:** viewer **and internal Alerts REST client**. **Purpose:** return authoritative persisted incident state.
- **Path input:** `incident_id` (UUID). No body/query.
- **Success:** `200` `Incident` (§1.4).
- **Failure:** `422` malformed UUID; `404 {"detail":"Incident not found"}` absent valid UUID.
- **Important:** Alerts calls `GET http://incidents:8000/incidents/{incident_id}` **after** consuming `incident.detected`/`incident.resolved`; no separate “internal details” route is necessary.

### I4 — `POST /incidents/{incident_id}/ack`

- **Actor:** operator. **Purpose:** acknowledge active incident. **Input:** UUID path; **no body/query**.
- **Success:** `200` full **updated `Incident`**. `OPEN → ACKNOWLEDGED`, update `updated_at`; repeating ACK on ACKNOWLEDGED returns `200` same state and **does not update `updated_at`**.
- **Failure:** `422` bad UUID; `404` unknown UUID; `409 {"detail":"Incident already resolved"}` if RESOLVED.
- **Messaging:** no RabbitMQ or SSE event on ACK in v1; SSE represents detect/resolve only.

```http
POST /incidents/2e27b8da-84ee-4c6d-b6cf-a05b9b688c90/ack HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{"id":"2e27b8da-84ee-4c6d-b6cf-a05b9b688c90","monitor_id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13","title":"HTTP monitor unavailable","severity":"critical","status":"ACKNOWLEDGED","created_at":"2026-11-17T10:00:20Z","updated_at":"2026-11-17T10:00:30Z"}
```

### I5 — `WebSocket /ws/incidents/{incident_id}`

- **Actor:** operator. **Purpose:** ephemeral comments shared by all clients connected to the **same** incident (including sender). **Path:** UUID `incident_id`. No auth, no query, no subprotocol, no persistence/replay.
- **Handshake:** only accept (`websocket.accept()`) for existing incidents. Invalid UUID or missing incident: close with WS code **1008**, do not create incident.
- **Client → server message:** one UTF-8 JSON text frame:

```json
{"type":"comment","author":"alice","text":"Investigating the outage"}
```

| Field | Type | Rules |
|---|---|---|
| `type` | literal string | Exactly `comment` |
| `author` | string | Trimmed, 1–40 chars |
| `text` | string | Trimmed, 1–500 chars |

No extra fields; malformed JSON, wrong `type`, missing/invalid/empty fields → **close 1008**. Binary frames are unsupported → close 1008. Client may send multiple valid comments while connected.

- **Server → clients message:** broadcast to **all** sockets in that incident room:

```json
{"type":"comment_added","incident_id":"2e27b8da-84ee-4c6d-b6cf-a05b9b688c90","author":"alice","text":"Investigating the outage","created_at":"2026-11-17T10:01:00Z"}
```

`created_at` generated by server, UTC. Comments are not stored, and different incident rooms must be isolated. Remove disconnected clients; if send to a stale socket fails, remove it without failing other broadcasts. When a client disconnects normally, no response event is required. In-memory rooms assume **one Incidents process** in v1.

### I6 — broker-driven incident lifecycle (no REST endpoint)

- On `rule.triggered`: create one `OPEN` incident for the monitor **if no active incident exists**, then publish `incident.detected`. Duplicate delivery = no new incident/event. The active set is `OPEN` **or** `ACKNOWLEDGED`. Title/severity are fixed as in §1.4.
- On `rule.recovered`: if active incident exists, mark it `RESOLVED`, update `updated_at`, then publish `incident.resolved`. If none, no-op. Duplicate delivery is a no-op.
- Store incidents in Postgres, independent tables owned by Incidents. Enforce at most one active incident per monitor, ideally a partial unique index. Store processed `event_id` for idempotency (a small `processed_events` table, in same transaction as incident mutation); outbox is intentionally omitted. A broker message is ACKed **after** successful processing.
- Ordering assumption: single Monitoring producer with per-monitor check locking, one Incidents consumer group, and ordering of events for a monitor. Durable exactly-once pub/sub, event reordering across replicas and outbox are **not part of v1**.

State machine:

```text
                    POST /ack
  rule.triggered      ┌───────────────┐
(no active incident)  ▼               ▼
                 OPEN ─────────→ ACKNOWLEDGED
                   │                    │
                   └─────────┬──────────┘
                       rule.recovered
                             ▼
                         RESOLVED
```

`RESOLVED` incidents remain in history. A **later new** trigger after recovery produces a **new** incident (new UUID) for that monitor.

## 5. Alerts HTTP and SSE service — `localhost:8004`

### A1 — `GET /health`

- **Actor:** probe. **Input:** none. **Output:** `200`, `{"status":"ok","service":"alerts"}`. **Failure:** `500` unexpected error.

### A2 — `GET /alerts/stream` (SSE)

- **Actor:** viewer. **Purpose:** push incident detect/resolve notifications to all currently connected clients; **server → client only**.
- **Input:** no path, query or body. Recommended request header `Accept: text/event-stream`. No `Last-Event-ID` replay, no filters, no cursor in v1.
- **Handshake success:** HTTP `200`, `Content-Type: text/event-stream; charset=utf-8` (prefix `text/event-stream` is mandatory), `Cache-Control: no-cache`, `X-Accel-Buffering: no`. The stream remains open until disconnect; sending `: connected\n\n` immediately is part of the v1 contract for deterministic readiness.
- **Events:** single-line JSON `data:` with exactly one `incident` object (same `Incident` shape as §1.4). Valid event names: `incident_detected` and `incident_resolved`.

```text
: connected

event: incident_detected
data: {"incident":{"id":"2e27b8da-84ee-4c6d-b6cf-a05b9b688c90","monitor_id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13","title":"HTTP monitor unavailable","severity":"critical","status":"OPEN","created_at":"2026-11-17T10:00:20Z","updated_at":"2026-11-17T10:00:20Z"}}

event: incident_resolved
data: {"incident":{"id":"2e27b8da-84ee-4c6d-b6cf-a05b9b688c90","monitor_id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13","title":"HTTP monitor unavailable","severity":"critical","status":"RESOLVED","created_at":"2026-11-17T10:00:20Z","updated_at":"2026-11-17T10:01:05Z"}}

```

- **Heartbeat:** on idle stream, send `: ping\n\n` every 15 seconds. Clients ignore SSE lines starting with `:`.
- **Delivery:** no replay/persistence. A new subscriber receives only *future* events. Each connection owns a bounded in-memory queue; a slow subscriber may be disconnected/dropped but must not block the producer or other clients. Remove subscriber state on disconnect. One Alerts replica only in v1.
- **Enrichment:** on consuming `incident.detected`/`incident.resolved` from RabbitMQ, Alerts performs **HTTP REST** `GET http://incidents:8000/incidents/{incident_id}`. After it succeeds, fan out `Incident` to SSE; ACK RabbitMQ only after successful fetch and publish-to-local queues. On REST failure do **not** generate invented incident data; retry/requeue according to your simple broker retry design.

```bash
curl -N -H 'Accept: text/event-stream' http://localhost:8004/alerts/stream
```

## 6. Fake target — test-only `localhost:8090`

**Fake target is a local test fixture, not a fifth domain microservice. Its four handlers are stubs (`...`) just like all others in this delivery.** Its `__test__` routes have no security; bind them to localhost only.

### F1 — `GET /health`

- **Actor:** Monitoring worker. **Input:** none. **Output:** actual configured HTTP status (200–599), JSON body `{"service":"fake-target","healthy":true|false}`, where healthy is `200<=status<300`. **Latency:** intentional delay (`delay_ms`) before responding; Monitoring may time out instead.
- Default: `HTTP 200 {"service":"fake-target","healthy":true}`.
- If mode is 503: `HTTP 503 {"service":"fake-target","healthy":false}`.

### F2 — `GET /__test__/state`

- **Actor:** test runner. **Input:** none. **Output:** always `200` `Mode`, e.g. `{"status_code":503,"delay_ms":0}` (even when `/health` is failing).

### F3 — `POST /__test__/mode`

- **Actor:** test runner. **Input:** JSON object with optional fields from `Mode` (§1.5); `{}` resets fields to defaults. **Output:** `200` updated `Mode`. **Failure:** `422` for invalid mode/extra fields.

```bash
curl -i -X POST http://localhost:8090/__test__/mode \
 -H 'Content-Type: application/json' \
 -d '{"status_code":503,"delay_ms":0}'
```

### F4 — `POST /__test__/reset`

- **Actor:** test runner. **Input:** no body. **Output:** `200 {"status_code":200,"delay_ms":0}`. Always resets the fake target to healthy default.

## 7. RabbitMQ — exact async event contracts

**Exchange:** durable topic `signalwatch.events`; JSON UTF-8 persistent messages; queues `signalwatch.incidents.rules` bound to `rule.*`, `signalwatch.alerts.incidents` bound to `incident.*`. Define exchange/queues idempotently on startup.

Envelope (EVERY event):

```json
{
  "event_id": "5ff33451-4746-4eb7-990b-15383ec924b9",
  "type": "RuleTriggered",
  "occurred_at": "2026-11-17T10:00:20Z",
  "data": {
    "monitor_id": "c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13",
    "severity": "critical"
  }
}
```

| Routing key | `type` | Exact `data` fields | Publisher | Consumer | When |
|---|---|---|---|---|---|
| `rule.triggered` | `RuleTriggered` | `monitor_id: UUID`, `severity: "critical"` | Monitoring | Incidents | gRPC result `TRIGGERED` |
| `rule.recovered` | `RuleRecovered` | `monitor_id: UUID` | Monitoring | Incidents | gRPC result `RECOVERED` |
| `incident.detected` | `IncidentDetected` | `incident_id: UUID` | Incidents | Alerts | Newly persisted OPEN incident |
| `incident.resolved` | `IncidentResolved` | `incident_id: UUID` | Incidents | Alerts | Persisted RESOLVED incident |

**Explicit samples** (envelope fields are mandatory even when abbreviated here):

```json
{"event_id":"5ff33451-4746-4eb7-990b-15383ec924b9","type":"RuleTriggered","occurred_at":"2026-11-17T10:00:20Z","data":{"monitor_id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13","severity":"critical"}}
{"event_id":"6ff33451-4746-4eb7-990b-15383ec924b9","type":"RuleRecovered","occurred_at":"2026-11-17T10:01:05Z","data":{"monitor_id":"c3cf9d18-0caa-4a83-ab9c-4a5fcd240e13"}}
{"event_id":"7ff33451-4746-4eb7-990b-15383ec924b9","type":"IncidentDetected","occurred_at":"2026-11-17T10:00:20Z","data":{"incident_id":"2e27b8da-84ee-4c6d-b6cf-a05b9b688c90"}}
{"event_id":"8ff33451-4746-4eb7-990b-15383ec924b9","type":"IncidentResolved","occurred_at":"2026-11-17T10:01:05Z","data":{"incident_id":"2e27b8da-84ee-4c6d-b6cf-a05b9b688c90"}}
```

Each publisher generates a fresh `event_id` UUID4 and UTC timestamp. RabbitMQ is **at-least-once**: consumer must tolerate redelivery; Incidents stores processed `event_id` in Postgres. ACK only after work completed; on failure NACK/requeue (avoid tight hot loops). No schema-registry, dead-letter topology, exactly-once cross-service transaction, or outbox in v1. The event definitions in §7 are normative; the `.proto` contract is in `contracts/rules.proto`.

## 8. Required complete flow — acceptance scenario

1. `POST /__test__/reset` ⇒ fake target 200.
2. `POST /monitors` with `{name:"Payments API",url:"http://fake-target:8090/health",interval_seconds:3600,failure_threshold:3}` ⇒ `201` and UUID.
3. Connect SSE **before events**; first SSE frame is `: connected`.
4. `POST /__test__/mode` set target 503 ⇒ `200` Mode.
5. `POST /monitors/{id}/check` three times ⇒ transitions `NONE`, `NONE`, `TRIGGERED`; status_code 503.
6. Monitoring waits for gRPC every time; publishes **one** `rule.triggered` event.
7. Incidents consumes it; `GET /incidents?monitor_id={id}&status=OPEN` eventually contains **exactly one** incident; Incidents publishes one `incident.detected`.
8. Alerts REST GETs that incident and sends `event: incident_detected` to existing SSE connection.
9. Open two WebSockets to `/ws/incidents/{incident_id}`. Send one valid comment from A; B receives `comment_added` for same incident.
10. `POST /incidents/{incident_id}/ack` ⇒ `200` ACKNOWLEDGED; ACK again stays ACKNOWLEDGED; no new event.
11. Set target 200; one manual `/check` ⇒ `RECOVERED`, count0; one `rule.recovered` published.
12. Incident becomes `RESOLVED` (same ID) and Alerts emits `incident_resolved`; ACK on resolved ⇒ `409`.
13. Delete monitor ⇒ `204`; GET after delete ⇒ `404`; fake target reset ⇒ healthy.

**Acceptance procedure:** run the 13 steps above in order. The fake-target state is process-global, so test runs must be sequential. No test runner, scripts, or backend implementation are included in this contract-and-stubs delivery.

## 9. Out of scope / known limitations (explicit, not missing specs)

- No production auth or RBAC; no exposing these ports publicly. Arbitrary user-controlled target URLs can cause **SSRF**; use trusted localhost/Docker targets only until URL/IP allowlisting is added.
- No editing/updating monitors, custom schedules, check history, thresholds per severity, rules CRUD, email/SMS/push notification, pagination, frontend, or Prometheus metrics.
- One process/replica each for Rules, Incidents WS, Alerts SSE; **no distributed in-memory state sharing**. Scaling and reconnect/resume are next-phase features.
- In-memory Rules state resets after process restart; SSE does not replay; WS comments are ephemeral.
- No transactional outbox: crash after Postgres commit but before RabbitMQ publish can lose an event. This risk is acknowledged for the one-week PoC; production requires outbox/reconciliation.
- Health HTTP routes indicate *liveness*, not end-to-end dependency readiness.

**Definition of done:** all documented HTTP requests return the exact specified status/schema, the gRPC decision sequence is correct, both RabbitMQ flows run, SSE delivers detection and recovery, and WebSocket comments reach all clients of a single incident. The §8 scenario passes end-to-end. No additional features are needed to consider backend v1 complete.

## 10. Stub inventory and implementation boundary

All **17 HTTP route handlers**, **1 WebSocket handler**, and **1 gRPC handler** are present as explicit functions ending in `...` in `services/*/main.py` or `services/rules/grpc_server.py`. `services/*/service.py` and `services/rules/engine.py` contain additional domain-function stubs. The Pydantic models and `.proto` declarations are complete contracts, **not business logic**. No handler is expected to work until implemented. `compose.yaml` defines only process infrastructure; the Rules gRPC server must be started by your Rules service implementation.

**Suggested startup after implementing handlers and service startup:** `docker compose up --build`. The four FastAPI liveness endpoints are also stubs and therefore will not return their expected schemas until implemented.
