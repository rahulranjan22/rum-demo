# Building a RUM Demo Tool for Elastic APM: How I Test Real User Monitoring Without Real Users

*A walkthrough of a self-contained browser tool that generates synthetic RUM events, populates Kibana's User Experience dashboard, and tests fan-out across multiple APM endpoints, all from a single Python command.*

> **The tool is open source. Grab it here:** [github.com/rahulranjan22/rum-demo](https://github.com/rahulranjan22/rum-demo)

Real User Monitoring is one of those things that sounds simple until you try to set it up. You want to see browser performance, visitor breakdowns, Core Web Vitals, error rates. But to actually see that data in Kibana you need real users hitting a real app. That is a problem during setup, demos, and support troubleshooting.

This article walks through a tool I built for Elastic Support that generates synthetic RUM events and sends them to one or more APM servers at the same time. It runs entirely from a single Python command, needs no Node or npm, and produces real data in Kibana including browser breakdown, OS breakdown, device type, geo-location, Core Web Vitals, transaction waterfalls, correlated traces, and error capture.

## What you will get out of this

By the end of this article you will know:

* Why generating synthetic RUM data is harder than it looks
* How the tool bypasses CORS to reach any APM server from a browser
* How browser, OS, device, and geo-location fields actually get populated in Kibana
* How to send synthetic events to up to three APM endpoints at the same time
* How to generate correlated traces, errors, Core Web Vitals, and burst traffic
* What to look at in each Kibana view after sending events

## What is RUM and why is testing it hard

RUM stands for Real User Monitoring. It is a type of APM telemetry captured in the browser. When a user loads a page, the APM RUM SDK measures things like:

* How long the page took to load (First Contentful Paint, Largest Contentful Paint)
* What API calls the page made and how long each took
* Any JavaScript errors that were thrown
* What browser, OS, and device the user was on
* Where the user was located

In Elastic APM, this data lands in the `traces-apm.*` data stream and shows up in two places in Kibana:

* The APM Service Inventory under the service name
* The User Experience dashboard at Observability → User Experience

The problem is that to see any of this you need events. You need a browser hitting an instrumented page. During customer demos or internal testing, you either wait for real traffic or you fake it.

Faking it is harder than it looks. The APM RUM intake API (`/intake/v2/events`) expects NDJSON. Browsers cannot call APM servers directly because of CORS. Even if you enable RUM in Fleet, the browser needs to be on the same origin or the APM server needs to explicitly allow cross-origin requests. And the data that populates the User Experience dashboard (browser, OS, device, location) comes from specific fields in the NDJSON body and the HTTP headers on the forwarded request, not from the browser making the call.

This tool solves all of that.

## Architecture

The [rum-demo](https://github.com/rahulranjan22/rum-demo) tool has three files:

* `rum-demo.html`: self-contained browser UI with all JS inline
* `start.py`: single launcher that runs both servers
* `rum-proxy.py`: standalone CORS proxy (also embedded in `start.py`)

When you run `python3 start.py`, it does four things:

1. Kills any existing processes on ports 9210 and 9211
2. Starts a static HTTP server on port 9210 to serve `rum-demo.html`
3. Starts a CORS proxy on port 9211 to forward APM calls
4. Opens `http://localhost:9210/rum-demo.html` in the browser

The browser UI lets you configure up to three APM endpoints. Every action you trigger builds a valid NDJSON payload and POSTs it to all active endpoints at once, routing through the local proxy.

Here is how the full request flow looks:

```
Browser
  └─ POST /intake/v2/events
       X-Target-Url: https://your-apm-server.cloud.es.io
       X-Sim-Ip: 185.60.216.35
       X-Sim-Ua: Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 ...)
            │
            ▼
      localhost:9211 (CORS proxy)
            │  reads X-Target-Url header
            │  sets User-Agent: <sim UA>
            │  sets X-Forwarded-For: <sim IP>
            │
            ▼
      APM Server
            │  reads User-Agent → browser/OS/device fields
            │  reads socket.remote_address → geo-lookup
            │
            ▼
      traces-apm.rum-default (Elasticsearch)
```

> The key insight: the proxy forwards the request server-to-server. There is no CORS restriction server-to-server. The browser only ever talks to `localhost:9211`, which it can always reach.

## Setup: from zero to data in Kibana

### What you need

* Python 3 (already on macOS)
* An Elastic APM server: ECH APM, a local Fleet-managed APM agent, or any APM-compatible endpoint
* Chrome or Firefox

No npm, no Node, no Docker.

### Step 1: Clone the repo

```bash
git clone https://github.com/rahulranjan22/rum-demo.git
cd rum-demo
```

### Step 2: Start the tool

```bash
python3 start.py
```

You will see:

```
  Elastic APM RUM Demo
  UI    ->  http://localhost:9210/rum-demo.html
  Proxy ->  http://localhost:9211

  Opening browser...
  Press Ctrl+C to stop.
```

The browser opens automatically. Press Ctrl+C to stop both servers. If the ports are already in use from a previous run, `start.py` kills the old processes before binding.

### Step 3: Configure your endpoints

On first load you see a setup overlay. This is where you enter your APM server URLs.

* Endpoint 1 is required
* Endpoints 2 and 3 are optional: leave blank or fill in for fan-out testing
* Auth: leave blank for RUM. RUM intake uses anonymous access by default
* Kibana URL: optional but useful. When filled in, the right sidebar shows direct links to the APM service, transactions, errors, traces, service map, and User Experience dashboard

For ECH, your APM URL looks like `https://xxxx.apm.us-central1.gcp.cloud.es.io`. For local Fleet APM it is usually `http://localhost:8200`.

Click Save and start. Config persists in localStorage across reloads. To change endpoints later, click the gear icon at the top.

### Step 4: Send your first event

Click the blue Search button in the Actions panel. The event log shows:

```
[16:50:12] TX: product-search (user-interaction)
  ↳ api-search http 245ms
  ↳ cache-check http 12ms
  ↳ render-results ui 67ms
  → Your APM Server: 202 ✓
```

A 202 means the APM server accepted the event. Wait 10 to 15 seconds, then check:

```
Observability → APM → Services → rum-demo
```

## The UI layout

The tool uses a two-column layout so nothing is wasted:

* Left column: Product Catalog and the full Actions panel (standard actions, standalone actions, burst mode, custom event builder)
* Right sidebar: Session Stats with a live running timer, Cart, all six User Journeys, and Kibana quick-links
* Below the grid: a dark-themed RUM event log and an integration reference table

The Session Stats card shows four counters that update in real time as you fire events: transactions, spans, errors, and total POSTs (which accounts for fan-out across all endpoints). The card header shows a session timer counting up from page load so you can see how much activity you generated in a given window.

## Actions: what each one does

Every action builds a valid APM NDJSON payload and sends it to all active endpoints. The payload includes a metadata block, a transaction object, and one or more span objects.

### Standard actions

**Search**: fires a `product-search` user-interaction transaction with three spans: `api-search`, `cache-check`, and `render-results`.

**Page Load**: fires a page-load type transaction with resource timing, fetch, and FCP marks. This is the transaction type that populates Core Web Vitals in the User Experience dashboard.

**Filter**: category filter with an API call span and a render span.

**Login**: auth request and session create spans.

**Logout**: session teardown.

**Recommendations**: recommendation fetch. If Demo app integration is on and the OTel demo app is running on localhost:8080, this action also fetches `/api/recommendations` with a `traceparent` header, creating a real distributed trace.

**Slow TX (2s)**: a blocking 2-second span useful for testing the latency percentile view.

**Cache Hit**: a sub-10ms cache-hit path. Useful for showing bimodal latency distributions.

**API Retry**: three retry spans with exponential backoff labels.

**JS Error**: a transaction with a `captureError` call. Shows up in APM Errors.

**Timeout Error**: a network timeout span with a captured error.

**Checkout**: cart validation, payment gateway call, and confirmation spans. Also clears the cart.

### Standalone actions (no demo app needed)

**Dashboard load**: a BI dashboard transaction with five chart-load spans running in parallel.

**Form submit**: multi-field form validation and submit spans.

**WebSocket session**: connect, 15 message spans, disconnect. Simulates a live data feed.

**Infinite scroll**: intersection observer trigger, fetch, and DOM append spans.

## User Journeys

User journeys fire several transactions that share a single traceId. They appear as one correlated trace in APM Traces with a full waterfall spanning multiple page loads.

The six journeys:

**New visitor**: page-load → search → three product views → add to cart. Six transactions, all linked.

**Full purchase**: login → browse → add to cart → payment → confirmation.

**Abandoned search**: search → filter → slow-load → timeout → exit. Good for showing drop-off patterns.

**Power user**: login → five product views → compare → bulk checkout.

**Slow mobile**: slow page-load → cache-miss → three retries → error. Shows what a bad mobile session looks like in APM.

**API heavy**: five parallel API calls → DB query → cache check → render. Good for showing span depth and parallel execution.

Open APM → Traces in Kibana and click any trace to see the waterfall. All transactions in a journey are linked by the same traceId.

## Burst mode

The burst slider goes from 5 to 100 events. All events in a burst share one traceId. Use burst to:

* Generate enough volume to see latency percentiles stabilize
* Test APM ingest throughput under load
* Verify fan-out is working across all configured endpoints
* Trigger the high-cardinality transaction name warning if you want to show that behavior

## Custom event builder

Type any transaction name and select a type from the dropdown: `user-interaction`, `page-load`, `http-request`, `navigation`, or `custom`. This is useful for testing how a specific transaction naming convention looks in the APM service map, or for targeting a specific transaction type during a demo.

## How browser, OS, device, and location data get populated

> This is the part that took the most iteration to get right. If you have ever set up RUM and seen blank Visitor Breakdown charts in Kibana, this section explains why.

When you look at the Kibana User Experience dashboard you see:

* Browser breakdown: Chrome, Firefox, Safari, Edge
* OS breakdown: Windows, macOS, iOS, Android, Linux
* Device breakdown: desktop, mobile
* Visitor breakdown: visitor count by location on a world map

These fields are populated by the APM server's ingest pipeline, not by the browser making the request.

**Browser and OS** come from the `User-Agent` HTTP header on the request that hits the APM server. The APM ingest pipeline runs a `user_agent` processor that parses the UA string into `user_agent.name`, `user_agent.os.name`, and `user_agent.device.name`.

The tool rotates 8 realistic UA strings per event:

```
Chrome 124 on Windows 10
Chrome 123 on macOS 14
Safari 17.4 on iOS 17.4 (iPhone)
Chrome 124 on Android 14 (Pixel 8)
Firefox 125 on Windows 10
Safari 17.4 on macOS 14
Chrome 124 on Linux
Edge 124 on Windows 10
```

The proxy reads the `X-Sim-Ua` header from the browser request and sets it as the `User-Agent` on the forwarded server-to-server request. That is what the APM server sees and parses.

**Location** comes from `context.request.socket.remote_address` in the NDJSON body. The APM server reads this field and does a geo-IP lookup to set `client.geo.*`. The tool rotates 15 public IPs across US, EU, APAC, SA, and IN regions. Each event picks a random IP from this pool.

> Note: ECH's load balancer strips `X-Forwarded-For` headers on inbound requests. The only reliable way to get rotated geo data into APM is through `context.request.socket.remote_address` in the NDJSON body itself, not through the HTTP header.

**Core Web Vitals** come from the transaction payload itself. Every page-load transaction includes:

```json
"marks": {
  "navigationTiming": { "navigationStart": 0, "domInteractive": 420, "domComplete": 680 },
  "agent": { "timeToFirstByte": 95, "domInteractive": 420, "firstContentfulPaint": 380 }
},
"experience": {
  "cls": 0.04,
  "fid": 42,
  "lcp": 680,
  "tbt": 65
}
```

These populate the Web Vitals section of the User Experience dashboard directly.

## How the NDJSON payload is built

The APM intake API expects NDJSON where the first line is a metadata object and subsequent lines are event objects:

```json
{"metadata":{"service":{"name":"rum-demo","version":"2.0.0","environment":"lab","agent":{"name":"rum-js","version":"5.14.0"},"language":{"name":"javascript"}},"user_agent":{"original":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."}}}
{"transaction":{"id":"abc123","trace_id":"def456","name":"product-search","type":"user-interaction","duration":324,"result":"success","context":{"page":{"url":"http://localhost:9210/products"},"request":{"method":"GET","headers":{"User-Agent":"Mozilla/5.0 ..."},"socket":{"remote_address":"185.60.216.35"}},"response":{"status_code":200}},"timestamp":1748000000000000}}
{"span":{"id":"span1","transaction_id":"abc123","trace_id":"def456","parent_id":"abc123","name":"api-search","type":"http","duration":245,...}}
```

Three things matter for User Experience data:

1. `metadata.user_agent.original`: send only the raw UA string. The APM ingest pipeline parses it. Sending pre-parsed fields like `name`, `version`, or an `os` object causes a field type conflict with the keyword mappings the pipeline sets.

2. `transaction.context.request.headers["User-Agent"]`: the APM server uses this to set `user_agent.original` for the transaction. The proxy sets the actual HTTP `User-Agent` header to the same value so the pipeline picks it up.

3. `transaction.context.request.socket.remote_address`: the APM server reads this for geo-IP lookup. Set this to a real public IP from the region you want to simulate.

## Why the proxy exists

Browsers block cross-origin requests unless the server explicitly allows them. The APM RUM intake endpoint supports CORS, but only if RUM is enabled in the Fleet APM integration policy and `allow_origins` includes your browser's origin.

For local APM managed by elastic-agent, RUM is disabled by default. For ECH, anonymous RUM access needs to be enabled explicitly. In a support or demo context where you are testing multiple deployments, configuring all of this just to run a quick test is impractical.

The proxy bypasses all of this. The browser calls `localhost:9211` with the real APM server URL in an `X-Target-Url` header. The proxy forwards the request server-to-server with no CORS restrictions, then adds CORS response headers before returning to the browser.

The proxy reads four custom headers:

* `X-Target-Url`: the real APM server URL (required)
* `X-Target-Auth`: optional authorization header for the forwarded request
* `X-Sim-Ip`: simulated client IP, forwarded as `X-Forwarded-For`
* `X-Sim-Ua`: simulated user-agent, set as `User-Agent` on the forwarded request

None of these touch the actual browser request headers. They are set on the outbound server request only.

## Fan-out: testing multiple endpoints at once

Define up to three APM endpoints in the config panel. Use the checkboxes in the Send to bar to choose which ones receive the next event.

When all three are checked, every action sends to all three in parallel:

```
[16:51:12] TX: product-search (user-interaction)
  → Local APM :8200 (via proxy): 202 ✓
  → ECH APM (via proxy): 202 ✓
  → ECH ES2 APM (via proxy): 202 ✓
```

This is useful for:

* Comparing how the same event lands in a local Fleet APM vs ECH APM
* Testing RUM across deployment types in one session
* Verifying that a migration from one APM server to another produces identical data

## What to look at in Kibana

### APM Service

Go to Observability → APM → Services → `rum-demo`. You will see transaction throughput, latency percentiles, and error rate. Click into any transaction group to see individual samples with the full span waterfall.

### Traces

Go to Observability → APM → Traces. User journey transactions appear here linked by their shared traceId. Click one to see the full distributed trace waterfall across all linked transactions.

### Errors

Go to APM → Services → rum-demo → Errors. The JS Error and Timeout Error actions both appear here with exception messages, stack traces, and transaction context.

### User Experience

Go to Observability → User Experience. After sending a mix of page-load transactions you will see:

* Page load duration distribution
* Core Web Vitals (LCP, FID, CLS, TBT)
* Visitor Breakdown: browser, OS, device columns
* Map showing visitor locations by country

> If browser or OS breakdown shows blank after a fresh start, do a hard refresh in Kibana with Cmd+Shift+R on Mac. Kibana caches data view field type information and can show stale mappings after an index was recreated.

## Common issues and fixes

**Red proxy badge in the footer**: the proxy is not running. Run `python3 start.py` from the repo directory.

**All endpoint dots grey or red**: the APM server URL is not reachable. Check the URL in the config panel. Do not include `/intake/v2/events` in the URL. The tool appends the path automatically.

**202 in the log but nothing in Kibana**: wait 15 to 20 seconds and refresh. If still nothing, check that the APM server is forwarding to Elasticsearch and the ILM policy has not closed the index.

**400 from local APM**: RUM is disabled by default in Fleet. Go to Fleet → Agent policies → your policy → APM integration → enable RUM → set allowed origins to `*`.

**Setup overlay appears on every load**: your browser cleared localStorage. Re-enter the endpoints and save.

**OS or Browser breakdown shows an error in User Experience**: this happens after the `traces-apm.rum-default` data stream is deleted and recreated. Kibana caches field type metadata. Hard refresh with Cmd+Shift+R.

## OTel demo app integration (optional)

If you have the OpenTelemetry demo app running on localhost:8080, enable Demo app integration in the header. When on, the Recommendations action fires the usual synthetic APM RUM transaction and also makes a real `fetch()` call to `localhost:8080/api/recommendations` with a `traceparent` header.

If the OTel demo's collector is forwarding to your APM server, this creates a distributed trace that starts in the browser and continues through backend microservices. In APM → Traces you will see the browser span linked to backend service spans in one waterfall.

All other actions are fully standalone and do not need the OTel demo app running.

## What this is good for in a support context

**Reproducing Kibana User Experience issues**: generate specific combinations of UA strings, geo IPs, and transaction types to reproduce mapping or aggregation problems without needing real user traffic.

**Testing APM server configuration**: sending to a local Fleet APM and an ECH APM at the same time makes it easy to compare how the same event is indexed in each deployment.

**Demonstrating APM RUM capabilities**: the journeys, burst mode, and action variety cover the full APM RUM feature set in a single demo session.

**Validating ingest pipelines**: after deleting and recreating a data stream or changing an ILM policy, send a controlled batch and confirm what landed in Elasticsearch without waiting for real users.

## Files in the repo

* `start.py`: single launcher that starts the HTTP server on 9210, the proxy on 9211, and opens the browser
* `rum-demo.html`: self-contained browser UI, all JS inline, no build step required
* `rum-proxy.py`: standalone CORS proxy if you want to run it separately from the launcher
* `README.md`: setup reference, feature list, and troubleshooting guide

The HTML file is entirely self-contained. No external CDN, no SDK dependency, no API key baked in. All event construction and endpoint config lives in the file.

## Closing

The tool started as a quick way to populate a demo APM environment with RUM events without needing real user traffic. It grew into something more complete as each gap showed up: CORS blocking, blank Visitor Breakdown, missing geo data, field type conflicts in the APM ingest pipeline.

Every fix came from testing against a real APM server, reading the ingest pipeline code, and iterating until the Kibana charts showed what they should.

If you are working with Elastic APM RUM and need synthetic data, this is the fastest path from zero to a populated User Experience dashboard.

The full source is at [github.com/rahulranjan22/rum-demo](https://github.com/rahulranjan22/rum-demo).

Built by Rahul Ranjan, Elastic Support
