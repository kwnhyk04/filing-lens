# Deploy

How FilingLens runs in production: the web on Vercel, the API on this PC behind FilingLens's own Tailscale Funnel node. The plan and its status are in `docs/todo.md` (step 10); the decisions are in `docs/memory.md`.

## What runs where

- **Web:** a Vercel project with Root Directory `web`, functions in `hkg1` (`web/vercel.json`), and deploys from `main` only. Its server routes call the API with the server-only `API_KEY`; the browser never calls the API.
- **API:** the compose project `filinglens-prod` on this PC: `infra/docker-compose.yml` with `infra/docker-compose.prod.yml` on top, settings in `.env.prod`. It runs CI's GHCR images by `sha-<7>` tag, never `latest`, and publishes no host port.
- **Public path:** `https://filinglens.<tailnet>.ts.net` (443), then the `tailscale` container's Funnel, then `http://api:4100` (`infra/tailscale/serve.json`). Nothing else is reachable from outside.
- **Networks:** Postgres, Redis and RabbitMQ sit on `data`, which has no route out, and `edge` joins the api to the tailscale container alone. The api and the tailscale container reach the internet only through the egress proxy (below). The workers (`ingest` and `embed`) sit behind the `ingest` profile and stay off: serving needs only the api. When they run, `ingest` keeps `default`, a direct route, for SEC (todo.md).
- **Database:** `corpus-v1`, restored once: revision 0008, 30 companies, 30 indexed 10-Ks, 11,263 chunks with model A vectors in `embedding`, 856,438 facts. Never upgrade it past 0008: the head (0006) runs the embedding swap.
- **Models:** Claude Haiku 5.5 writes answers first, on prepaid credits, within its limits: 1,052 tokens out per call, no prompt that could pass 100,000 tokens, `CLAUDE_DAILY_TOKEN_BUDGET` a day. Then Gemini 3.5 Flash-Lite, then NVIDIA gpt-oss-20b. Groq gpt-oss-20b routes.
  - Claude is off for good once its credits are gone, after a rejected key or model, and from `ANTHROPIC_CREDITS_EXPIRE` (2026-11-10).
  - It sits out a single answer on a 429, and while its day's budget is used up.
- **Not yet:** monitoring and alert delivery stay off in production (todo.md). Until the egress proxy is rolled out (steps 30 to 36), the api and tailscale containers can still reach services on the PC's own ports through `host.docker.internal` (`docs/context.md`, Known Limitations).

## Egress proxy

```
tailscale --edge--> api:4100                                          (Funnel's target)
api       --outbound, 10.231.232.2--> egress-proxy:3128 --egress--> the model providers
tailscale --outbound, 10.231.232.3--> egress-proxy:3129 --egress--> Tailscale, Let's Encrypt
```

Docker Desktop lets any container on a routed network reach the PC's own listeners at `host.docker.internal` (192.168.65.254). So the api and the tailscale container sit on internal networks only (`data`, `edge`, `outbound`), and `egress-proxy` (squid, `infra/squid/squid.conf`) is the only container on a routed one. The design is FreightAudit's:

