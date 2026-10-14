# PROTOCOL.md — Reverse-Engineering the Urja Meter Ops Portal

> **Author:** Flock Energy Take-Home Engineering Submission  
> **Target System:** Urja Meter Ops Internal Portal (`https://urja-ops.flockenergy.tech`)  
> **Scope:** Full protocol dissection, authentication mechanics, hidden endpoints, cryptographic signing schemes, and data quirks.

---

## 1. Executive Summary

The "Urja Meter Ops" internal utility portal is an operational dashboard utilized by field technicians and grid operators to query smart electricity meters across distribution networks in the Jaipur region.

Although presented to end users as a human-facing web interface with "no API", reverse-engineering of the client bundle revealed that the portal is a **SvelteKit single-page application (SPA)** backed by RESTful JSON endpoints. 

Rather than relying on brittle HTML DOM scraping or headless browser emulation (Puppeteer/Playwright), our modern API service communicates directly with the portal's internal REST protocol, including an authenticated cryptographic HMAC bulk export pipeline.

---

## 2. Authentication & Session Architecture

### 2.1 Better-Auth Framework & Cookie Semantics
The portal delegates user identity and session management to **Better Auth**. Upon successful login, the portal issues a session cookie:
- **Cookie Name:** `__Secure-better-auth.session_token`
- **Security Flags:** `Secure; HttpOnly; SameSite=Lax; Path=/`
- **Lifetime:** `Max-Age=3600` (1 hour)

All subsequent requests to internal `/portal/*` endpoints require this cookie in the `Cookie` header.

### 2.2 SvelteKit CSRF Protection (The 403 Gotcha)
When attempting standard programmatic `POST /login` with `{"email": "operator@urja.local", "password": "urja-ops-2026"}`, the server immediately responds with:
```http
HTTP/1.1 403 Forbidden
Content-Type: text/plain

Cross-site POST form submissions are forbidden
```

#### Why this happens:
SvelteKit contains built-in cross-site request forgery protection (`csrf.check_origin`). When handling non-GET requests with form content types, SvelteKit compares the request's `Origin` and `Referer` headers against the host's actual origin. If these headers are missing (standard in CLI `curl` or basic HTTP clients) or mismatch, the request is unconditionally rejected.

#### How to bypass cleanly:
Every outbound HTTP request from our API client strictly provides browser headers:
```http
POST /login HTTP/1.1
Host: urja-ops.flockenergy.tech
Origin: https://urja-ops.flockenergy.tech
Referer: https://urja-ops.flockenergy.tech/login
Content-Type: application/x-www-form-urlencoded

email=operator%40urja.local&password=urja-ops-2026
```

#### Login Response:
```json
{
  "type": "redirect",
  "status": 303,
  "location": "/meters"
}
```
Along with the `Set-Cookie: __Secure-better-auth.session_token=...` header.

---

## 3. Discovered Endpoints & Protocol Specifications

Inspection of the compiled SvelteKit JavaScript bundles (`app.03ZTmlg3.js`, node `4.2Bgc2kUI.js`, node `5.C4dYcCRt.js`, node `6.l777LXKL.js`) identified the following endpoints:

| Endpoint | Method | Auth Required | Purpose |
|---|---|---|---|
| `/login` | `POST` | Public | Authenticates credentials and sets session cookie |
| `/portal/meters/search?q={query}&page={page}` | `GET` | Session Cookie | Paginated basic meter directory search |
| `/portal/dts?page={page}` | `GET` | Session Cookie | Paginated Distribution Transformers |
| `/portal/keys` | `GET` | Session Cookie | Retrieves cryptographic export signing secret |
| `/portal/export?page={page}` | `GET` | Session + HMAC Header | Bulk cryptographic meter export with full hierarchy |
| `/portal/meters/{meterId}/energy` | `GET` | Session Cookie | 7-day half-hourly interval energy telemetry (337 points) |
| `/portal/meters/{meterId}/geo` | `GET` | Session Cookie | Physical GPS coordinates (`latitude`, `longitude`) |
| `/meters/{meterId}/__data.json` | `GET` | Session Cookie | SvelteKit server load bundle |

---

## 4. The Bulk Export Path: Cryptographic HMAC Signature

While the portal UI paginates meters by 20 on `/portal/meters/search`, clicking the "Export all meters" button on the Transformers page initiates a bulk download. Reverse-engineering `4.2Bgc2kUI.js` revealed a custom HMAC-SHA256 request signing mechanism.

