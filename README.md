# ACG Search SG Prototype

This is a FastAPI-based prototype for a Singapore-first ACG news aggregator. It supports two modes:

- Home feed: latest headlines ranked by freshness, source quality, and Singapore relevance.
- Search feed: hybrid retrieval that combines SQLite FTS keyword search with vector similarity and optional LLM reranking.
- Profile-aware ranking: each `user_id` accumulates preferences from pinned interests, searches, opens, likes, and dismissals.

## What is included

- FastAPI backend with `GET /api/news`, `POST /api/search`, `POST /api/search/digest`, `GET/POST /api/profile`, `POST /api/interactions`, `POST /api/refresh`, and `GET /api/source-health`
- SQLite article store with FTS5 for lexical search
- Local hash vectors only when no embedding provider is configured, with provider-backed semantic embeddings available through `EMBEDDING_*` settings and optional ChromaDB persistence when you want a vector database backing store
- RSS ingestion adapters for ACG-heavy sources and Singapore-oriented Google News queries
- Direct Singapore event ingestion from Eventbrite plus curated Singapore/SEA feeds such as Anime Festival Asia and Bandwagon Asia
- Optional LLM hooks for query expansion, summarization, digest generation, and reranking
- Static frontend served by FastAPI for default headlines and prompt-driven search
- Lightweight profile controls in the UI so the feed can learn from user feedback without a separate auth system
- Seed dataset so the prototype is usable before any live sources are fetched

## Project layout

```text
app/
  main.py
  config.py
  database.py
  schemas.py
  services/
  sources/
  static/
data/
  sample_articles.json
scripts/
  ingest_news.py
```

## Local setup

1. Create and activate a virtual environment.
2. Install dependencies.
3. Copy `.env.example` to `.env` if you want to customize the runtime.
4. Run the ingestion script once.
5. Start the FastAPI server.

Example commands:

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
/opt/homebrew/bin/python3 scripts/ingest_news.py
/opt/homebrew/bin/python3 -m uvicorn app.main:app --reload
```

For browser regressions, install the dev-only test dependency set instead:

```bash
pip install -r requirements-dev.txt
```

If you explicitly want the optional ChromaDB backend, install its extra dependency set as well:

```bash
pip install -r requirements-chromadb.txt
```

Open `http://127.0.0.1:8000` in your browser.

## Automated tests

Run the deterministic backend and cache-behavior tests with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The suite now includes a browser-level Playwright navigation test. Install Chromium once before running it locally:

```bash
.venv/bin/python -m playwright install chromium
```

The same deterministic suite is wired into GitHub Actions in `.github/workflows/regression.yml`.

## Personalized profiles

The frontend now creates a lightweight local profile id and sends it with feed/search requests. That profile supports two sources of personalization:

- Pinned interests: explicit category and region preferences saved from the UI.
- Learned interests: search history and article interactions (`open`, `like`, `dismiss`) stored in SQLite and used as reranking signals.

Dismissed stories are hidden from that profile's future feed/search results. This keeps the behavior stateful without introducing a login system.

## Browser cache behavior

The prototype now defaults to `DISABLE_HTTP_CACHE=true` so local development does not reuse stale HTML, CSS, or JS and does not keep returning `304 Not Modified` for the app shell on every refresh.

- Keep it `true` for local iteration when you want predictable asset reloads.
- Set it to `false` if you want normal HTTP caching behavior.

The refresh endpoint is also local-only by default. `POST /api/refresh` only accepts loopback clients unless you explicitly set `ALLOW_REMOTE_REFRESH=true` in the environment.

The app also logs request timings for `POST /api/search` and `POST /api/refresh`, and it warns when any API request takes longer than `REQUEST_SLOW_LOG_MS`.
Each API response now includes an `X-Request-ID` header as well. If a caller supplies a valid `X-Request-ID`, the app reuses it so request-level logs can be correlated across the API boundary and refresh ingestion flow. The CLI ingest script now generates a unique request id for every run and prints it in the JSON result for the same reason.