- HTTPS CONNECT to port 443 only; nothing cached; no published port.
- Every loopback, private, link-local, CGNAT and other non-public destination is refused before any allowlist, by each address a name resolves to, so `host.docker.internal` is refused like 192.168.65.254.
- Names only: `dstdomain -n` never matches a bare IP address.
- One port per client, and each port serves only its client's fixed address on `outbound` (10.231.232.0/28; other containers get .8 to .15), so a compromised api cannot use tailscale's way out.
- CI builds the image from `infra/squid/Dockerfile` (`ubuntu:24.04` by digest and Ubuntu's newest squid from noble-security, never older than 6.14-0ubuntu0.24.04.4) and publishes `filinglens-squid` with the same `sha-<7>` tags as the api, so one `IMAGE_TAG` pins all three images. Dependabot's base-digest updates rebuild it with new fixes.

| Port | Client | Allowed hosts | Why |
| --- | --- | --- | --- |
| 3128 | api | `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.groq.com`, `integrate.api.nvidia.com` | The models production calls: Claude first, then Gemini, then NVIDIA; Groq routes |
| 3129 | tailscale | `controlplane.tailscale.com` | The control plane |
| 3129 | tailscale | the relays, by `^derp[0-9]+[a-z]*[.]tailscale[.]com$` | With no UDP out, all traffic rides a relay, Funnel's included. tailscaled measures every region's relays (FreightAudit's node asked for 87 names in 28 regions), so one pattern covers any that Tailscale adds |
| 3129 | tailscale | `acme-v02.api.letsencrypt.org` | Funnel's certificate, issued and renewed on the node; without it the certificate expires |

- Not allowed: Tailscale's log server (`TS_TAILSCALED_EXTRA_ARGS=--no-logs-no-support` turns the upload off), Hugging Face (models load offline), SEC (only the ingest worker fetches it), OpenRouter and Ollama (not used in production).
- The api's model clients read `HTTPS_PROXY` and `NO_PROXY` themselves (httpx, and the Anthropic SDK); its internal services stay direct.
- **Change the allowlist** in `infra/squid/squid.conf` and its test, `infra/tests/test_egress.py`, by pull request. After the merge and a `git pull` here: `docker restart filinglens-prod-egress-proxy-1`, which reads the mounted file again and needs no `.env.prod`.
- **Read its log:** `docker logs filinglens-prod-egress-proxy-1 | Select-String TCP_DENIED` lists refusals, and `Select-String CONNECT` the tunnels. A tunnel's line appears only when it closes, seconds later. The healthcheck adds two `NONE_NONE/000` lines every 10 s.

## Settings

You enter every value yourself; Claude Code never reads `.env.prod`. Make each secret in your own PowerShell window:

```powershell
node -e "console.log(require('node:crypto').randomBytes(32).toString('base64url'))"
```

It prints 43 URL-safe characters with no `$`.

### `.env.prod` (repo root; git ignores it)

| Name | Value |
| --- | --- |
| `COMPOSE_FILE` | `infra/docker-compose.yml;infra/docker-compose.prod.yml` |
| `COMPOSE_PATH_SEPARATOR` | `;` (Windows' default, made explicit) |
| `COMPOSE_PROFILES` | empty; `ingest` only to run the workers |
| `IMAGE_TAG` | `sha-<7>` of the deployed main commit, never `latest`. Compose stops without it |
| `TS_AUTHKEY` | a one-off key tagged `tag:filinglens` (step 6); delete the line after the first login (step 16) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | a new password |
| `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | a new password |
| `GRAFANA_ADMIN_PASSWORD` | required although monitoring stays off: compose checks required variables before it applies profiles |
| `SEC_USER_AGENT` | required for the same reason (the workers): your tool name and contact |
| `API_KEY` | new, 32+ characters; the same value goes to Vercel |
| `ADMIN_API_KEY` | new, 32+ characters, different from `API_KEY`; never on Vercel |
| `RETRIEVAL_EMBEDDING_COLUMN` | `embedding`: the corpus is at 0008 with model A. Compose stops without it |
| `AI_ENABLED` | `false` until step 29 |
| `DAILY_AI_TOKEN_BUDGET` | `300000`: about 55 textual answers a day, and it leaves room in Groq gpt-oss-20b's 200K a day for CI. It counts the free models in this stack's Redis only |
| `LLM_PRIMARY` | `anthropic:claude-haiku-5-5`: Claude answers first |
| `LLM_ANSWER_FALLBACK` | `gemini:gemini-3.5-flash-lite`: the free chain behind Claude |
| `LLM_ROUTER`, `LLM_FALLBACK`, `LLM_MAX_INFLIGHT`, `LOG_LEVEL` | leave out for the defaults: Groq routes, NVIDIA last, 4 answers at once, `INFO` |
| `ANTHROPIC_API_KEY` | FilingLens's Anthropic key; here only, never on Vercel |
| `ANTHROPIC_CREDITS_EXPIRE` | `2026-11-10`: Claude is off for good from that day (UTC) |
| `CLAUDE_DAILY_TOKEN_BUDGET` | `1500000`: at most $0.75 a day, FilingLens's $15 share over the days to 2026-11-10. It counts this stack's Redis only; the dev api and the local `--claude-primary` evals count apart |
| `GEMINI_API_KEY` | a key from FilingLens's own Google project, billing off (step 28); empty until then, which AI off allows |
| `GROQ_API_KEY`, `NVIDIA_API_KEY` | the dev keys (same quotas) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty (telemetry off) |

Not in `.env.prod`:
- `API_PORT`: it stays 4100, which `serve.json` names.
- `HF_HOME`: set machine-wide (`H:\.cache\huggingface`); the api mounts it read-only.
- The database, Redis and broker URLs: compose builds them.
- Host ports, `OPENROUTER_API_KEY`, `OLLAMA_URL`, `LLM_JUDGE`, `SEC_CACHE_DIR`, and the web's four.

With `AI_ENABLED=true`, the api refuses to start while a role's key is missing, and its log names the variable: Claude needs `ANTHROPIC_API_KEY`, Gemini `GEMINI_API_KEY`, the router `GROQ_API_KEY` and the last fallback `NVIDIA_API_KEY`.

### Vercel (Production scope only)

| Name | Value |
| --- | --- |
| `API_URL` | `https://filinglens.<tailnet>.ts.net` |
| `API_KEY` | Sensitive; the same value as in `.env.prod` |
| `SESSION_SECRET` | Sensitive; new for production, from the one-liner above |
| `LOGIN_PASSWORD_HASH` | Sensitive; from `npm --prefix web run hash-password`, pasted without the single quotes it prints |

## Commands

Run every command from the repo root with `--env-file .env.prod`; its `COMPOSE_FILE` names both compose files. Never point `make migrate` or `make corpus-restore` at production: both use `.env`, the dev stack.

## Steps

### Anytime

1. **GHCR packages public.** GitHub → your profile → Packages → `filinglens-api` → Package settings → Danger Zone → Change visibility → Public → type `filinglens-api` → confirm. Repeat for `filinglens-ingest`, and for `filinglens-squid` once CI has published it (step 31). **This cannot be undone.**
2. **Tailscale access controls.** Admin console → Access controls:
   - add `"tag:filinglens": ["autogroup:admin"]` to `tagOwners`;
   - add `{"target": ["tag:filinglens"], "attr": ["funnel"]}` to `nodeAttrs` (or add the tag to FreightAudit's funnel entry);
   - copy any rule that limits what `tag:freightaudit` may reach to `tag:filinglens`;
   - Save.
3. **Vercel account** (Hobby), signing up with GitHub.
4. **Optional, so the backend stays up:** Windows never sleeps on AC power; Docker Desktop → Settings → General → "Start Docker Desktop when you sign in". Docker Desktop starts only after you sign in to Windows.

### After 10a, 10b and 10c merge

5. The merge commit's GitHub status is green, and both packages' pages list `sha-<7>` for it.
6. Tailscale admin → Settings → Keys → Generate auth key: Reusable off, Ephemeral off, Pre-approved on (if device approval is on), Tags `tag:filinglens`, expiry 1 day.
7. Create `.env.prod` at the repo root with the table's names: `IMAGE_TAG=sha-<7>`, `AI_ENABLED=false`, `TS_AUTHKEY`, `RETRIEVAL_EMBEDDING_COLUMN=embedding`, the model rows, and new values for both store passwords, `GRAFANA_ADMIN_PASSWORD`, `API_KEY` and `ADMIN_API_KEY`.
8. `docker volume create filinglens-prod-tailscale-state`
9. `docker compose --env-file .env.prod pull`
10. Start Postgres alone: `docker compose --env-file .env.prod up -d postgres`. Then run `docker compose --env-file .env.prod ps postgres` until it shows `(healthy)`.
11. `(Get-FileHash .cache\corpus\corpus-v1.dump -Algorithm SHA256).Hash` must print `50FAA04AA39BC16B622235EBC33F223D86A9DBA870D38365870BF057BC6A52C0`.
12. Restore the dump. Run the three commands in this order, before anything else starts:
    ```powershell
    docker cp .cache\corpus\corpus-v1.dump filinglens-prod-postgres-1:/tmp/corpus.dump
    docker exec filinglens-prod-postgres-1 pg_restore --exit-on-error --single-transaction --no-owner --no-privileges --dbname=postgresql:/// /tmp/corpus.dump
    docker exec filinglens-prod-postgres-1 rm -f /tmp/corpus.dump
    ```
13. Check the restore. Expect `0008`, `11263` and `30`:
    ```powershell
    docker exec filinglens-prod-postgres-1 psql -At -c "select version_num from alembic_version" -c "select count(*) from chunks" -c "select count(*) from filings where status = 'indexed'"
    ```
14. Start the rest: `docker compose --env-file .env.prod up -d`. In `docker compose --env-file .env.prod ps`, postgres, redis, rabbitmq, api and tailscale should all show `(healthy)`, and egress-proxy too once `main` has it.
15. Search once, with no model call. The key stays inside the container. Expect `200`, which also proves the read-only api loads its models:
    ```powershell
    docker exec filinglens-prod-api-1 python -c "import os, urllib.request as u; r = u.Request('http://127.0.0.1:4100/v1/search?q=supply+chain+risk&limit=3', headers={'X-API-Key': os.environ['API_KEY']}); print(u.urlopen(r, timeout=60).status)"
    ```
16. Check Funnel: `docker exec filinglens-prod-tailscale-1 tailscale --socket=/tmp/tailscaled.sock funnel status` should show Funnel on for `https://filinglens.<tailnet>.ts.net`, proxying to `http://api:4100`. Then delete the spent `TS_AUTHKEY` line from `.env.prod`.
17. Public checks from the PC. They go through the public path, since the PC has no Tailscale client. A new Funnel name can take up to about 10 minutes to resolve.
    - `curl.exe -si https://filinglens.<tailnet>.ts.net/healthz`: 200 `{"status":"ok"}`.
    - `curl.exe -si https://filinglens.<tailnet>.ts.net/v1/companies`: 401, `www-authenticate: APIKey`, `"code":"unauthorized"`.
    - `curl.exe -si -X POST https://filinglens.<tailnet>.ts.net/graphql -H "Content-Type: application/json" --data "{}"`: 401.
    - `curl.exe -si https://filinglens.<tailnet>.ts.net/docs`: 404.
    - `curl.exe -si https://filinglens.<tailnet>.ts.net/v1/companies -H "Origin: https://example.org"`: 403.
    - `docker ps --filter label=com.docker.compose.project=filinglens-prod --format "{{.Names}}\t{{.Ports}}"`: no `127.0.0.1:` or `0.0.0.0:` binding.
18. Vercel → Add New → Project:
    - import `kwnhyk04/filing-lens`, and let the Vercel GitHub App see only that repo;
    - Framework Next.js; Root Directory → Edit → `web`; defaults otherwise, no variables yet;
    - Deploy. The build needs no variables; its pages fail until step 20.
19. Vercel project Settings:
    - **Build and Deployment:** "Include files outside the root directory in the Build Step" on (the web imports `../clients/ts`); Node.js Version 24.x.
    - **Functions:** the region shows `hkg1`.
    - **Deployment Protection:** Vercel Authentication on, Standard Protection.
    - **Security:** Git Fork Protection on.
20. Settings → Environment Variables: add the four of the Vercel table, Production scope only, the three secrets as Sensitive. Then Deployments → the latest → ⋮ → Redeploy.
21. Firewall → New Rule:
    - Name `sign-in rate limit`.
    - If Request Path equals `/login` and Method equals `POST`.
    - Then Rate Limit: fixed window, 60 s, 10 requests, key IP, 429 when exceeded. It backs the per-instance sign-in limiter (5 attempts per 15 minutes).
    - Review → Publish.
22. Share only `https://<project>.vercel.app`. Check that the build log shows Node 24.x and the deployment summary shows `hkg1`.
23. From now on, after each merge, confirm the deploy from the merge commit's GitHub status.
    - **A merge that changes the API** (`services/api` or `packages`) goes to the PC right away: `git pull` on `main`, `IMAGE_TAG` set to its `sha-<7>`, then `docker compose --env-file .env.prod pull api egress-proxy` and `docker compose --env-file .env.prod up -d --wait api`. Vercel ships the web on merge, and a web that asks for something the running API lacks reads the API as offline (`web/lib/errors.ts`). After #31 (2026-10-25) the web asked for `totals` while the PC still ran `sha-41ac308`.

### Phone test with AI off

Phone on cellular data, Wi-Fi off.

24. Open the production domain: the landing page, with no sign-in. "Try the live demo" goes to `/login`. One wrong password shows "Wrong password."; the right one opens Ask (`/ask`), which proves `crypto.argon2` on Vercel's Node.
25. Check the live pages:
    - Coverage: 30 companies on 2 pages, with Indexed pills.
    - Ask: a question gets the switched-off message, with no model call.
    - `/demo` works, and Sign out returns to `/login`.
    - In the phone's browser, `https://filinglens.<tailnet>.ts.net/v1/companies` shows the 401 problem.
26. PC off:
    - On the PC: `docker compose --env-file .env.prod stop tailscale`.
    - On the phone, reload `/ask`. Within about 5 s it lands on `/demo?offline=1` with the offline banner, and Ask says "The API is offline right now." The landing page at `/` stays as it was: it calls no API.
    - On the PC: `docker compose --env-file .env.prod start tailscale`. Reload: the page is live again.
27. API down, PC on: `docker compose --env-file .env.prod stop api` gives the same demo fallback (Funnel's 502). Then `docker compose --env-file .env.prod start api`.

### Before AI on

28. Create FilingLens's own Gemini key: Google AI Studio → Get API key → Create API key → in a new project for FilingLens, with no billing account linked, so the free tier applies. Put it in `.env.prod` as `GEMINI_API_KEY` yourself. The dev key shares Triage Copilot's project quota.

### AI on: the first live test (your go)

29. Turn AI on and ask exactly two questions:
    - Set `AI_ENABLED=true` in `.env.prod`, then run `docker compose --env-file .env.prod up -d api`, which recreates only the api.
    - On the phone, signed in at the production domain, ask n01, then x04. Each draft should grow in pieces; if one arrives all at once, note it (Funnel buffering).
    - Run the usage check below.

**The questions:** n01 "What was Apple's total revenue in fiscal 2025?" and x04 "What are Amazon's reportable segments?".

**Every live call it makes** (nothing else in production calls a model or SEC: no worker runs, Hugging Face is offline, telemetry is off). Tokens come from the 2026-10-17 thinking-off test runs of n01 and x04 (`evals/reports/runs/20261017T082950Z` and `T084716Z`); prices from `evals/providers.json` (Haiku: $0.10 per million input tokens and $0.50 per million output, for prompts up to 100,000 tokens).

| # | Call | Model | Tokens in / out | Billed |
| --- | --- | --- | --- | --- |
| 1 | n01 router | groq `openai/gpt-oss-20b` | ~1,030 / ~80 | $0 |
| 2 | n01 answer | anthropic `claude-haiku-5-5` | ~450 / ~155 | ~$0.0001 of credits |
| 3 | x04 router | groq `openai/gpt-oss-20b` | ~1,030 / ~70 | $0 |
| 4 | x04 answer | anthropic `claude-haiku-5-5` | ~7,670 / ~165 | ~$0.0009 of credits |

- **Expected:** about 10,700 tokens and about $0.001 of credits. Claude: 2 calls, about 8,450 of its 1,500,000 tokens a day. Groq: about 2,200 of gpt-oss-20b's 200K a day.
- **Only on a condition:**
  - a second router call when the reply names an untracked ticker or a comparison without a metric (~1,030 / ~75);
  - one more Claude call per answer that fails validation, at most 1,052 tokens out;
  - Gemini, then NVIDIA, in place of a Claude call that fails: Gemini about 330 / 60 for n01 and 5,040 / 270 for x04, $0 billed.
- **Worst case:** both answers regenerate on Claude at its cap: about 16,250 tokens in and 4,210 out, about $0.0037 of credits.
- **Stop rule:** ask exactly these two. Stop at the first error, unexpected refusal or fallback; a fallback means Claude did not answer. No retry. Then read:
  - `docker compose --env-file .env.prod logs api --since 15m`;
  - `docker exec filinglens-prod-redis-1 redis-cli HGETALL ai:claude:off` (empty while Claude is on).
- **Usage check** (`<UTC date>` such as `2026-10-30`):
  - `docker exec filinglens-prod-redis-1 redis-cli HGETALL ai:claude:<UTC date>`: `calls` 2 and `tokens` near 8,450;
  - `docker exec filinglens-prod-redis-1 redis-cli HGETALL ai:usage:<UTC date>`: `calls` 2 (the router), `tokens` near 2,200, and no `fallbacks`. Claude's tokens leave this counter.

### Egress proxy rollout: the first deploy after its PR merges

Production reads the compose file and `infra/squid/squid.conf` from this checkout, so deploy only with `main` checked out. Once `main` holds the proxy, every deploy runs it; this first one also checks it.

30. Record what runs now, for the rollback and the comparison:
    - `docker inspect --format "{{.Config.Image}}" filinglens-prod-api-1` and `git rev-parse --short HEAD`;
    - ten public requests: ``1..10 | ForEach-Object { curl.exe -s -o NUL -m 30 -w "%{http_code} tls=%{time_appconnect} total=%{time_total}`n" https://filinglens.<tailnet>.ts.net/healthz }``;
    - `docker exec filinglens-prod-tailscale-1 tailscale --socket=/tmp/tailscaled.sock netcheck`: whether the node has UDP now, and its nearest relay.
31. The merge commit's CI is green, and GitHub's Packages list its `sha-<7>` for `filinglens-api`, `filinglens-ingest` and `filinglens-squid`. Make `filinglens-squid` public as in step 1 (**it cannot be undone**; the image holds only Ubuntu and squid, and its config is mounted from the public repo).
32. `git switch main`, then `git pull --ff-only`. In `.env.prod`: `IMAGE_TAG=sha-<7>` of the merge commit.
33. `docker compose --env-file .env.prod pull api egress-proxy`, then `docker compose --env-file .env.prod up -d --wait egress-proxy api tailscale`. This creates `filinglens-prod_edge`, `filinglens-prod_outbound` and `filinglens-prod_egress`, starts the proxy and recreates the api and the tailscale container; the stores keep running.
34. Checks, in this order:
    - `docker compose --env-file .env.prod ps`: egress-proxy, api and tailscale `(healthy)`.
    - `docker inspect --format '{{.Name}}: {{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' filinglens-prod-api-1 filinglens-prod-tailscale-1 filinglens-prod-egress-proxy-1`: the api on `data`, `edge` and `outbound`; tailscale on `edge` and `outbound`; the proxy on `egress` and `outbound`, each with the `filinglens-prod_` prefix.
    - Funnel: step 16's `funnel status`, then step 17's public checks. Allow a minute while tailscaled picks a home relay.
    - On the phone, signed in: Ask is live, not the offline demo. Ask n01; the draft should grow in pieces.
    - `docker logs filinglens-prod-egress-proxy-1 | Select-String CONNECT`: `TCP_TUNNEL/200` for `api.groq.com:443` and `api.anthropic.com:443` from 10.231.232.2, and for Tailscale's hosts from 10.231.232.3.
    - `docker logs filinglens-prod-egress-proxy-1 | Select-String TCP_DENIED`: nothing. If tailscaled asks for another host, report it; never allow a bare IP address.
    - Gemini's and NVIDIA's routes, with no key and no model call. Each prints an HTTP status, and the log shows a tunnel for each:
      `docker exec filinglens-prod-api-1 python -c "import httpx; [print(h, httpx.head('https://' + h, timeout=10).status_code) for h in ('generativelanguage.googleapis.com', 'integrate.api.nvidia.com')]"`
    - The PC's own ports are closed to the api: every result is non-zero. 10.231.232.1 is `outbound`'s gateway, which FreightAudit never probed:
      `docker exec filinglens-prod-api-1 python -c "import socket; socket.setdefaulttimeout(2); [print(h, p, socket.socket().connect_ex((h, p))) for h in ('192.168.65.254', '10.231.232.1') for p in (5433, 6380, 5672, 15672, 135, 445, 3389)]"`
    - `docker exec filinglens-prod-api-1 python -c "import socket; socket.create_connection(('host.docker.internal', 5433), 3)"` fails with `gaierror`.
    - Through the proxy, a `403 Forbidden`: `docker exec filinglens-prod-api-1 python -c "import socket; s = socket.create_connection(('egress-proxy', 3128), 5); s.sendall(b'CONNECT host.docker.internal:443 HTTP/1.1\r\nHost: x\r\n\r\n'); print(s.recv(40))"`
    - The ten public requests and `netcheck` again; expect `UDP: false`.
35. Roll back (Rollback, Egress proxy) if Funnel's `/healthz` is not 200 within 10 minutes, the phone lands on the offline demo, an answer fails, or any request now takes over 5 s (the web's page timeout) where none did before.
36. A day later: `docker stats --no-stream filinglens-prod-egress-proxy-1` stays well under its 256 MB, and the denial check shows only step 34's own probe. The before and after numbers go to the activity log.

## Rollback

- **Public kill switch** (seconds): `docker compose --env-file .env.prod stop tailscale`. The web serves the demo; `start tailscale` undoes it.
- **AI off:** set `AI_ENABLED=false` in `.env.prod`, then `docker compose --env-file .env.prod up -d api`. Ask shows the switched-off message, and no model is called.
- **Claude only off:** set `LLM_PRIMARY=gemini:gemini-3.5-flash-lite` and an empty `LLM_ANSWER_FALLBACK`, then `docker compose --env-file .env.prod up -d api`. Answers then run on the free chain alone.
- **Backend image:** set `IMAGE_TAG` back to the previous `sha-<7>` (the activity log records each deployed tag), then `docker compose --env-file .env.prod pull api egress-proxy` and `docker compose --env-file .env.prod up -d api`. No `filinglens-squid` image exists before the egress proxy's merge commit, so going back past it needs the egress proxy's rollback as well; the pull fails first and changes nothing.
- **Egress proxy** (about 2 minutes, back to the networks before it):
  1. `git checkout <commit from step 30> -- infra/docker-compose.prod.yml`. The checkout stays changed until a revert or fix merges; then `git checkout -- infra/docker-compose.prod.yml` and `git pull`.
  2. Keep `IMAGE_TAG`: the proxy's PR changed no app code, and an image older than `sha-c5282a1` breaks today's web.
  3. `docker compose --env-file .env.prod up -d --wait api tailscale`: both are back on `data` and `default`.
  4. By exact name: `docker stop filinglens-prod-egress-proxy-1`, `docker rm filinglens-prod-egress-proxy-1`, then `docker network rm filinglens-prod_edge filinglens-prod_outbound filinglens-prod_egress`.
  5. Check `ps`, Funnel's `/healthz` and one question.
- **Web:** Vercel → the project → Instant Rollback.
  - Hobby rolls back only to the previous production deployment.
  - After a rollback, Vercel stops putting new main deploys on the domain until you Undo Rollback.
  - A rollback keeps the current variables; a variable change needs a Redeploy.
- **Data:** the database rebuilds from `corpus-v1`:
  1. `docker compose --env-file .env.prod down` (never `-v`).
  2. `docker volume rm filinglens-prod_postgres-data` (that volume only, by name).
  3. Steps 10 to 14 again.
- **Leaked key:**
  - API key: set a new `API_KEY` in `.env.prod` and on Vercel, then `docker compose --env-file .env.prod up -d api` and Redeploy on Vercel.
  - Tailscale node: Tailscale admin → Machines → `filinglens` → Remove, then a new auth key and steps 6 to 17.
  - Anthropic key: revoke it in the Anthropic console, then empty `ANTHROPIC_API_KEY` and take Claude off as above; with Claude still first and AI on, the api refuses to start without the key.
- **Whole step:** `docker compose --env-file .env.prod down`. The volumes stay, and the Tailscale state is external. The web stays on the demo.

## Never

- `docker compose down -v`, any prune, or anything on `freightaudit-prod`.
- `make migrate` or `make corpus-restore` against production: both use `.env`, the dev stack.
- An upgrade past revision 0008 (the head runs the embedding swap).
- `ANTHROPIC_API_KEY` or `ADMIN_API_KEY` on Vercel.
- A bare IP address in the egress proxy's allowlists, or an allowlist change outside a pull request and its test.
- A production compose command with another branch checked out: compose reads that branch's files.
