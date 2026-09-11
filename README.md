# Elastic APM RUM Demo

A standalone browser tool for generating synthetic RUM (Real User Monitoring) events and sending them to one or more Elastic APM servers at the same time. Built for Elastic Support to demonstrate and validate RUM ingest across ECH, local APM, and other deployments.

## What it does

* Sends RUM transactions, spans, and errors directly to the APM intake API using NDJSON format
* Fan-out to up to 3 APM endpoints in parallel with one click
* Routes all requests through a local CORS proxy so browser restrictions do not block the calls
* Rotates 8 realistic browser/OS user-agents and 15 geo IPs per event so Kibana shows real Visitor Breakdown and location data
* First-run setup overlay prompts you to enter your own APM URLs — no personal endpoints pre-filled
* Endpoint config persists in localStorage across page refreshes
* Live proxy status badge in the footer shows green when the proxy is running and red with the start command when it is not
* Session stats card shows a live timer and running TX/span/error/POST counts

## Layout

The UI uses a two-column layout:

* Left column — Product Catalog and full Actions panel (standard, standalone, burst, custom event)
* Right sidebar — Session Stats with live timer, Cart, User Journeys, and Kibana quick-links
* Below the grid — dark-themed RUM Event Log and Integration reference table

## Requirements

* Python 3 (ships with macOS)
* An Elastic APM server reachable from your machine (ECH APM, local Fleet APM, or any compatible endpoint)
* Chrome or Firefox

No npm, no Node, no Docker needed.

## Setup

Clone the repo:

```bash
git clone https://github.com/rahulranjan22/rum-demo.git
cd rum-demo
```

Start everything with one command:

```bash
python3 start.py
```

This starts both the CORS proxy on port 9211 and the HTTP server on port 9210, then opens `http://localhost:9210/rum-demo.html` in your browser automatically.

```
  Elastic APM RUM Demo
  UI    ->  http://localhost:9210/rum-demo.html
  Proxy ->  http://localhost:9211

  Opening browser...
  Press Ctrl+C to stop.
```

Press Ctrl+C to stop both servers. If you run `start.py` again while it is already running, it cleans up the old instance automatically before starting.

## First run

On first load a setup overlay appears. Add up to 3 APM server URLs.

* Endpoint 1 is required, 2 and 3 are optional
* Leave Auth blank for RUM — RUM intake does not require a token or API key
* Kibana URL is optional and generates quick-links in the sidebar
* Click Save and start when you are done

Config is saved to localStorage. To change endpoints later, click the gear icon and use the config panel.

## Actions

Every action fires a RUM transaction with realistic child spans to all checked endpoints at once.

Standard actions:

* Search — product search with API, cache, and render spans
* Page Load — homepage load with resource, fetch, and FCP spans
* Filter — category filter with API and render spans
* Login — auth request and session create
* Logout — session teardown
* Recommendations — recommendation fetch, optionally calls the OTel demo app if integration is on
* Slow TX (2s) — 2 second blocking span, useful for latency testing
* Cache Hit — fast cache-hit path under 10ms
* API Retry — simulated retry with 3 attempt spans
* JS Error — transaction with a captured JavaScript error
* Timeout Error — network timeout span with captured error
* Checkout — cart validation, payment, and confirmation spans

Standalone actions (no OTel demo app needed):

* Dashboard load — BI dashboard with 5 chart-load spans
* Form submit — multi-field form validation and submit
* WebSocket session — connect, 15 messages, disconnect
* Infinite scroll — intersection observer, fetch, DOM append

User journeys fire several correlated transactions that share one traceId so they appear linked in APM Traces:

* New visitor — Homepage, Search, Product detail, Add to cart
* Full purchase — Login, Browse, Cart, Payment, Confirm
* Abandoned search — Search, Filter, Slow load, Timeout
* Power user — 5 steps including Login, Search, Filter, Product, Checkout
* Slow mobile — Page load, Recommendations, Slow TX, Timeout, Error
* API heavy — 5 parallel API calls, DB, Cache, Render