Source ingestion health is now persisted per source. `GET /api/source-health` returns the latest per-source status, fetched count, persisted contribution count, consecutive failures, last success timestamp, last error, and stale flag. Staleness defaults to `SOURCE_HEALTH_STALE_HOURS=24` and can be overridden per request via `stale_after_hours`.
Historical runs are also stored in `source_health_runs`; `GET /api/source-health/runs` returns recent run history, optionally filtered by `source_name`, so repeated failures and recovery patterns can be examined over time. Old run rows are pruned automatically based on `SOURCE_HEALTH_RUNS_RETENTION_DAYS` so the SQLite history does not grow without bound.
`GET /api/source-health/rollups` returns a per-source failure-rate summary over a configurable trailing window, which the UI uses for a quick 24-hour operational view.
The source monitor UI also shows a recent-status sparkline per source and a modal for deeper per-source run history, including request ids and stored error text.

## LLM options

You can run the prototype without an LLM. In that mode, query expansion, digest generation, and tagging fall back to deterministic heuristics.

The prototype also runs without ChromaDB enabled. `VECTOR_BACKEND=local` is the safest default on newer Python versions. If you want persistent vector storage through ChromaDB, set `VECTOR_BACKEND=chromadb`.

When `VECTOR_BACKEND=local`, vector search now scores a bounded candidate pool instead of scanning the full article table. The pool is seeded by lexical hits and then filled from the strongest stored headlines. You can tune its size with `LOCAL_VECTOR_PREFILTER_LIMIT`.

Actual semantic retrieval is configured separately from chat generation:

- Set `EMBEDDING_PROVIDER`, `EMBEDDING_BASE_URL`, and `EMBEDDING_MODEL` to enable provider-backed semantic vectors.
- Existing articles are backfilled on startup when the active semantic embedding signature changes, so you do not need a full re-ingest to switch models.
- When an embedding provider is configured, vector search stays strict: it uses semantic vectors or contributes no vector score. It does not silently fall back to the hash-vector path.
- For local Ollama, `EMBEDDING_MODEL=nomic-embed-text` and `LLM_MODEL=qwen2.5:3b` are the lightest practical defaults for this app on consumer hardware.
- Local model calls use dedicated timeouts now: `EMBEDDING_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`, `LLM_EXPAND_TIMEOUT_SECONDS`, `LLM_RERANK_TIMEOUT_SECONDS`, and `LLM_DIGEST_TIMEOUT_SECONDS` can be tuned separately so search-time model steps fall back quickly without stalling the whole request.
- Startup backfill batches semantic embedding requests with `EMBEDDING_BATCH_SIZE`, which matters for local Ollama because sending the entire corpus in one request can time out on smaller machines.
- `LLM_MAX_TOKENS` now caps local model output, which helps smaller Ollama models stay responsive for query expansion, reranking, and digest generation.
- You can tune cold-path latency more precisely now with `LLM_EXPAND_MAX_TOKENS`, `LLM_RERANK_MAX_TOKENS`, and `LLM_DIGEST_MAX_TOKENS` instead of relying only on the single global `LLM_MAX_TOKENS` cap.
- Query expansion and digest generation now use a small in-process TTL cache. Tune it with `LLM_CACHE_TTL_SECONDS` and `LLM_CACHE_MAX_ENTRIES` if you want shorter reuse windows or a larger cache.
- Rerank outputs now use the same in-process TTL cache, keyed by query plus the active candidate set, so repeated interactive searches can avoid paying the full rerank cost again.
- When query expansion, reranking, or deferred digest hit their task-specific timeout budget, the service now falls back immediately to the deterministic path and caches that fallback result too, so repeated requests do not keep paying the timeout.
- Search requests also short-circuit later inline LLM steps after the first search-time timeout, so a slow query expansion will not make the same request wait again for reranking or inline digest generation.
- For local Ollama search, already-specific queries also skip inline LLM expansion and reranking up front when heuristic expansion already fired or the query already has strong anchor terms, which keeps the cold path near vector-search cost instead of waiting on chat generation.
- Deferred search digests now reuse that same local skip gate, so specific Singapore/SEA-style searches can return the deterministic "Why these headlines" rationale immediately instead of waiting on a local chat completion.
- `POST /api/search/digest` also supports `prefer_llm=true` for an optional enhanced digest pass, but the frontend only auto-requests that second pass when the backend marks it as worthwhile for the active provider.
- Semantic query embeddings now use the same TTL cache too, so warm semantic searches can skip the repeat embedding call and spend their time mostly on candidate scoring.
- `WARM_LOCAL_MODELS_ON_STARTUP=true` now warms local embeddings during runtime initialization and kicks LLM warmup off in the background, so startup stays fast while the chat model is still nudged warm for the next search or deferred digest.
- `POST /api/search` now accepts `include_digest`; the static frontend sends `false` so interactive search renders results first and fetches the digest afterward through `POST /api/search/digest`.
- Search and deferred-digest responses now include timing breakdowns. `FeedResponse.timings` reports query expansion, lexical retrieval, semantic retrieval, reranking, and optional inline digest cost; `DigestResponse.timings` reports deferred digest lookup and generation time.

