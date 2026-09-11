# Building a RUM Demo Tool for Elastic APM: How We Test Real User Monitoring Without Real Users

Real User Monitoring is one of those things that sounds simple until you try to set it up. You want to see browser performance, visitor breakdowns, Core Web Vitals, error rates. But to actually see that data in Kibana you need real users hitting a real app. That is a problem during setup, demos, and support troubleshooting.

This article walks through a tool I built for Elastic Support that generates synthetic RUM events and sends them to one or more APM servers at the same time. It runs entirely from a single Python command, needs no Node or npm, and produces real data in Kibana including browser breakdown, OS breakdown, device type, geo-location, Core Web Vitals, transaction waterfalls, correlated traces, and error capture.

## What is RUM and why is testing it hard

RUM stands for Real User Monitoring. It is a type of APM telemetry captured in the browser. When a user loads a page, the APM RUM SDK measures things like:

* How long the page took to load (First Contentful Paint, Largest Contentful Paint)
* What API calls the page made and how long each took
* Any JavaScript errors that were thrown
* What browser, OS, and device the user was on
* Where the user was located

In Elastic APM, this data lands in the `traces-apm.*` data stream and shows up in two places in Kibana:

* The APM Service Inventory under the `rum-demo` service
* The User Experience dashboard at Observability → User Experience

The problem is that to see any of this you need events. You need a browser hitting an instrumented page. During customer demos or internal testing, you either wait for real traffic or you fake it.

Faking it is harder than it looks. The APM RUM intake API (`/intake/v2/events`) expects NDJSON. Browsers cannot call APM servers directly because of CORS. Even if you enable RUM in Fleet, the browser needs to be on the same origin or the APM server needs to explicitly allow cross-origin requests. And the data that populates the User Experience dashboard (browser, OS, device, location) comes from specific fields in the NDJSON body and the HTTP headers on the forwarded request, not from the browser making the call.

This tool solves all of that.

## Architecture

The tool has three parts:

```
rum-demo.html       self-contained browser UI with all JS inline
start.py            single launcher that runs both servers
rum-proxy.py        standalone CORS proxy (optional, also embedded in start.py)
```

When you run `python3 start.py`, it:

1. Kills any existing processes on ports 9210 and 9211
2. Starts a static HTTP server on port 9210 to serve `rum-demo.html`
3. Starts a CORS proxy on port 9211 to forward APM calls
4. Opens `http://localhost:9210/rum-demo.html` in the browser

The browser UI lets you configure up to 3 APM endpoints. Every action you trigger builds a valid NDJSON payload and POSTs it to all active endpoints at once, routing through the local proxy.

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

The key insight is that the proxy forwards the request server-to-server. There is no CORS restriction server-to-server. The browser only talks to `localhost:9211`, which it can always reach.

## Setup: from zero to data in Kibana

### What you need

* Python 3 (already on macOS)
* An Elastic APM server: ECH APM, a local Fleet-managed APM agent, or any APM-compatible endpoint
* Chrome or Firefox

You do not need npm, Node, Docker, or any build tooling.

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

The browser opens automatically. Press Ctrl+C to stop both servers. If the ports are already in use from a previous run, `start.py` kills the old processes automatically before binding.

### Step 3: Configure your endpoints

On first load you see a setup overlay. This is where you enter your APM server URLs.

* Endpoint 1 is required
* Endpoints 2 and 3 are optional: leave them blank or fill them in for fan-out testing
* Auth: leave blank for RUM. RUM intake uses anonymous access by default
* Kibana URL: optional but useful. When filled in, the right sidebar shows direct links to the APM service, transactions, errors, traces, service map, and User Experience dashboard

Paste your APM server URL. For ECH it looks like `https://xxxx.apm.us-central1.gcp.cloud.es.io`. For local Fleet APM it is usually `http://localhost:8200`.

Click Save and start.

Config is saved to localStorage. To change endpoints later, click the gear icon at the top.

### Step 4: Send your first event

Click the blue Search button in the Actions panel. The event log shows the result:

```
[16:50:12] TX: product-search (user-interaction)
  ↳ api-search http 245ms
  ↳ cache-check http 12ms
  ↳ render-results ui 67ms
  → Your APM Server: 202 ✓
```

A 202 means the APM server accepted the event. Wait 10-15 seconds and check Kibana.

```
Observability → APM → Services → rum-demo
```

## The event log and session stats

The right sidebar shows a Session Stats card with four counters that update in real time:

* Transactions
* Spans
* Errors
* Total POSTs (TX + spans + errors × endpoints)

