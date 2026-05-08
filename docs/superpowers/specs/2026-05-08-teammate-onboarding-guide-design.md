# Teammate Onboarding Guide — Design

**Date:** 2026-05-08
**Status:** Draft, awaiting user review
**Owner:** Khana Bazaar Developer

## 1. Goal

Produce a self-contained, idiot-proof onboarding guide that lets a non-technical teammate (Windows 10/11, no engineering background) install every required tool, clone the public KhanaBazaar repository, configure environment files, run the full stack with seeded demo data, and demo the platform across admin, seller, and customer roles without needing live help from the author.

The guide must remain readable on its own — a teammate Slacked the URL of `docs/teammate-guide/README.md` should be able to reach a working demo using only that page and the chapters it links to. No reference to the engineer-flavoured `README.md` or `docs/local_setup.md` is required for completion (those remain authoritative for engineers and may be cross-linked, never inlined).

## 2. Audience & assumptions

- **Operating system:** Windows 10 or Windows 11 only. macOS / Linux paths intentionally omitted to keep the guide focused.
- **Hardware:** 8 GB RAM minimum, 20 GB free disk, x86_64 CPU with virtualisation enabled in BIOS (the guide includes a section on enabling it).
- **Skill floor:** Can use a web browser, can install applications, can copy and paste text. Has never opened a terminal, does not know what an environment variable is, has never used Git.
- **Network:** Reasonable home or office internet. Indian-market network conditions assumed (slow downloads, occasional proxy interference, payment gateways that reject some international cards).
- **Repo access:** KhanaBazaar repository is public on GitHub. Teammates do **not** need a GitHub account, SSH key, or personal access token. Plain `git clone` over HTTPS works.

## 3. Non-goals

- macOS and Linux setup paths.
- Native PowerShell / Windows-without-WSL setup. WSL2 is mandatory.
- Replacing or duplicating the engineer-facing `docs/local_setup.md` and `docs/development_guide.md`. Those stay as-is.
- Teaching teammates to write code, open pull requests, or run tests.
- Production deployment guidance (already covered in `docs/azure_deployment.md`).
- Exhaustive coverage of every backend route — only the demo flows that matter for the role-tour script.

## 4. Approach

A new top-level documentation directory `docs/teammate-guide/` containing nine numbered chapter files plus two appendices. The directory is self-contained: a teammate landing on `docs/teammate-guide/README.md` (which doubles as chapter 00) navigates linearly via "Previous / Next" footers to reach a working demo, then uses chapters 6 and 7 as reference material on later days.

Each chapter is written for first-time installation. Length is uncapped — completeness over brevity. Every command is shown with its execution context, expected output, expected wait time, and inline first-line troubleshooting. Deeper failure modes link to chapter 6.

### 4.1 File layout

```
docs/teammate-guide/
├── README.md                  # = chapter 00 — start here / cover page
├── 01-install-tools.md        # WSL2, Docker Desktop, Git, Node, Python, uv
├── 02-clone-and-env.md        # clone repo, copy & edit .env files, generate secrets
├── 03-google-maps-keys.md     # GCP signup, billing, two API keys, paste into env
├── 04-first-run.md            # docker up, migrate, seed, dev.sh start, verify URLs
├── 05-demo-logins.md          # seeded accounts, OTP-via-log flow, role tour script
├── 06-troubleshooting.md      # symptom-indexed failure catalogue
├── 07-daily-use.md            # day-2+ start/stop/update workflow
├── appendix-mobile-ngrok.md   # optional phone-testing flow
├── appendix-glossary.md       # plain-English term definitions
└── images/                    # placeholder folder for screenshots (added later)
```

### 4.2 Navigation

- Every chapter starts with a breadcrumb line: `Teammate Guide > Chapter N: Title` and an "Estimated time" callout.
- Every chapter ends with a footer linking previous / next chapters and back to `README.md`.
- Cross-links use relative paths (`./06-troubleshooting.md#docker-wont-start`).
- Each troubleshooting entry has a stable anchor matching its keyword so other chapters can deep-link (`./06-troubleshooting.md#port-3000-in-use`).
- `README.md` is the cover page; opening the bare directory URL on GitHub renders it automatically.

### 4.3 Voice & style rules (apply to every chapter)