If you want a model in the loop:

- For Ollama, set `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://localhost:11434`, and `LLM_MODEL` to a local model.
- For OpenAI-compatible servers such as LM Studio or an API gateway, set `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_MODEL`, and optionally `LLM_API_KEY`.
- Search-time query expansion and reranking are enabled whenever a valid LLM provider/model is configured; `ENABLE_LLM_ENRICHMENT` only gates ingest-time summarization and tagging.
- The chat client now tolerates both base URLs that already end in `/v1` and URLs that point at the API root.

## How the ranking works

Home feed score:

```text
0.45 * freshness + 0.25 * Singapore relevance + 0.15 * category priority + 0.15 * source quality
```

Search score:

```text
0.30 * lexical score + 0.22 * vector score + 0.28 * query intent + 0.10 * Singapore relevance + 0.10 * freshness + 0.12 * profile match
```

Singapore relevance is boosted by signals such as `Singapore`, `SGD`, `Anime Festival Asia`, `HoyoFest`, `Suntec`, `MLBB`, and other local or regional cues.

Profile match combines explicit pinned interests with learned category, tag, region, and recent-query affinity.

Search also drops weak candidates that do not contain any meaningful anchor match for the user query, and it no longer falls back to unrelated latest headlines when no strong match exists.

## Search evaluation

You can run a backend-only query suite to inspect search quality across a wider Singapore ACG prompt set:

```bash
.venv/bin/python scripts/evaluate_search.py
```

The script currently evaluates 31 queries against the current article store, checks the top results for expected keywords, and prints a JSON report with per-query pass/fail status. It intentionally runs without a `user_id` so profile learning does not contaminate baseline search evaluation.

This live-store evaluation is intentionally separate from the deterministic CI suite. The CI tests run against a controlled fixture, while `scripts/evaluate_search.py` checks relevance against whatever has actually been ingested locally.

The ingestion path now also canonicalizes recurring event-listing titles and prunes stored duplicates, so repeated series entries such as day-by-day workshop variants do not keep stacking in search and feed results.

When duplicate or stale articles are removed, the stored interaction log is maintained as well. Duplicate-prune runs remap interaction rows from deleted article ids to the kept article id, and startup maintenance removes interaction rows that no longer point at any article.

The CLI ingestion script now prints the latest source-health summary after each run, which makes it easier to spot failing or stale upstream sources without opening the API separately.

The regression suite now also includes concurrent profile-write checks to confirm that overlapping search and interaction updates against the same user profile do not lose affinity or interaction-count updates.

Cross-source entity normalization is now layered on top of that cleanup. The API extracts shared event and franchise labels such as `AFA Singapore`, `SGCC`, `HoyoFest Singapore`, `MLBB`, and `FFXIV Fan Festival`, then returns grouped coverage clusters alongside each feed/search response.

## Result diversity

Broad queries now run through a lightweight diversity pass before results are returned. That reduces same-source stacking and helps the feed/search mix in adjacent but still relevant stories instead of showing near-duplicates back-to-back.

The deterministic tests include explicit coverage for this behavior so diversity regressions are caught alongside top-hit relevance regressions.

## Coverage clusters

Feed and search responses now include `entity_groups`, which summarize repeated coverage around the same normalized event, franchise, or esports topic across multiple sources.

The frontend uses these groups to show a shared-coverage panel and renders per-article entity chips so related stories are easier to scan.

Entity chips are now interactive. Clicking a chip or a cluster focus button pivots the search feed directly to that normalized entity, and the profile model now learns entity-level affinities from searches, likes, opens, and dismissals.

The profile form also supports explicit pinned entities, so users can permanently bias the feed toward clusters such as `AFA Singapore`, `SGCC`, `HoyoFest Singapore`, or `MLBB` without waiting for interaction history to build up.

