# REFLECTION.md — Engineering Reflections & Architectural Critique

> **Author:** Flock Energy Take-Home Engineering Submission ~ Debershi Mitra 
> **Topic:** Post-implementation retrospective on reverse-engineering the Urja Meter Ops portal and building the modern API platform.

---

### 1. What assumptions did you make?

1. **Topology Stability:** We assumed the electrical network topology (Zone $\rightarrow$ Circle $\rightarrow$ Division $\rightarrow$ Sub-Division $\rightarrow$ Substation $\rightarrow$ Feeder $\rightarrow$ DT) is structurally static over operational timeframes (hours to days). Physical transformers and 11kV lines are rarely re-routed in real-time, justifying our in-memory 1-hour TTL caching strategy.
2. **Telemetry Scope:** The 337 energy intervals represent a trailing 7-day rolling window of half-hourly load profiles ($7 \times 48 = 336 + 1$ boundary reading). We assumed the portal does not support ad-hoc custom historical date-range querying beyond this 7-day capture.
3. **DT Exclusivity for Hierarchy Imputation:** We assumed each Distribution Transformer (DT) maps deterministically to a single Feeder, Substation, Division, Circle, and Zone. This physical tree assumption held true across all 40 DTs, enabling our self-healing algorithm to achieve 100% repair accuracy for all 14 broken meter records.
4. **Signing Key Freshness:** We assumed the cryptographic HMAC signing secret exposed by `/portal/keys` is session-scoped or system-wide and can be cached until the session expires or a 403 occurs.

---

### 2. Which part was the most difficult, and how did you get unstuck?

The most difficult hurdle was encountering the initial `403 Cross-site POST form submissions are forbidden` when submitting credentials to the `/login` endpoint.

At first glance, the HTML rendered a standard `<form method="POST">` with `email` and `password` inputs, yet standard HTTP client requests (`requests.post` or `curl`) were immediately rejected. 

To get unstuck, we stopped treating the application as a black box and dug directly into SvelteKit's client-side runtime bundles (`start.Dtb6sIWb.js` and `app.03ZTmlg3.js`). We traced SvelteKit’s native CSRF mitigation layer, which asserts that any non-GET form submission must carry explicit `Origin` and `Referer` headers matching the host origin. Emulating these exact browser headers in our HTTP client immediately unblocked authentication and granted the `__Secure-better-auth.session_token` cookie.

A second challenge was extracting the HMAC signing scheme for `/portal/export`. Minified chunk `4.2Bgc2kUI.js` obscured the signature formatting. By analyzing the Web Crypto API calls (`crypto.subtle.sign("HMAC", ...)`), we reconstructed the exact multi-line string structure (`"GET\n/portal/export\npage=1\n" + timestamp`) and hex-encoding format.

---

### 3. If you had another day, what would you improve?

1. **Persistent Spatial Database with PostGIS:** Currently, proximity queries use an in-memory Haversine calculation. While this executes in $<0.1\text{ms}$ for 403 meters, it scales at $O(N)$. With an additional day, we would introduce PostgreSQL with PostGIS and GiST spatial indexes (`ST_DWithin`, `ST_Distance`) to support sub-millisecond radius and polygon bounding queries at millions of meters scale.
2. **Streaming WebSocket Telemetry & Anomaly Alerts:** We would implement a WebSocket pipeline (`/ws/telemetry`) streaming real-time voltage and load warnings to the frontend when voltage drops below 200V or power factor drops below 0.80.
3. **Asynchronous Background Synchronization with Celery/Arq:** Instead of refreshing the cache upon client request (even with SWR), we would deploy a dedicated background worker to continuously poll the portal, maintain an append-only time-series database (TimescaleDB), and push incremental telemetry deltas.

---

### 4. What mistake did you make while solving this (there's always one)?

Early in the investigation, before inspecting the Transformers bundle, we assumed that extracting the entire 403-meter dataset required writing a crawler to iterate through all 21 pages of `/portal/meters/search?page=N`, followed by 403 concurrent `GET /portal/meters/{id}/geo` calls to fetch coordinates.

This was a classic trap: treating the system as a shallow scraper rather than looking for bulk pathways. It would have generated over 420 upstream HTTP requests, risked rate-limiting (HTTP 429), and resulted in significant latency.

We caught this mistake when auditing the Transformers page bundle and noticed the `fetch('/portal/export')` call. Pivoting to reverse-engineer the HMAC signature algorithm allowed us to replace hundreds of requests with a single signed bulk call that returns all 403 meters with full hierarchies and geo coordinates in 300ms.

---

### 5. If you were reviewing your own submission, what would you criticise?

1. **In-Memory State vs. Distributed Readiness:** The service maintains the hydrated meter index and hierarchy graph in memory within the single FastAPI worker process. If deployed across multiple horizontal replicas (e.g. 4 Uvicorn workers behind a Kubernetes Ingress), each worker maintains its own independent cache and re-authenticates separately against the upstream portal. A production-grade multi-worker architecture should store the session token and shared index in Redis.
2. **Fixed Radius Search Limit:** The spatial search assumes meters reside within a relatively contiguous geographical boundary (Jaipur, Rajasthan). If a user queries coordinates far outside this cluster with a small radius, the response is empty. The UI could provide auto-centering or bounds-snapping to the nearest cluster.
3. **Mocking Upstream in CI:** The integration test suite (`tests/test_api.py`) relies on live network reachability to the Urja portal during startup hydration. While this guarantees 100% end-to-end fidelity during evaluation, a strict isolated CI/CD pipeline should record and replay upstream responses using VCR.py or WireMock to prevent test flakiness if the external demo server experiences downtime.