Burst mode fires 5 to 100 events sharing one traceId. Use this to generate volume or test ingest throughput.

Custom event builder lets you type any transaction name and type and send it directly.

## Endpoint selection

Check the boxes at the top to choose which endpoints receive the next event. Each action shows one result line per endpoint in the event log so you can confirm fan-out.

## What to check in Kibana

APM Service Inventory:

```
Observability -> APM -> Services -> rum-demo
```

Transactions:

```
APM -> Services -> rum-demo -> Transactions
```

Traces (correlated waterfall for journey and burst events):

```
APM -> Traces
```

Errors (JS Error and Timeout Error actions both capture errors):

```
APM -> Services -> rum-demo -> Errors
```

User Experience (RUM dashboard with page load, Core Web Vitals, Visitor Breakdown, Location):

```
Observability -> User Experience
```

The Kibana quick-links in the right sidebar generate direct URLs once you add a Kibana URL to an endpoint. Six links per endpoint: User Experience, APM Service, Transactions, Errors, Service Map, Traces.

A 202 response from the APM intake API means the event was accepted. Allow 10 to 15 seconds before refreshing Kibana.

## Why the proxy is needed

Browsers cannot call APM servers directly. Opening the HTML as a file:// URL sends a null origin that APM servers reject. Even from localhost, APM servers return a CORS preflight error unless RUM is explicitly enabled in the Fleet agent policy.

`rum-proxy.py` (embedded in `start.py`) solves this by acting as a local relay:

```
Browser -> localhost:9211/intake/v2/events
           (X-Target-Url: https://your-apm-server.cloud.es.io)
                |
                v
           proxy forwards server-to-server (no CORS restriction)
                |
                v
           APM server -> 202 -> proxy -> 202 + CORS headers -> browser
```

Each request includes an X-Target-Url header that tells the proxy where to forward. No hardcoded targets.

## How visitor data populates in Kibana

Kibana User Experience shows Browser, OS, Device, and Location breakdowns. These come from:

* Browser and OS — APM server reads the User-Agent HTTP header on the forwarded request. The proxy sets this from the rotated UA pool.
* Location — APM server reads `context.request.socket.remote_address` from the NDJSON body and does a geo-IP lookup. The tool passes a rotated IP from 15 real public IPs across US, EU, APAC, SA, and IN.
* Core Web Vitals — each page-load transaction includes `transaction.marks` (FCP, LCP, TTFB, domInteractive, domComplete) and `transaction.experience` (cls, fid, lcp, tbt).

The 8 user-agents in the rotation pool cover Chrome on Windows, Chrome on macOS, Chrome on Android, Safari on iOS, Safari on macOS, Firefox on Windows, Chrome on Linux, and Edge on Windows.

## OTel demo app integration (optional)

If the OpenTelemetry demo app is running on localhost:8080, enable Demo app integration in the header. When on, the Recommendations action also fetches `/api/recommendations` with a traceparent header, creating a real distributed trace from the browser through to backend services. All other actions work without it.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Red proxy badge | start.py not running | `python3 start.py` |
| All endpoints red dots | APM URL unreachable | Check URL in config panel |
| 400 from local APM | RUM not enabled in Fleet policy | Enable RUM in Fleet or use ECH |
| Setup overlay reappears | localStorage cleared | Re-enter endpoints |
| Events sent, nothing in Kibana | Indexing lag | Wait 15 seconds and refresh |
| OS/Browser breakdown blank | Stale Kibana data view cache | Hard refresh: Cmd+Shift+R |

## Files

| File | What it does |
|---|---|
| `start.py` | Starts both servers and opens the browser |
| `rum-demo.html` | Self-contained browser UI, all JS inline, no build step |
| `rum-proxy.py` | Standalone CORS proxy if you want to run it separately |

Built by Rahul Ranjan, Elastic Support