- Plain English at roughly grade-8 reading level. Short sentences.
- Second person ("you"), imperative mood ("Click Next", not "Next should be clicked").
- Banned words: "just", "simply", "obviously", "easy".
- Every command lives in a fenced code block on a single line, copy-paste ready.
- Every command is preceded by a bold execution-context line: `**Run in: WSL2 Ubuntu terminal**`, `**Run in: PowerShell (as Administrator)**`, or `**Click in: web browser**`.
- Every command is followed by an "**What you should see:**" block showing the real expected output (3-10 lines, truncated only with `...` markers).
- Every command states a typical wait time when it exceeds 10 seconds: `*This takes about 2-5 minutes on a fast connection.*`.
- After every command, a short "If it fails:" sentence pointing to the relevant troubleshooting anchor.
- Jargon gets a short analogy on first use, plus a glossary link: "Docker is like a sealed lunchbox — the app and its tiny kitchen come together so it runs the same on every laptop. ([more](./appendix-glossary.md#docker))".
- Glossary terms italicised on first use per chapter, linked to glossary anchor.
- Screenshots are written as placeholders: `[Screenshot: Docker Desktop install wizard, "Use WSL 2 instead of Hyper-V" checkbox highlighted]`. Real images get added to `docs/teammate-guide/images/` later — guide is text-complete without them.

## 5. Per-chapter content

### 5.1 `README.md` (chapter 00 — Start Here)