When multiple visible results share the same normalized entity, the main feed now collapses them into a single expandable cluster card instead of repeating near-identical coverage card by card.

Those entity chips and cluster cards now include direct follow and unfollow controls, so users can pin a normalized event or franchise in one click without going back to the profile form.

Pinned clusters also render as removable interactive rows inside the profile memory panel, and the UI now exposes a dedicated cluster detail modal that can open broader related coverage without replacing the current feed view.

The app shell now keeps lightweight URL state for the active search and open cluster detail. Shared links such as `/?query=AFA%20Singapore&entity=AFA%20Singapore` reopen both the prompt-ranked feed and the matching cluster modal on load.

History state now uses user-facing navigation semantics rather than silent replacement only. Explicit searches, opening cluster detail, returning home, and closing the modal create navigable browser history entries, while internal refreshes and route replay avoid recording duplicate profile-search signals.

Cluster detail cards now surface lightweight structured event metadata when it can be inferred from the stored story text, including event type, date window, venue, ticket status, guest-lineup mentions, and merch or booth updates.

For Eventbrite-style event listings, the ingestion path now carries source-specific structured metadata through to the stored article record, including normalized date ranges, venue, ticket URLs, ticket availability cues, and named performers when the source provides them.

## CI

The repository includes a GitHub Actions workflow that runs the deterministic regression suite on `push`, `pull_request`, and manual dispatch.

It is defined in `.github/workflows/regression.yml` and uses the same local-vector, no-LLM configuration as the workspace tests.

## Vercel deployment

The repository now includes a Vercel FastAPI entrypoint in `app/index.py`, a minimal `vercel.json` that selects the FastAPI framework preset, and a GitHub Actions deployment workflow in `.github/workflows/vercel-deploy.yml`.

To make pushes to `main` deploy automatically, the GitHub repository must have these secrets configured:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

The Vercel deployment now installs from the repo-level `requirements.txt`, which is already limited to runtime dependencies instead of browser-test packages.
The repository also pins Python with `.python-version` because Vercel reads Python versions from `.python-version`, `pyproject.toml`, or `Pipfile.lock` rather than from a `runtime` string in `vercel.json`.

Important deployment note: the app still uses SQLite as its operational store, and on Vercel that writable database lives under `/tmp`. To make that durable without rewriting the repository layer yet, set `DATABASE_URL` to a Neon or other Postgres database. When configured, the app restores the SQLite file from Postgres on startup and persists updated snapshots back after profile writes, personalized searches, interactions, refresh runs, and CLI ingests.

The relevant environment variables are:

- `DATABASE_URL`
- `STATE_SNAPSHOT_KEY` (optional, defaults to `acg-search-runtime`)
- `STATE_STORE_CONNECT_TIMEOUT_SECONDS` (optional, defaults to `10`)

This is a low-risk durability bridge rather than a full native Postgres migration. The current SQLite and FTS5 logic stays intact, while Neon stores the latest runtime snapshot across cold starts.

The bundled seed dataset continues to load on Vercel even though the writable runtime state lives under `/tmp`, so cold starts still have baseline feed and search content. It also serves as the first bootstrap source when the durable snapshot store is empty.

For better production parity, the app will prefer a bundled deployment snapshot at `data/deploy_articles.json` when it exists, then fall back to the smaller sample seed set.
It will also bootstrap the source monitor from `data/deploy_source_health.json` when that snapshot is available.
You can refresh that bundled snapshot from your local SQLite store before deploying with:

```bash
.venv/bin/python scripts/export_deploy_snapshot.py --limit 60
```

The export keeps the original article summaries when available, clears the heavier article body field to keep the bundle compact, and also writes a source-health snapshot for the production monitor UI.

The scheduled GitHub Actions ingest workflow now runs this export automatically after each ingest cycle and commits refreshed deploy snapshots back to `main` when they change. That push then flows through the normal regression and Vercel deploy workflows.


## Notes

- The seed dataset uses sample stories from `data/sample_articles.json` so the UI is not empty on first launch.
- Live ingestion uses a mix of RSS feeds and structured-data parsing for Eventbrite pages to improve Singapore event coverage without a private API.
- The GitHub Actions workflow uploads the generated SQLite database and vector-store files as build artifacts. It does not commit them back to a repository.