The card header also shows a session timer that counts up from when the page loaded. This is useful during demos to show how much activity has been generated in a given window.

Below the stats is the Cart and User Journeys section. Below the two-column layout is a dark-themed event log that shows every TX, every span indent, and every endpoint response code.

The proxy status badge in the footer turns green when it can reach `localhost:9211` and red when it cannot, with the start command displayed inline.

## Actions: what each one does

Every action builds a valid APM NDJSON payload and sends it to all active endpoints. The payload includes a metadata block, a transaction object, and one or more span objects.

### Standard actions

**Search**: fires a `product-search` user-interaction transaction with three spans: `api-search`, `cache-check`, and `render-results`.

**Page Load**: fires a page-load type transaction with resource timing, fetch, and FCP marks. This is the transaction type that populates Core Web Vitals in the User Experience dashboard.

**Filter**: category filter with an API call span and a render span.

**Login**: auth request and session create spans.

**Logout**: session teardown.

**Recommendations**: recommendation fetch. If Demo app integration is enabled and the OTel demo app is running on localhost:8080, this action also fetches `/api/recommendations` with a `traceparent` header, creating a real distributed trace.

**Slow TX (2s)**: a blocking 2-second span useful for testing the APM latency percentile view.

**Cache Hit**: a sub-10ms cache-hit path. Useful to show bimodal latency distributions.

**API Retry**: three retry spans with exponential backoff labels.

**JS Error**: a transaction with a `captureError` call. Shows up in APM Errors and increments the error counter in the session stats.

**Timeout Error**: a network timeout span with a captured error.

**Checkout**: cart validation, payment gateway call, and confirmation spans. Also clears the cart.

### Standalone actions (no OTel demo needed)

**Dashboard load**: a BI dashboard transaction with five chart-load spans running in parallel.

**Form submit**: multi-field form validation and submit spans.

**WebSocket session**: connect, 15 message spans, disconnect. Simulates a live data feed.

**Infinite scroll**: intersection observer trigger, fetch, and DOM append spans.

## User Journeys

User journeys fire several transactions that share a single traceId. This means they appear as one correlated trace in APM Traces with a full waterfall spanning multiple page loads.

The six journeys:

**New visitor**: page-load → search → three product views → add to cart. Six transactions, all linked.

**Full purchase**: login → browse → add to cart → payment → confirmation.

**Abandoned search**: search → filter → slow-load → timeout → exit. Good for showing drop-off patterns.

**Power user**: login → five product views → compare → bulk checkout.

**Slow mobile**: slow page-load → cache-miss → three retries → error. Shows what a bad mobile session looks like in APM.

**API heavy**: five parallel API calls → DB query → cache check → render. Good for showing span depth and parallel execution.

In Kibana, open APM → Traces and click any trace to see the waterfall. All transactions in a journey are linked by the same traceId.

## Burst mode

The burst slider goes from 5 to 100 events. All events in a burst share one traceId. Use burst to:

* Generate enough volume to see latency percentiles stabilize
* Test APM ingest throughput
* Verify fan-out is working across all configured endpoints
* Trigger the high-cardinality transaction name warning if you want to show that behavior

## Custom event builder

At the bottom of the Actions panel is a custom event builder. Type any transaction name and select a type:

* user-interaction
* page-load
* http-request
* navigation
* custom

This is useful during demos to show specific transaction names appearing in APM, or to test how a customer's transaction naming convention looks in the service map.

## How browser, OS, device, and location data work

This is the part that took the most iteration to get right.

When you look at the Kibana User Experience dashboard you see:

* Browser breakdown: Chrome, Firefox, Safari, Edge
* OS breakdown: Windows, macOS, iOS, Android, Linux
* Device breakdown: desktop, mobile
* Visitor breakdown: visitor count by location on a world map

These fields are populated by the APM server's ingest pipeline, not by the browser making the request. Specifically:

**Browser and OS** come from the `User-Agent` HTTP header on the request that hits the APM server. The APM ingest pipeline runs a `user_agent` processor that parses the UA string into `user_agent.name`, `user_agent.os.name`, `user_agent.device.name`.

The tool rotates 8 realistic UA strings:

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

**Location** comes from `context.request.socket.remote_address` in the NDJSON body. The APM server reads this field and does a geo-IP lookup to set `client.geo.*`. The tool rotates 15 public IPs across different regions:

* US: Google DNS, Google NYC, Fastly SF, AWS us-east-1, AWS us-west-2
* Europe: Facebook London, Frankfurt, Paris
* APAC: Singapore, Tokyo, Amsterdam
* Other: São Paulo, Johannesburg, Mumbai, TEST-NET AU

Each event picks a random IP from this pool. That is why the User Experience map shows visitors from different countries.

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

## Why the proxy exists and how it works

Browsers block cross-origin requests unless the server explicitly allows them. The APM RUM intake endpoint does support CORS, but only if RUM is enabled in the Fleet APM integration policy and the `allow_origins` list includes your browser's origin.

For local APM managed by elastic-agent, RUM is disabled by default. For ECH, CORS is supported but you need a valid RUM secret token or anonymous access enabled. In a support or demo context where you are testing different deployments, configuring all of this just to run a demo is impractical.

The proxy bypasses all of this. The browser calls `localhost:9211` with the real APM server URL in an `X-Target-Url` header. The proxy forwards the request server-to-server, which has no CORS restrictions. The proxy adds the CORS response headers before returning to the browser.

The proxy reads four custom headers from the browser:

* `X-Target-Url`: the real APM server URL to forward to (required)
* `X-Target-Auth`: optional authorization header to set on the forwarded request
* `X-Sim-Ip`: simulated client IP, forwarded as `X-Forwarded-For`
* `X-Sim-Ua`: simulated user-agent, set as `User-Agent` on the forwarded request

These never touch the actual browser request headers. They are set by the proxy on the outbound server request. That is how the APM server sees a Chrome iOS UA and a London IP even though the request is coming from your Mac.

## Fan-out: testing multiple endpoints at once

The config panel lets you define up to three APM endpoints. In the Send to bar at the top, you toggle which endpoints are active for the next event.

When all three are checked, every action sends to all three in parallel. The event log shows one result line per endpoint:

```
[16:51:12] TX: product-search (user-interaction)
  → Local APM :8200 (via proxy): 202 ✓
  → ECH APM (via proxy): 202 ✓
  → ECH ES2 APM (via proxy): 202 ✓
```

This is useful for:

* Comparing how the same event lands in a local Fleet APM vs ECH APM vs a different cluster
* Testing RUM across deployment types in one session
* Verifying that a migration from one APM server to another produces identical data

Each endpoint is independent. You can uncheck one to exclude it from the next event and re-check it at any time.

## What to look at in Kibana after sending events

### APM Service

```
Observability → APM → Services → rum-demo
```

You will see the service listed with:

* Transaction throughput (req/min)
* Latency percentiles (p50, p95, p99)
* Error rate

Click in to see transaction groups: `product-search`, `page-load /`, `error-scenario`, etc.

### Transactions

Click any transaction group to see individual transaction samples. The detail view shows the waterfall with all spans, their durations, and any tags. The trace context section shows `traceId`, `transactionId`, and the service name.

### Traces

```
Observability → APM → Traces
```

User journey transactions appear here linked by their shared traceId. Click one to see the full distributed trace waterfall across all linked transactions.

### Errors

```
Observability → APM → Services → rum-demo → Errors
```

JS Error and Timeout Error actions both appear here. Each error shows the exception message, the stack trace, and the transaction context.

### User Experience

```
Observability → User Experience
```

This is the RUM-specific dashboard. After sending a mix of page-load transactions you will see:

* Page load duration distribution
* Core Web Vitals (LCP, FID, CLS, TBT)
* Visitor Breakdown: browser, OS, device columns
* Map showing visitor locations by country

If the browser or OS breakdown shows blank, do a hard refresh in Kibana (Cmd+Shift+R on Mac). Kibana caches data view field type information and can show stale mappings after an index was recreated.

## Common issues

**Red proxy badge in the footer**

The proxy is not running. Run `python3 start.py` from the repo directory and reload the page.

**All endpoint dots are grey or red**

The APM server URL is not reachable. Check the URL in the config panel. For ECH, make sure the URL does not have a trailing path (just the hostname and port, no `/intake/v2/events` appended: the tool adds the path automatically).

**202 in the log but nothing in Kibana**

APM ingest has a short lag. Wait 15-20 seconds and refresh. If still nothing, check that the APM server is forwarding to Elasticsearch and that the index lifecycle policy has not closed the index.

**400 from local APM**

RUM is disabled by default in the Fleet APM integration. In Kibana, go to Fleet → Agent policies → your policy → APM integration → enable RUM → set allowed origins to `*`. Or route through ECH APM which supports anonymous RUM access.

**Setup overlay appears on every load**

Your browser cleared localStorage. Re-enter the endpoints and save.