- One-paragraph description of KhanaBazaar in plain English: "an online grocery and food marketplace for Indian neighbourhoods, where shop owners list what they have and customers nearby order through the app."
- "What you'll have at the end" bullet list: full app running on your laptop, demo accounts to log in as admin / seller / customer, ability to stop and restart the app on later days.
- Total time estimate: roughly 90 minutes the first time, around 5 minutes on subsequent days.
- Pre-flight checklist: Windows 10/11, 8 GB RAM, 20 GB free disk, admin rights on the machine, virtualisation enabled in BIOS (link to chapter 1's enable-virtualisation section), stable internet for ~3 GB of downloads.
- Numbered chapter index, each with one-line "you'll do X" summary.
- "If you get stuck" callout pointing at chapter 6 plus a Slack-style "what to send your engineer" template.
- Optional appendices listed at the bottom.

### 5.2 `01-install-tools.md` (Install your tools)

Each tool gets four sub-sections: **What it is** (one short paragraph with analogy), **Install steps** (numbered, click-by-click), **Verify it worked** (one terminal command and expected output), **If it fails** (inline 2-3 most common causes plus link to chapter 6).

Tools in install order:

1. **BIOS virtualisation check.** Many Indian-market laptops ship with virtualisation off. Steps to open Task Manager → Performance → CPU → check "Virtualization: Enabled". If disabled: reboot, enter BIOS (vendor-specific F2 / F10 / Del), enable VT-x / SVM, save and exit. Cover Lenovo, HP, Dell, Asus key combinations.
2. **WSL2 with Ubuntu.** `wsl --install` in PowerShell (as Administrator), restart, set Ubuntu username and password (explain it is *not* the Windows password, must be lowercase, password is invisible while typing — that is normal).
3. **Docker Desktop for Windows.** Direct download URL from docker.com, installer wizard with the "Use WSL 2 instead of Hyper-V" checkbox callout, first-run sign-in skipped, Settings → Resources → WSL Integration → Ubuntu toggle on, Apply & Restart.
4. **Windows Terminal** (optional polish — explains how to pin Ubuntu as default profile).
5. **Git inside Ubuntu.** `sudo apt update && sudo apt install -y git`. Explains `sudo` (run as administrator), `apt` (Ubuntu's app store), `-y` (say yes to prompts).
6. **Node.js 20 via nvm.** `nvm` install via curl one-liner, restart shell, `nvm install 20`, `nvm use 20`. Explains why we use nvm (lets you switch versions later) instead of `apt install nodejs` (ships an old version).
7. **Python 3.12.** Ubuntu 24.04 ships with 3.12 already; verify with `python3 --version`. If 22.04 or older: `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv`.
8. **uv** (Python package manager). `curl -LsSf https://astral.sh/uv/install.sh | sh`, restart shell.
9. **Final verification block.** Single fenced code block running `wsl --version`, `docker --version`, `git --version`, `node --version`, `python3 --version`, `uv --version` with all expected outputs. If any fail, link to relevant section.

Cross-cutting concerns explicitly addressed in this chapter:
- Slow connections / hostel networks — what timeouts look like, how to retry.
- Antivirus (Quick Heal, K7, Norton) blocking Docker installer — how to whitelist.
- Corporate / college proxy — how to set `HTTP_PROXY` and `HTTPS_PROXY` in WSL.
- Reboot prompts — explicit "save your work and restart now" callouts after WSL install and Docker install.

### 5.3 `02-clone-and-env.md` (Get the code and configure secrets)

1. Open Ubuntu terminal. Make a project folder: `mkdir -p ~/projects && cd ~/projects`. Explain `~` (home folder) and `cd` (change directory).
2. Clone the repo: `git clone https://github.com/rishimule/KhanaBazaar.git`. Explain "cloning" as "downloading a folder along with its full edit history".
3. Enter the repo: `cd KhanaBazaar`.
4. Copy the example env files:
   ```
   cp backend/app/.env.example backend/app/.env
   cp frontend/.env.example   frontend/.env.local
   ```
   Explain what an *environment variable* is (a setting the app reads at startup, kept outside the code so secrets do not leak).
5. Generate the two secrets:
   - `python3 -c "import secrets; print(secrets.token_hex(32))"` — copy output, this is `JWT_SECRET`.
   - `python3 -c "import secrets; print(secrets.token_hex(16))"` — copy output, this is `OTP_PEPPER`.
   Explain in one paragraph what each secret is used for, in plain language.
6. Edit `backend/app/.env` with `nano` — line-by-line walkthrough of nano: arrow keys to move, type to edit, `Ctrl+O` to save (then `Enter` to confirm filename), `Ctrl+X` to exit. Show the exact two lines they should change. Critical instruction: replace the **entire value between the quotes** (the placeholder text `change-me-use-secrets-token-hex-32` must go), not just paste the new secret next to the placeholder. Show a before/after side-by-side. End-state should look like `JWT_SECRET="<their-real-hex-string>"`.
7. Note that `EMAIL_PROVIDER="console"` should stay as-is — explains that OTP codes will print to a log they can view in chapter 5.
8. Maps keys section: a clearly-marked "**Skip this if you do not need maps**" block. Tells them to leave `GOOGLE_MAPS_SERVER_API_KEY` and `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` blank for now and continue. Note that the backend `.env` also contains a `GOOGLE_MAPS_BROWSER_API_KEY` line — that one stays empty in this app's setup; only the frontend `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` is read at runtime. Forward link to chapter 3 for when they want maps.
9. Sanity check: `cat backend/app/.env` shows the file contents, JWT and OTP secrets are real hex strings (not the `change-me-...` placeholder text).

### 5.4 `03-google-maps-keys.md` (Optional: Google Maps API keys)

Top callout: "**Skip this chapter if you only need the core e-commerce demo.** The app falls back to manual address entry without maps. Come back here later when you want store distances, address autocomplete, and the map pin picker."

1. **What you are about to do.** Two-paragraph plain-English explanation: Google Maps is not free in production, but Google gives a generous monthly free tier that the demo will not exceed. You'll create a Google Cloud account, link a payment method (required even for free use), enable three APIs, create two keys, and lock each key down so it cannot be abused.
2. **Sign in to Google Cloud.** Visit `console.cloud.google.com`, sign in with a Google account.
3. **Create project "KhanaBazaar Dev".** Project picker → New Project → name → create.
4. **Enable billing.** Navigation → Billing → Link a billing account → Create billing account. Add payment method (Indian card or UPI). Explicit callout: **RuPay-only cards may be rejected**; use a Visa / Mastercard credit or debit card. Free trial with $300 credit may appear — accept it. Reassurance paragraph: Maps Platform also gives **$200 of free Maps usage every month** on top of any trial credit. The demo will not come close to using it.
5. **Set a budget alert.** Billing → Budgets & alerts → Create Budget → $5 → email alert at 50% / 90% / 100%. Reassures them they will get warned long before any real charge happens. Five dollars is a paranoia floor, not the actual free-tier ceiling.
6. **Enable the three APIs.** APIs & Services → Library → search for and Enable each:
   - **Maps JavaScript API** — renders the map in the browser.
   - **Places API** — address autocomplete suggestions.
   - **Geocoding API** — turning a typed address into latitude / longitude.
   Explanation per API: one short sentence on what it does in this app. Reinforce: do **not** enable other Maps APIs (Routes, Roads, Air Quality) — they bill separately and the app does not use them.
7. **Create the server key.**
   - APIs & Services → Credentials → Create Credentials → API key.
   - Rename to "khana-bazaar-server".
   - Application restrictions → leave at **None** for local dev. Plain-English explanation: home internet IP addresses change frequently, so locking the key to one IP just causes pain. The key only ever runs from your laptop right now; tightening this is a production concern.
   - API restrictions → Restrict key → tick **Places API** and **Geocoding API** only.
   - Save. Copy the key value.
8. **Create the browser key.**
   - Same Credentials page → Create Credentials → API key.
   - Rename to "khana-bazaar-browser".
   - Application restrictions → HTTP referrers → add `http://localhost:3000/*` and `http://127.0.0.1:3000/*` (trailing `/*` is required).
   - API restrictions → Restrict key → tick **only** Maps JavaScript API. Untick Places and Geocoding — the browser never calls those directly; they go through the backend.
   - Save. Copy the key value.
9. **Paste into env files.** Open `backend/app/.env`, replace `GOOGLE_MAPS_SERVER_API_KEY=""` line with the server key. Open `frontend/.env.local`, replace `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""` line with the browser key. Restart `dev.sh` after editing so the backend re-reads its env.
10. **Test each key.** Provided after chapter 4 runs the app — browser key works if the embedded map renders without a "For development purposes only" watermark; server key works if address autocomplete shows Indian suggestions when typing in the location chip. Cross-link to chapter 6 troubleshooting entries `RefererNotAllowedMapError`, `REQUEST_DENIED`, `For development purposes only`.
11. Cross-link to engineer doc `docs/google_maps_setup.md` for deeper detail (cost orientation §10, key rotation §11, local-dev shortcut §12).

### 5.5 `04-first-run.md` (Run the app for the first time)

1. **Start Docker Desktop.** Confirm whale icon in system tray, wait until "Docker Desktop is running" tooltip.
2. **Bring up Postgres and Redis.**
   ```
   cd ~/projects/KhanaBazaar
   docker compose up -d
   ```
   Wait time: 1–3 minutes first run while images download (around 400 MB total).
   Verify:
   ```
   docker compose ps
   ```
   Both services should show `Up` (or `healthy`). **Wait for Postgres to finish starting** before the next step — running migrations against a half-started database fails with `connection refused`. Plain-English wait test:
   ```
   docker compose exec postgres pg_isready -U postgres -d khanabazaar
   ```
   Repeat until it prints `accepting connections`.
3. **Install backend dependencies.**
   ```
   cd backend/app
   uv sync
   ```
   Wait time: 2–5 minutes first time. Subsequent runs are seconds.
4. **Build database tables.**
   ```
   uv run alembic upgrade head
   ```
   Plain-English explanation: this creates the empty tables in the database, ready to receive data.
5. **Load demo data.**
   ```
   uv run python scripts/seed_database.py
   ```
   Explanation: fills the database with sample products, stores, and the demo accounts they will use in chapter 5.
6. **Install frontend dependencies.**
   ```
   cd ../../frontend
   npm install
   ```
   Wait time: 2–4 minutes.
7. **Start everything with one command.**
   ```
   cd ..
   ./scripts/dev.sh start
   ```
   Explain what it starts (backend on 8000, Celery worker, frontend on 3000, log viewer on 8001) and that logs land in `.dev/logs/`.
8. **Verify in browser.** Open each URL and describe what they should see:
   - `http://localhost:3000` — KhanaBazaar storefront with stores listed.
   - `http://localhost:8000/docs` — Swagger API documentation page.
   - `http://localhost:8001` — Log viewer showing four tabs (backend, celery, frontend, ngrok).
9. **Stop the app for the day.**
   ```
   ./scripts/dev.sh stop
   ```
   Note Docker keeps running in background; that's fine.

Inline troubleshooting for: Docker not running, port 3000 already in use, port 5432 already in use, `uv sync` SSL cert error, `npm install` ETIMEDOUT, seed script crashing on duplicate data.

### 5.6 `05-demo-logins.md` (Demo accounts and login flow)

1. **How OTP login works in dev — three sentences.** Type your email → backend prints a 6-digit code to its log → paste the code on the login screen → you're in. No real email is sent in dev mode.
2. **Where the code appears.** Open `http://localhost:8001` (the log viewer started by `dev.sh`). Click the "backend" tab. After requesting an OTP, look for a line like `OTP for customer@khanabazaar.dev: 123456`. `[Screenshot: Log viewer with OTP highlighted]`.
3. **Demo accounts table.** All seeded accounts with role, email, and what they can demo. Sourced from `backend/app/src/app/db/dev_seed.py` (lines 51-61 for users, 132-176 for application states):
   | Role | Email | What they see / can do |
   |------|-------|-----------------------|
   | Admin | `admin@khanabazaar.dev` | Approve sellers, manage master catalog, see all orders |
   | Seller (approved) | `seller@khanabazaar.dev` | Manage own store inventory, see orders received |
   | Seller (approved) | `seller2@khanabazaar.dev` through `seller9@khanabazaar.dev` | Same as above, different stores |
   | Seller application (pending) | `pending.seller@khanabazaar.dev` | Stuck on "awaiting approval" screen |
   | Seller application (approved record) | `approved.seller@khanabazaar.dev` | Already-approved record — useful for admin tour |
   | Seller application (rejected record) | `rejected.seller@khanabazaar.dev` | Rejected record — useful for admin tour |
   | Customer | `customer@khanabazaar.dev` | Browse stores, add to cart, place orders |
4. **First login walkthrough — customer.** Step-by-step from clicking "Login" to landing on the home page. Click-level detail.
5. **Quick demo script: "Show this in 5 minutes".** A guided sequence:
   - Log in as customer → set delivery address → browse a store → add three items → checkout → place order.
   - Log out, log in as `seller@khanabazaar.dev` → see the order in the seller dashboard → mark it packed.
   - Log out, log in as admin → catalog tab to show master products → sellers tab → approve `pending.seller@khanabazaar.dev`.
6. **Page tour by role** — for each role, what every nav item does and what each button means. Long-form, not just a list.

### 5.7 `06-troubleshooting.md` (When things break)

Symptom-indexed reference. Top of page is a hyperlinked index keyed by error message keywords. Each entry follows the same shape: **What you see** (exact error quote), **Why it happens** (1–2 sentences), **How to fix** (numbered steps), **If the fix does not work** (next escalation).

Categories and entries (extracted from `docs/local_setup.md` §9, the codebase, and common Windows / WSL pain points):

**Install errors**
- `wsl --install` says "the requested operation requires elevation" — run PowerShell as Administrator.
- `wsl --install` fails with virtualisation error — enable VT-x / SVM in BIOS.
- Ubuntu app from Microsoft Store but `wsl` does not see it — set default version: `wsl --set-default-version 2`.
- Docker Desktop "WSL update failed" — run `wsl --update` in PowerShell, restart Docker.
- Antivirus blocking Docker installer — temporarily disable, install, re-enable.
- `sudo apt update` hangs / "Could not resolve archive.ubuntu.com" — DNS issue, set `/etc/resolv.conf` or fix proxy.
- `nvm: command not found` after install — restart the shell, or `source ~/.bashrc`.
- `uv: command not found` — same fix, restart shell to pick up PATH.

**Docker errors**
- `Cannot connect to the Docker daemon` — Docker Desktop not running, start it.
- Docker Desktop "WSL 2 backend not enabled" — Settings → General → "Use the WSL 2 based engine" → on.
- `docker compose up` says port 5432 in use — another Postgres is running. Either stop it (Services → PostgreSQL → Stop) or change the project's compose port mapping.
- Container crashes immediately — `docker compose logs postgres` to read why.
- Disk space low — `docker system prune -a` to reclaim.

**Backend errors**
- `asyncpg.InvalidPasswordError` / `connection refused` — Postgres container not up. `docker compose ps`, `docker compose up -d postgres`.
- `dialect 'postgres' is not supported` — `DATABASE_URL` scheme wrong, must be `postgresql+asyncpg://`.
- `redis.exceptions.ConnectionError` — Redis container not up.
- `alembic upgrade head` says "Target database is not up to date" or two heads — pull main, `alembic merge` (cross-link to engineer doc).
- Seed script `IntegrityError` — likely re-running on partly-seeded DB. `docker compose down -v && docker compose up -d` to start clean, then re-run migrate + seed.
- `uv sync` SSL certificate error — corporate / college proxy or out-of-date CA bundle. `pip config` workaround.
- `uv: error: failed to fetch` — proxy or rate-limited.

**Frontend errors**
- `npm install` ETIMEDOUT or ECONNRESET — slow / interrupted network, retry. If repeated, try `npm config set registry https://registry.npmmirror.com` (Indian mirror).
- `npm install` "EACCES" — permission issue, do not `sudo npm`. Reinstall Node via nvm so it lives in your home folder.
- Frontend at `localhost:3000` shows blank white page — open browser console (F12), look for errors. Often the backend is down.
- Frontend cannot reach API — `NEXT_PUBLIC_API_URL` should be empty in `frontend/.env.local`. Restart `npm run dev` after editing.
- Hot reload not working — disable Windows Defender real-time scanning of the project folder, or move the project inside the WSL filesystem (`~/projects/`, not `/mnt/c/...`).

**Login / OTP errors**
- "OTP not arriving" — confirm `EMAIL_PROVIDER=console` in `backend/app/.env`. Restart backend after editing. Look in log viewer's backend tab.
- "Invalid OTP" — code is 6 digits, no spaces. Code expires in 10 minutes. After 5 wrong attempts you are locked out for an hour.
- "User does not exist" — they typed an email that was not seeded. Use one from chapter 5's table.

**Map errors**
- `RefererNotAllowedMapError` in browser console — browser key referrer restrictions don't include `http://localhost:3000/*`. Add it in GCP Credentials.
- `REQUEST_DENIED` from server geo endpoints — server key IP restrictions don't include current public IP. Update in GCP. Note IP changes when network changes.
- "This page can't load Google Maps correctly" — billing not enabled on the GCP project, or APIs not enabled. Re-check chapter 3 steps.

**Generic / "nothing here matches"** — Slack template they should send the engineer:
- What chapter and step were you on?
- The exact error message (paste, do not paraphrase).
- Output of `./scripts/dev.sh status`.
- Output of `docker compose ps`.
- Last 30 lines of the relevant log: `./scripts/dev.sh logs backend | tail -30`.

### 5.8 `07-daily-use.md` (Day-to-day after install)

- **Open the project.**
  ```
  cd ~/projects/KhanaBazaar
  ./scripts/dev.sh start
  ```
  That's the whole start-of-day routine. Open the browser tabs from chapter 4.
- **Stop for the day.** `./scripts/dev.sh stop`. Optional: also stop Docker via `./scripts/dev.sh stop --all` if RAM-constrained.
- **Status / logs.** Brief recap of `dev.sh status` and `dev.sh logs <service>`.
- **Pulling new code.**
  ```
  git pull
  ```
  If backend changed: `cd backend/app && uv sync && uv run alembic upgrade head`.
  If frontend changed: `cd frontend && npm install`.
  Restart with `./scripts/dev.sh restart`.
- **When to re-seed.** Only after schema changes wipe the database, or if their data gets weird and they want a clean slate. Steps: `./scripts/dev.sh stop && docker compose down -v && docker compose up -d && cd backend/app && uv run alembic upgrade head && uv run python scripts/seed_database.py`.
- **Updating tools.**
  - Docker Desktop: built-in updater notifies, click and apply.
  - WSL: `wsl --update` in PowerShell.
  - Node: `nvm install --lts`.
  - uv: `uv self update`.
- **Reading logs to find your own answers.** A short tutorial on what to look for in backend log lines: `INFO` is normal, `WARNING` is suspicious, `ERROR` and `CRITICAL` are real problems. Show one example of each.
- **Reset to clean slate** (in case of last resort): full destroy command sequence with explicit "this deletes all your demo data" warning.

### 5.9 `appendix-mobile-ngrok.md` (Optional: Phone testing)

- **What it does.** Lets a teammate open the dev app on their phone over mobile data (not just same-wifi) for real-device feel.
- **One-time setup.**
  - Sign up at `ngrok.com` (free).
  - Dashboard → Your Authtoken → copy.
  - Install ngrok in WSL: `curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt update && sudo apt install ngrok`.
  - Authenticate: `ngrok config add-authtoken <token>`.
- **Each session.**
  - `./scripts/dev.sh start --tunnel` → prints public URL.
  - Open URL on phone → "Visit Site" interstitial → app loads.
- **Common gotchas.**
  - URL rotates on every restart on the free plan.
  - First request may 502 while Next.js compiles — reload after a few seconds.
  - `NEXT_PUBLIC_API_URL` must remain empty (default).
  - Can install as a PWA from the phone browser's "Add to Home Screen" menu.

### 5.10 `appendix-glossary.md` (Plain-English glossary)

Approximately 30 terms, each with 2–4 sentence definition in plain English plus an analogy where useful. Anchored so other chapters deep-link.

Initial term list:
API, Backend, Branch, Cache, Celery, Cluster, Commit, Container, Database, Dependency, Docker, Environment variable, Frontend, Git, Hot reload, JSON, JWT, Localhost, Migration, Node.js, npm, OTP, Port, PostgreSQL, Python, Redis, Repository, Seed data, Shell / Terminal, SQL, SSL / TLS, Swagger, uv, WSL.

## 6. Implementation strategy

The guide is content, not code. Implementation is sequential, one file at a time. There is no testing infrastructure beyond reading the produced docs and dry-running them.

Order of writing:

1. `appendix-glossary.md` first — so other chapters can link into a real file from the start.
2. `README.md` (chapter 00) — establishes voice, navigation pattern, breadcrumb format.
3. `01-install-tools.md` — heaviest chapter, sets the precedent for "what / install / verify / fail" structure used elsewhere.
4. `02-clone-and-env.md` and `04-first-run.md` together — they share most of the command-execution patterns.
5. `03-google-maps-keys.md` — separate flow, can be written in isolation.
6. `05-demo-logins.md` — depends on knowing the seed data, source of truth is `backend/app/src/app/db/dev_seed.py`.
7. `06-troubleshooting.md` — written last so anchors from other chapters are known and stable.
8. `07-daily-use.md` — final summary chapter.
9. `appendix-mobile-ngrok.md` — last because it is optional.

After all files exist, do one full read-through pass to sync cross-links, verify every troubleshooting anchor referenced from other chapters exists, and tighten voice consistency.

## 7. Validation

Validation is by manual dry-run, not automated tests:

- **Cross-link check.** Every internal link resolves to an existing file or anchor.
- **Command verification.** Every command in the guide actually runs against a clean WSL2 + Ubuntu environment. (Cannot be done by author of the spec — flagged as a follow-up step for whoever executes the plan.)
- **Voice consistency.** Spot-check each chapter for banned words ("just", "simply", "obviously", "easy") and pronoun consistency.
- **Source-of-truth sync.** The seeded account list in chapter 5 must match `backend/app/src/app/db/dev_seed.py`. Add a brief note in chapter 5 pointing future maintainers to update both together if the seed changes.

## 8. Open questions / risks

- **Screenshots are placeholders only.** Guide ships text-complete. Whoever drops real images into `docs/teammate-guide/images/` later must use the placeholder text as the brief. If images never get added, the guide remains usable but harder for visual-installer steps (Docker Desktop setup is the worst-affected).
- **Seed data drift.** If `dev_seed.py` changes (new test users, removed accounts), chapter 5's table goes stale. Mitigation: a one-line maintenance note inside chapter 5 telling future engineers to update both.
- **GCP signup flow drift.** Google rearranges Cloud Console UI fairly often. Chapter 3's click-by-click steps may stop matching exactly within months. Mitigation: the prose explains *why* each step exists, so a reader can adapt; the cross-link to `docs/google_maps_setup.md` provides a more durable engineer-level reference.
- **Tool version drift.** `wsl --install`, Docker Desktop UI, nvm, uv all change. Each install section ends with a "if the screen looks different from this guide, the underlying step is still <X>" reassurance.
- **Author of guide cannot test on Windows directly.** Recommend the user runs through the full flow on a clean Windows machine (or a colleague does) before circulating.
