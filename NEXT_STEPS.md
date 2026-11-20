# Next steps — Fake Target (FAK)

**Implementation owner: ChatGPT.** These four tasks are intentionally excluded from the repository owner's open GitHub Issues. They are planned for implementation by ChatGPT, not by the repository owner.

**Status:** Not yet implemented. This document preserves the original English task definitions and acceptance criteria. No Fake Target code is changed by this move.

---

# FAK-01 | GET /health — Configurable HTTP test target

**Implementation owner: ChatGPT.** Status: pending.

Former tracking issue: [#20](https://github.com/AlexandruAprodu/ping--patrol/issues/20)

## Objective
Fake Target simulates a healthy HTTP URL, an HTTP error, or a slow response so Monitoring can be tested without external dependencies.

## Input
```http
GET /health
```
No body/query parameters/JWT. Behavior is controlled by `Mode` configured through #22: `status_code` integer 200–599 (excluding 204, 205, 304), `delay_ms` integer 0–10000. Default `{200,0}`.

## Expected output
If Mode is `{"status_code":503,"delay_ms":1500}`: after approximately 1500ms, return **HTTP 503** with:
```json
{"service":"fake-target","healthy":false}
```
If Mode is `{"status_code":201,"delay_ms":0}`: **HTTP 201** and `healthy:true`. Do not always return HTTP 200: the actual HTTP status must match the configured one.

## What to implement
1. Read a snapshot of the current process-local Mode.
2. Await `delay_ms` asynchronously (without `time.sleep` or blocking the event loop).
3. Return a `JSONResponse` with the configured `status_code` and `healthy = 200 <= status_code < 300`.
4. Do not modify Mode or query the Monitor/Users database.

## Acceptance criteria
- [ ] Default → HTTP 200, `healthy:true`.
- [ ] Mode 503 → **HTTP 503**, `healthy:false`.
- [ ] Mode 201 → HTTP 201, `healthy:true`.
- [ ] The configured delay is applied without blocking other requests.
- [ ] After reset #23, the next GET returns HTTP 200.

**Files:** `services/fake_target/main.py`, `schemas.py`. **Local test fixture only; do not expose publicly.**

---

# FAK-02 | GET /__test__/state — Read target mode

**Implementation owner: ChatGPT.** Status: pending.

Former tracking issue: [#21](https://github.com/AlexandruAprodu/ping--patrol/issues/21)

## Objective
The test runner can inspect Fake Target's current configuration even when `/health` is simulating an error.

## Input
```http
GET /__test__/state
```
No body/query parameters/JWT; local access only.

## Expected output
**HTTP 200**:
```json
{"status_code":503,"delay_ms":1500}
```
If no configuration has been applied, the response is `{"status_code":200,"delay_ms":0}`.

## What to implement
1. Read the process-global `Mode` object (set by #22 or reset by #23).
2. Return the current values without simulated delay or state mutation.
3. Preserve the exact `Mode` schema defined in `services/fake_target/schemas.py`.

## Acceptance criteria
- [ ] Initial state → 200, `{"status_code":200,"delay_ms":0}`.
- [ ] After setting 503/1500 → 200 with those values, **without waiting 1500ms**.
- [ ] Repeating GET does not change the state.
- [ ] Even when `GET /health` returns 503, `GET /__test__/state` returns 200.

**File:** `services/fake_target/main.py`. **Local testing endpoint only.**

---

# FAK-03 | POST /__test__/mode — Configure test failure

**Implementation owner: ChatGPT.** Status: pending.

Former tracking issue: [#22](https://github.com/AlexandruAprodu/ping--patrol/issues/22)

## Objective
The test runner configures **all** Fake Target behavior in a single request; Monitoring can then observe the real status code and delay from `GET /health`.

## Input
```http
POST /__test__/mode
Content-Type: application/json
```
```json
{"status_code":503,"delay_ms":1500}
```
Optional fields: `status_code` integer 200–599, excluding 204/205/304; `delay_ms` integer 0–10000. No extra fields; booleans are not valid integers. `{}` means `status_code=200, delay_ms=0`.

## Expected output
**HTTP 200** with the **entire** new state:
```json
{"status_code":503,"delay_ms":1500}
```
Afterward, `GET /health` returns **HTTP 503 after the delay**, and `GET /__test__/state` displays that Mode.

## What to implement
1. Parse the body using the Pydantic `Mode` in `schemas.py`.
2. Validate everything **before** changing state; on error, preserve the previous Mode.
3. Atomically replace process state with the new `Mode`; omitted fields take defaults of 200/0 instead of retaining old values.
4. Do not actually run an HTTP check here.

## Acceptance criteria
- [ ] 503/1500 → 200 with the same values; the next `GET /health` uses the code and delay.
- [ ] `{}` → 200, `{"status_code":200,"delay_ms":0}`.
- [ ] Invalid values (`"503"`, `true`, `204`, `delay_ms:-1`, extra field) → 422 and unchanged state.
- [ ] Updating state does not wait for the configured delay.

**File:** `services/fake_target/main.py`. **Local test fixture only.**

---

# FAK-04 | POST /__test__/reset — Restore default mode

**Implementation owner: ChatGPT.** Status: pending.

Former tracking issue: [#23](https://github.com/AlexandruAprodu/ping--patrol/issues/23)

## Objective
Reset Fake Target to a healthy response with no delay, regardless of which error was simulated.

## Input
```http
POST /__test__/reset
```
No body/query parameters/JWT. Local test action.

## Expected output
**HTTP 200**, exactly:
```json
{"status_code":200,"delay_ms":0}
```

## What to implement
1. Immediately replace the process's `Mode` with `Mode(status_code=200, delay_ms=0)`.
2. Return the new `Mode` without waiting for the previous `delay_ms`.
3. Make the operation idempotent: repeated resets produce the same state.

## Acceptance criteria
- [ ] After Mode 503/10000, reset immediately returns 200/0.
- [ ] `GET /__test__/state` confirms 200/0.
- [ ] `GET /health` returns HTTP 200 with `{"service":"fake-target","healthy":true}`.
- [ ] Two consecutive resets have the same result.

**File:** `services/fake_target/main.py`. **Test-only; not publicly exposed.**