**OS or Browser breakdown shows error in User Experience**

This can happen after the `traces-apm.rum-default` data stream is deleted and recreated. Kibana caches field type metadata. Hard refresh with Cmd+Shift+R.

## How the NDJSON payload is built

The APM intake API expects NDJSON where the first line is a metadata object and subsequent lines are event objects. A minimal page-load transaction looks like this:

```json
{"metadata":{"service":{"name":"rum-demo","version":"2.0.0","environment":"lab","agent":{"name":"rum-js","version":"5.14.0"},"language":{"name":"javascript"}},"user_agent":{"original":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."}}}
{"transaction":{"id":"abc123","trace_id":"def456","name":"product-search","type":"user-interaction","duration":324,"result":"success","outcome":"success","sampled":true,"span_count":{"started":3,"dropped":0},"context":{"page":{"url":"http://localhost:9210/products"},"request":{"method":"GET","url":{...},"headers":{"User-Agent":"Mozilla/5.0 ..."},"socket":{"remote_address":"185.60.216.35"}},"response":{"status_code":200}},"timestamp":1748000000000000}}
{"span":{"id":"span1","transaction_id":"abc123","trace_id":"def456","parent_id":"abc123","name":"api-search","type":"http","subtype":"external","duration":245,...}}
```

Three things matter for User Experience data:

1. `metadata.user_agent.original`: just the raw UA string, nothing more. The APM ingest pipeline parses it. Sending pre-parsed fields (`name`, `version`, `os` object) causes a field type conflict with the keyword mappings set by the pipeline.

2. `transaction.context.request.headers["User-Agent"]`: the APM server uses this to set `user_agent.original` for the transaction. The proxy also sets the actual HTTP `User-Agent` header to the same value for the pipeline to pick up.

3. `transaction.context.request.socket.remote_address`: the APM server reads this for geo-IP lookup. The ECH load balancer strips `X-Forwarded-For` headers, so the only reliable way to get rotated geo data is through this field in the NDJSON body.

## OTel demo app integration

If you have the OpenTelemetry demo app running locally on port 8080, enable Demo app integration in the header bar.

When enabled, the Recommendations action does two things:

1. Fires the usual synthetic APM RUM transaction to your configured endpoints
2. Makes a real `fetch()` call to `localhost:8080/api/recommendations` with a `traceparent` header containing the current traceId and spanId

If the OTel demo's collector is configured to forward to your APM server, this creates a distributed trace that starts in the browser and continues through the OTel demo's backend microservices. In APM → Traces you will see the browser span linked to the backend service spans in one waterfall.

All other actions are fully standalone and do not need the OTel demo app running.

## What this tool is good for in a support context

**Reproducing Kibana User Experience issues**: you can generate specific combinations of UA strings, geo IPs, and transaction types to reproduce mapping or aggregation problems without needing real user traffic.

**Testing APM server configuration**: sending to a local Fleet APM and an ECH APM at the same time makes it easy to compare how the same event is indexed in each deployment. Useful for verifying that a Fleet policy change actually enables RUM.

**Demonstrating APM RUM capabilities**: the journeys, burst mode, and action variety give you enough variety to walk through the full APM RUM feature set in a demo.

**Validating ingest pipelines**: after deleting and recreating a data stream, or after changing an ILM policy, you can send a controlled batch of events and confirm what landed in Elasticsearch without waiting for real user traffic.

## Files in the repo

| File | What it does |
|---|---|
| `start.py` | Single launcher: runs HTTP server on 9210, proxy on 9211, opens browser |
| `rum-demo.html` | Self-contained browser UI, all JS inline, no build step required |
| `rum-proxy.py` | Standalone CORS proxy: use this if you want to run the proxy separately |
| `README.md` | Setup and feature reference |

The HTML file is entirely self-contained. No external CDN, no SDK dependency, no API key baked in. All event construction and endpoint config lives in the file itself.

## Closing

The tool started as a quick way to populate a demo APM environment with RUM events without needing real user traffic. It grew into something more complete as each gap showed up: CORS blocking, blank Visitor Breakdown, missing geo data, field type conflicts in the APM ingest pipeline.

Every fix came from actually testing against a real APM server, reading the APM server source and ingest pipeline docs, and iterating until the Kibana charts matched what they should show.

If you are working with Elastic APM RUM and need synthetic data, this is the fastest path from zero to a populated User Experience dashboard.

The repo is at https://github.com/rahulranjan22/rum-demo.

Built by Rahul Ranjan, Elastic Support