# Elastic APM RUM Demo — Multi-Endpoint Lab

A standalone browser tool for generating synthetic Real User Monitoring (RUM) events and sending them to one or more Elastic APM servers simultaneously. Built for Elastic Support Engineering to demonstrate and validate RUM ingest across ECH, local Fleet-managed APM, and other APM deployments.

---

## What it does

- Sends RUM transactions, spans, and errors directly to the APM intake API (`/intake/v2/events`) using the NDJSON format
- Fan-out to up to 3 APM endpoints in parallel — each action fires independently to all configured endpoints at once
- Routes all requests through a local CORS proxy (`rum-proxy.py`) so browser CORS restrictions do not block the calls
- No external library dependency — the Elastic APM RUM JS SDK is not used; events are built and POSTed natively
- First-run setup overlay prompts you to enter your own APM endpoint URLs — no personal URLs are pre-filled
- Endpoint config is persisted in `localStorage` and survives page refreshes
- Live proxy status badge: green when the proxy is reachable, red with the start command when it is not

---

## Requirements

- Python 3 (ships with macOS)
- An Elastic APM server reachable from your machine (ECH APM, local Fleet APM, or any APM-compatible endpoint)
- A modern browser (Chrome or Firefox)

No npm, no Node, no Docker required for the tool itself.

---

## Setup — start from download

### 1. Download the files

Download or clone this repository:

```bash
git clone https://github.com/rahulranjan22/rum-demo.git
cd rum-demo
```

Files included:

| File | Purpose |
|---|---|
| `rum-demo.html` | The browser UI |
| `rum-proxy.py` | CORS proxy (used internally by start.py) |
| `start.py` | Single launcher — starts both servers and opens the browser |

### 2. Run the launcher

```bash
python3 start.py
```

That's it. `start.py` starts both required servers and opens `http://localhost:9210/rum-demo.html` in your browser automatically:

```
  Elastic APM RUM Demo
  ─────────────────────────────────────
  UI    →  http://localhost:9210/rum-demo.html
  Proxy →  http://localhost:9211
  
  Opening browser...
  Press Ctrl+C to stop.
```

Press **Ctrl+C** in the terminal to stop both servers.

> **Why two servers?** The HTML page must be served over `http://` (not `file://`) so the browser sends a proper origin header. The CORS proxy forwards APM intake calls server-side, bypassing browser CORS restrictions. `start.py` runs both in background threads so you only need one terminal.

### (Optional) Run servers individually

If you want separate control:

```bash
# Terminal 1 — CORS proxy
python3 rum-proxy.py

# Terminal 2 — HTTP server
python3 -m http.server 9210
```

Then open `http://localhost:9210/rum-demo.html`.

---

## First-run setup

On first load (or after clicking **Reset config**), a setup overlay appears.

1. **Endpoint 1** (required) — enter your APM server URL, e.g. `https://<cluster-id>.apm.us-central1.gcp.cloud.es.io`
2. Optionally click **+ Add another endpoint** to add a second and third target (up to 3)
3. For each endpoint you can optionally set:
   - **Kibana URL** — used to generate quick-links to APM Service Inventory and Traces
   - **Name** — displayed in the log and endpoint selector
   - **Auth** — leave blank for RUM (RUM intake does not require a secret token or API key)
4. Click **Save & start**

> The proxy status at the bottom of the setup box shows whether the proxy is reachable before you save.

Config is saved to `localStorage` under the key `rum_endpoints_v2`.

---

## The UI at a glance

```
┌─────────────────────────────────────────────────┐
│  Header: Send to [EP1] [EP2] [EP3]  │ EP dots   │
│  Auto-simulate toggle                            │
├──────────────────────┬──────────────────────────┤
│  Product catalog     │  Cart                    │
│  (click to add)      │  [Checkout]              │
├──────────────────────┴──────────────────────────┤
│  Actions (click to fire one event)              │
├─────────────────────────────────────────────────┤
│  Standalone-only (no demo app required)         │
├──────────────────────┬──────────────────────────┤
│  User Journeys       │  Burst mode              │
├──────────────────────┴──────────────────────────┤
│  Custom event builder                           │
├─────────────────────────────────────────────────┤
│  Metrics: TX | Spans | Errors | Total POSTs     │
├─────────────────────────────────────────────────┤
│  Activity log                                   │
└─────────────────────────────────────────────────┘
```

**Endpoint selector (top bar):** checkboxes for each configured endpoint. Uncheck one to exclude it from the next event — the others still receive it. Re-check to include it again.

**EP status dots:** coloured circles next to each endpoint name. Green = last POST returned 202. Red = last POST failed.

**Proxy status badge (footer):** live check — green tick when proxy is running, red warning with start command when it is down.

---

## Actions

Every action fires a RUM transaction with realistic child spans to all checked endpoints simultaneously.

### Standard actions

| Button | Transaction name | What it simulates |
|---|---|---|
| Search | `search:"<term>"` | Product search with API + cache + render spans |
| Page Load | `/` | Homepage load with resource, fetch, and FCP spans |
| Filter | `filter:category` | Category filter with API + render spans |
| Login | `POST /login` | Auth request + session create |
| Logout | `DELETE /session` | Session teardown |
| Recommendations | `GET /recommendations` | Recommendation fetch (optionally calls demo app if integration is on) |
| Slow TX (2s) | `slow-operation` | 2 second blocking span — useful for latency testing |
| Cache Hit | `GET /products/cached` | Fast cache-hit path, sub-10ms span |
| API Retry | `POST /orders` | Simulated retry with 3 attempt spans |
| JS Error | `/ (page-load)` | Transaction + captured JavaScript error |
| Timeout Error | `GET /api/timeout` | Network timeout span + captured error |
| Checkout | `POST /checkout` | Cart validation + payment + confirmation spans |