### 4.1 Signing Key Acquisition
Before calling `/portal/export`, the client requests the active signing secret:
```http
GET /portal/keys HTTP/1.1
Cookie: __Secure-better-auth.session_token=<SESSION_TOKEN>
```
**Response:**
```json
{
  "data": {
    "signingSecret": "I3dZPPf5CgTp7JyGNMI8i6z8LFR7TmSR"
  }
}
```

### 4.2 Signature Construction Algorithm
The client signs the request using the algorithm discovered in the minified bundle:

```javascript
// Extracted from 4.2Bgc2kUI.js:
async function C(method, path, queryString, secret) {
  let timestamp = String(Math.floor(Date.now() / 1000));
  let message = [method, path, queryString, timestamp].join("\n");
  let key = await crypto.subtle.importKey(
    "raw", 
    new TextEncoder().encode(secret), 
    { name: "HMAC", hash: "SHA-256" }, 
    false, 
    ["sign"]
  );
  let signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return {
    timestamp: timestamp,
    signature: [...new Uint8Array(signature)].map(e => e.toString(16).padStart(2, "0")).join("")
  };
}
```

In our Python client (`src/client/urja_client.py`), this is implemented as:
```python
def generate_export_signature(method: str, path: str, query: str, secret: str) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    message = f"{method}\n{path}\n{query}\n{timestamp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return timestamp, sig
```

### 4.3 Export Request Headers
```http
GET /portal/export?page=1 HTTP/1.1
Host: urja-ops.flockenergy.tech
Cookie: __Secure-better-auth.session_token=<SESSION_TOKEN>
x-timestamp: 1776149880
x-signature: 8f42d4a13e2b9c7d41f0a5... (64 hex characters)
```

**Payoff:** A single call to `/portal/export?page=1` returns **all 403 meters** with complete geographic coordinates, hardware builds, and 7-tier hierarchy objects in under 350ms, eliminating the need to execute 21 sequential paginated scrapes!

---

## 5. Telemetry & Energy Readings Schema

Calling `GET /portal/meters/{meterId}/energy` returns a 7-day rolling window of half-hourly load profile captures.
- **Total intervals:** Exactly 337 readings ($7\text{ days} \times 48\text{ intervals/day} + 1\text{ boundary point}$).
- **Interval structure:**
  ```json
  {
    "timestamp": "23/06/2026 23:30",
    "kwh": "48438.74",
    "kvah": "52313.84",
    "voltR": "226"
  }
  ```
- **Quirks & Discoveries:**
  - `timestamp` is formatted as non-ISO Indian standard: `DD/MM/YYYY HH:MM`.
  - Numerical telemetry fields (`kwh`, `kvah`, `voltR`) are serialized as strings rather than floats/integers.
  - Three-phase meters report only `voltR` in this portal version; `voltY` and `voltB` are omitted upstream.
  - Sub-nominal voltage events ($V < 200\text{V}$) occur periodically during peak load periods, which our service flags as voltage dips.

---

## 6. Data Anomalies & Inconsistencies

A systematic audit across all 403 meters revealed real-world data corruption in the upstream utility database:

### 6.1 Incomplete Hierarchy Trees
14 meters have missing administrative or network nodes:
- **Missing `circle`:** 11 meters (e.g. `J100011` on `DT-012`, `J100074` on `DT-035`, `J100097` on `DT-018`).
- **Missing `feeder`:** 8 meters (e.g. `J100044` on `DT-005`, `J100078` on `DT-039`, `J100134` on `DT-015`).
- **Missing `substation`:** 3 meters (e.g. `J100153` on `DT-034`, `J100228` on `DT-029`, `J100302` on `DT-023`).

### 6.2 Topological Self-Healing
Because distribution networks are physical trees, all meters connected to a specific Distribution Transformer (DT) share the exact same upstream path:
$$\text{Meter} \rightarrow \text{DT} \rightarrow \text{Feeder} \rightarrow \text{Substation} \rightarrow \text{Sub-Division} \rightarrow \text{Division} \rightarrow \text{Circle} \rightarrow \text{Zone}$$

Our service scans all 403 meters during ingestion, extracts complete templates for all 40 DTs (which have at least 8 complete peer meters each), and automatically repairs all 14 broken records, exposing clean, complete hierarchies to downstream consumers.