### Standalone-only actions (no OTel demo app needed)

| Button | Transaction name | What it simulates |
|---|---|---|
| Dashboard load | `dashboard:/analytics` | BI dashboard with 5 chart-load spans |
| Form submit | `POST /contact` | Multi-field form validation + submit |
| WebSocket session | `ws://stream/live` | Connect + 15 messages + disconnect |
| Infinite scroll | `GET /products?page=2` | Intersection observer + fetch + DOM append |

### User journeys (multi-step)

Each journey fires several correlated transactions that share the same `traceId`, so they appear linked in the Elastic APM Traces view.

| Journey | Steps |
|---|---|
| New visitor | Homepage → Search → Product detail |
| Checkout | Homepage → Search → Add to cart → Checkout |
| Search abandoned | Homepage → Search → Filter → (exit) |
| Power user | 5 steps: Homepage, Search, Filter, Product, Checkout |
| Mobile heavy | Page load → Recommendations → Slow TX → Timeout |
| API heavy | API Retry → Cache Hit → Recommendations → Search |

### Burst mode

Fires N events in quick succession, all sharing one `traceId`. Use the slider (5–100) and click **Send burst**.

Useful for:
- Load-testing APM ingest throughput
- Generating enough volume to see patterns in APM

### Custom event builder

Type any transaction name and type, then click **Send**. The event is sent to all checked endpoints.

---

## Selecting endpoints

- **All endpoints checked:** every action is sent to all of them in parallel. The activity log shows one result line per endpoint.
- **One endpoint checked:** only that endpoint receives the event. Use this to compare APM servers side by side.
- **Mix:** check any combination. The tool respects whichever boxes are ticked at the moment you click an action.

### Editing endpoints after setup

Click **Edit endpoints** (gear icon, top-right) to open the config panel. You can change URL, name, Kibana link, proxy toggle, and auth for any slot. Click **Apply** to save.

Click **Reset config** to wipe all endpoints and show the first-run setup overlay again.

---

## Where to check results in Kibana

After firing events, open Kibana for the target deployment.

### APM Service Inventory

```
Kibana → Observability → APM → Services
```

Look for the service named **`rum-ecommerce-demo`**. If the Kibana URL is saved in the endpoint config, the quick-link in the **Kibana links** section of the tool opens this directly.

### Transactions

```
APM → Services → rum-ecommerce-demo → Transactions
```

You will see transaction names matching the actions you fired (e.g. `search:"telescope"`, `POST /checkout`).

### Traces (distributed trace view)

```
APM → Traces
```

For journey and burst events, multiple transactions share a `traceId`. Open the waterfall to see correlated spans across steps.

### Errors

```
APM → Services → rum-ecommerce-demo → Errors
```

**JS Error** and **Timeout Error** actions both capture an error — it appears here with a stack trace.

### What a 202 means

The APM intake API returns `202 Accepted` when it has queued the event for processing. It does not mean the event is immediately visible in Kibana — allow a few seconds for indexing.

---

## Proxy — how it works

Browser JavaScript cannot call APM servers directly because:
1. The `file://` origin (when opening HTML from disk) sends a `null` origin, which APM servers reject
2. Even from `http://localhost`, APM servers return a CORS preflight error unless RUM is explicitly enabled in the Fleet agent policy

`rum-proxy.py` solves this by acting as a local relay:

```
Browser ──POST──▶ localhost:9211/intake/v2/events
                  (X-Target-Url: https://your-apm-server.cloud.es.io)
                        │
                        ▼
                  proxy forwards server-to-server (no CORS)
                        │
                        ▼
                  APM server ──202──▶ proxy ──202 + CORS headers──▶ browser
```

Each request from the browser includes an `X-Target-Url` header specifying the real APM server. The proxy reads this header, forwards the request, adds CORS response headers, and returns the HTTP status code. No hardcoded targets — fully driven by the HTML config.

---

## Running with the OTel demo app (optional)

If the OpenTelemetry demo app is running on `localhost:8080`, enable **Demo app integration** in the header toggle. When on, the **Recommendations** action also calls the demo's `/api/recommendations` endpoint with a `traceparent` W3C header, creating a real distributed trace from the browser RUM event through to the backend services.

With integration off (default), all actions are fully synthetic and require no backend.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Red "Proxy offline" badge | Proxy not running | Run `python3 start.py` (or `python3 rum-proxy.py` separately) |
| All endpoints show red dots | Proxy running but APM server unreachable | Check APM URL in config panel |
| 400 from local APM | RUM not enabled in Fleet agent policy | Use ECH or another APM endpoint, or enable RUM in Fleet |
| Setup overlay reappears | `localStorage` was cleared | Re-enter your endpoints in setup |
| Events sent but nothing in Kibana | Indexing lag | Wait 10–15 seconds and refresh |

---

## File reference

| File | Description |
|---|---|
| `start.py` | Single launcher — runs HTTP server + CORS proxy, opens browser |
| `rum-demo.html` | Self-contained browser UI — all JS inline, no build step |
| `rum-proxy.py` | Python 3 CORS proxy, generic `X-Target-Url` routing |

---

Built by **Rahul Ranjan** · Elastic Support · OTel Ingest Lab
