# Teammate Onboarding Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a self-contained, idiot-proof onboarding guide at `docs/teammate-guide/` that lets a non-technical Windows-using teammate go from zero installed tools to a running KhanaBazaar demo with seeded data and demo logins.

**Architecture:** Documentation-only deliverable. Eleven new Markdown files under `docs/teammate-guide/` (cover, seven chapters, two appendices, plus an empty `images/` folder). Linear navigation via per-chapter previous/next footers. Symptom-indexed troubleshooting chapter. Plain-English glossary cross-linked from every other chapter. No code, schemas, tests, or runtime changes.

**Tech Stack:** GitHub-flavoured Markdown only. No build step, no static-site generator, no link-check CI. Validation is by manual read-through and grep-based cross-link check (Task 12).

**Source spec:** `docs/superpowers/specs/2026-05-08-teammate-onboarding-guide-design.md` — every chapter task below references the spec section that fixes its content. The spec is the source of truth for scope, voice, and per-chapter outline; this plan is the *order of operations*.

**Branch:** All commits land on `docs/teammate-onboarding-guide` (already checked out; spec lives there). Do **not** branch off again. Do **not** commit to `main`.

**Voice rules** (apply in every task; spec §4.3 is authoritative):
- Plain English at roughly grade-8 reading level. Short sentences. Second person, imperative mood.
- Banned words: `just`, `simply`, `obviously`, `easy` — grep before commit.
- Every command in a fenced code block, single line, copy-paste ready.
- Every command preceded by a bold execution-context line: `**Run in: WSL2 Ubuntu terminal**`, `**Run in: PowerShell (as Administrator)**`, or `**Click in: web browser**`.
- Every command followed by a `**What you should see:**` block with real expected output (3–10 lines, truncate with `...`).
- Wait times stated when over 10 seconds: `*This takes about 2-5 minutes on a fast connection.*`.
- Inline 1–2 sentence "If it fails:" pointer after each command, linking to a `06-troubleshooting.md` anchor.
- Glossary terms italicised on first use per chapter, linked to `./appendix-glossary.md#<anchor>`.
- Screenshot placeholders use the form `[Screenshot: <one-line description of what to capture>]`.

**Repo facts the writer MUST honour** (do not invent):
- Repo URL: `https://github.com/rishimule/KhanaBazaar.git`.
- Backend env example: `backend/app/.env.example` (verbatim variable names: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `JWT_EXPIRES_HOURS`, `OTP_PEPPER`, `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN`, `OTP_MAX_PER_HOUR`, `EMAIL_PROVIDER`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `SMS_PROVIDER`, `TWILIO_*`, `FRONTEND_ORIGIN`, `GOOGLE_MAPS_SERVER_API_KEY`, `GOOGLE_MAPS_BROWSER_API_KEY`, `GEO_RATE_LIMIT_PER_MIN`, `GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS`, `GEO_REVERSE_CACHE_TTL_SECONDS`).
- Frontend env example: `frontend/.env.example` (variables: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`).
- Placeholder strings to replace in backend `.env`: `change-me-use-secrets-token-hex-32` (JWT_SECRET) and `change-me-use-secrets-token-hex-16` (OTP_PEPPER).
- Docker services and ports: `khanabazaar-postgres` (image `postgis/postgis:15-3.4`) on `5432`, `khanabazaar-redis` (image `redis:alpine`) on `6379`. Postgres user `postgres`, password `password`, db `khanabazaar`.
- Seed script path: `backend/app/scripts/seed_database.py`.
- Dev orchestrator: `./scripts/dev.sh` with subcommands `start`, `start --tunnel`, `stop`, `stop --all`, `restart`, `status`, `logs [backend|celery|frontend|ngrok|log_viewer]`, `tunnel`, `tunnel-url`.
- Dev URLs: backend `http://localhost:8000` (Swagger at `/docs`), frontend `http://localhost:3000`, log viewer `http://localhost:8001`.
- Seeded users from `backend/app/src/app/db/dev_seed.py`:
  - Admin: `admin@khanabazaar.dev`
  - Customer: `customer@khanabazaar.dev`
  - Sellers: `seller@khanabazaar.dev`, `seller2@khanabazaar.dev` … `seller9@khanabazaar.dev` (9 seller users total)
  - Seller applications (separate `APPLICATIONS` list): `pending.seller@khanabazaar.dev`, `approved.seller@khanabazaar.dev`, `rejected.seller@khanabazaar.dev`
- Login is email-OTP only. With `EMAIL_PROVIDER="console"` the 6-digit code prints to backend stdout (and to the log viewer).

---

## File Structure

All new files live under `docs/teammate-guide/`. No existing project files are modified by this plan.

| File | Responsibility |
|------|---------------|
| `docs/teammate-guide/README.md` | Cover page (chapter 00). Audience, expectations, time estimate, pre-flight checklist, chapter index, "if stuck" callout. Spec §5.1. |
| `docs/teammate-guide/01-install-tools.md` | BIOS virtualisation check, WSL2 + Ubuntu, Docker Desktop, Windows Terminal, Git, Node 20 via nvm, Python 3.12, uv. Spec §5.2. |
| `docs/teammate-guide/02-clone-and-env.md` | Clone repo, copy `.env` files, generate JWT/OTP secrets, edit env in nano. Spec §5.3. |
| `docs/teammate-guide/03-google-maps-keys.md` | GCP signup, billing, three APIs, server + browser keys, paste into env files. Spec §5.4. Optional chapter (skip-block at top). |
| `docs/teammate-guide/04-first-run.md` | Bring up Postgres+Redis, wait readiness, `uv sync`, migrate, seed, `npm install`, `dev.sh start`, browser verification. Spec §5.5. |
| `docs/teammate-guide/05-demo-logins.md` | OTP-via-log-viewer flow, full seeded-account table, customer first-login walkthrough, 5-minute demo script across all roles, page tour by role. Spec §5.6. |
| `docs/teammate-guide/06-troubleshooting.md` | Symptom-indexed catalogue: install / Docker / backend / frontend / login / map errors, plus Slack template. Spec §5.7. |
| `docs/teammate-guide/07-daily-use.md` | Day-2+ start/stop/status/logs, pulling new code, when to re-seed, updating tools, reading logs, full reset-to-clean. Spec §5.8. |
| `docs/teammate-guide/appendix-mobile-ngrok.md` | Optional: ngrok signup, install, auth-token, `dev.sh start --tunnel`, phone gotchas, PWA install. Spec §5.9. |
| `docs/teammate-guide/appendix-glossary.md` | ~30 plain-English term entries with anchors. Spec §5.10. |
| `docs/teammate-guide/images/.gitkeep` | Empty placeholder folder for future screenshots. |

---

## Task 1: Bootstrap directory and glossary

**Why first:** Other chapters italicise glossary terms on first use and link to `./appendix-glossary.md#<anchor>`. Writing the glossary first lets every later task author real links instead of marking placeholders. Spec §6 also pins this order.

**Files:**
- Create: `docs/teammate-guide/images/.gitkeep`
- Create: `docs/teammate-guide/appendix-glossary.md`

- [ ] **Step 1.1: Create the directory and empty image folder placeholder**

```bash
mkdir -p docs/teammate-guide/images
touch docs/teammate-guide/images/.gitkeep
```

- [ ] **Step 1.2: Write `appendix-glossary.md`**

The file must include, in this order:

1. Breadcrumb header line: `Teammate Guide > Appendix: Glossary`.
2. One-paragraph intro: "Plain-English definitions for every technical term used elsewhere in this guide. Each entry is short and avoids more jargon. If you bump into a word that is missing here, ping the engineer — they will add it."
3. Alphabetised entries, each as an `## <Term>` heading (so the GitHub anchor is `#<term-lowercase-hyphenated>`). Each entry is 2–4 sentences. Use an analogy where it adds clarity. Banned words rule still applies.
4. Footer line: `← [Previous: Appendix — Mobile testing](./appendix-mobile-ngrok.md)  |  [Back to start](./README.md)`. (Order matches the chapter sequence — glossary is the final document.)

Required terms (one entry each — do not collapse synonyms):

`API`, `Backend`, `Branch`, `Cache`, `Celery`, `Cluster`, `Commit`, `Container`, `Database`, `Dependency`, `Docker`, `Environment variable`, `Frontend`, `Git`, `Hot reload`, `JSON`, `JWT`, `Localhost`, `Migration`, `Node.js`, `npm`, `OTP`, `Port`, `PostgreSQL`, `Python`, `Redis`, `Repository`, `Seed data`, `Shell / Terminal`, `SQL`, `SSL / TLS`, `Swagger`, `uv`, `WSL`.

For each term, write one sentence that says what it is, one sentence that says why this app uses it (or what role it plays in development), and an optional analogy if jargon-density is high. Example for `Container`:

```markdown
## Container

A *container* is a sealed lunchbox that holds an app together with the small slice of operating system the app needs to run. The same container behaves the same way on your laptop, on a teammate's laptop, and on the production server — there are no "works on my machine" surprises. KhanaBazaar uses two containers in development (one for *PostgreSQL*, one for *Redis*); both are started by Docker.
```

Cross-references inside glossary entries are allowed and encouraged (use italic-link form `*[PostgreSQL](#postgresql)*` on first use within an entry). Do not link out to other chapters from inside the glossary — that traffic flows the other way.

- [ ] **Step 1.3: Verify the file with grep-based sanity checks**

```bash
grep -c '^## ' docs/teammate-guide/appendix-glossary.md
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/appendix-glossary.md
```

Expected: first command prints `34` (one heading per term). Second command prints nothing. If banned words appear, rewrite the offending lines before commit.

- [ ] **Step 1.4: Commit**

```bash
git add docs/teammate-guide/images/.gitkeep docs/teammate-guide/appendix-glossary.md
git commit -m "docs(teammate-guide): glossary appendix"
```

---

## Task 2: Cover page (`README.md` / chapter 00)

**Why second:** Establishes the breadcrumb, footer, callout, and screenshot-placeholder conventions every later chapter copies. Also gives every later chapter a real link target for "back to start". Spec §5.1.

**Files:**
- Create: `docs/teammate-guide/README.md`

- [ ] **Step 2.1: Write the cover page**

Required structure, in order:

1. Top-of-page line: a level-1 heading `# KhanaBazaar — Teammate Onboarding Guide`.
2. **Breadcrumb line** under the title: `*Teammate Guide > Start Here*`.
3. **One-paragraph "what is this app"** in plain English. Suggested wording: "KhanaBazaar is an online grocery and food marketplace for Indian neighbourhoods. Shop owners list what they have on the platform, and customers nearby order through the website. Three kinds of people use it — *admins* who run the catalogue, *sellers* who run their own shop on the platform, and *customers* who shop." Italicise the role words and link them to glossary entries even though those entries are role-descriptive (skip if a glossary entry was not written for "admin/seller/customer" — they were not, so leave plain). Reword as needed but keep it under 60 words.
4. **"What you'll have at the end"** as a 4–5-bullet list. Bullets: full app running on your Windows laptop; demo accounts to log in as admin, seller, and customer; ability to stop and restart the app on later days; an optional way to view it on your phone; troubleshooting reference for when things break.
5. **Time estimate callout** in a blockquote: roughly 90 minutes the first time end-to-end (install + run), then about 5 minutes on subsequent days.
6. **Pre-flight checklist** as a `## Before you start` section with a checkbox-style markdown list: Windows 10 or 11; 8 GB RAM minimum, 16 GB recommended; 20 GB free disk; admin rights on the machine; virtualisation enabled in BIOS (link to `./01-install-tools.md#bios-virtualisation`); stable internet, ~3 GB of downloads expected.
7. **Chapter index** as a `## The chapters` table with two columns (Chapter, You'll do):
   | Chapter | You'll do |
   |---|---|
   | [1 — Install your tools](./01-install-tools.md) | Set up WSL2, Docker Desktop, Git, Node, Python, and uv. |
   | [2 — Get the code and configure secrets](./02-clone-and-env.md) | Clone the repo, copy env files, generate JWT and OTP secrets. |
   | [3 — Google Maps API keys (optional)](./03-google-maps-keys.md) | Provision two restricted Google Maps keys for address autocomplete and the map pin. |
   | [4 — Run the app for the first time](./04-first-run.md) | Start the database, build tables, load demo data, launch backend + frontend. |
   | [5 — Demo accounts and login flow](./05-demo-logins.md) | Sign in as admin, seller, and customer; run a 5-minute demo script. |
   | [6 — When things break](./06-troubleshooting.md) | Look up errors by symptom and fix them. |
   | [7 — Day-to-day after install](./07-daily-use.md) | Start, stop, update, and reset the app. |
   | [Appendix — Phone testing (optional)](./appendix-mobile-ngrok.md) | Open the dev app on your phone via ngrok. |
   | [Appendix — Glossary](./appendix-glossary.md) | Plain-English definitions for every technical term. |
8. **"If you get stuck" callout** in a blockquote: "Jump to [chapter 6](./06-troubleshooting.md). If nothing there matches, send your engineer the message template at the [bottom of chapter 6](./06-troubleshooting.md#nothing-here-matches)."
9. **Footer**: `Next: [Chapter 1 — Install your tools](./01-install-tools.md) →`.

The page is the cover — keep it scannable, no long prose. Aim ~150 lines.

- [ ] **Step 2.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/README.md
test -f docs/teammate-guide/README.md && echo OK
```

Expected: first command prints nothing; second prints `OK`.

- [ ] **Step 2.3: Commit**

```bash
git add docs/teammate-guide/README.md
git commit -m "docs(teammate-guide): cover page (chapter 00)"
```

---

## Task 3: Chapter 01 — Install your tools

**Why now:** Heaviest chapter. Establishes the "What it is / Install / Verify / If it fails" four-block tool pattern that chapters 02 and 04 reuse. Spec §5.2.

**Files:**
- Create: `docs/teammate-guide/01-install-tools.md`

- [ ] **Step 3.1: Write the chapter**

Top-of-file boilerplate:
- `# Chapter 1 — Install your tools`
- Breadcrumb: `*Teammate Guide > Chapter 1: Install your tools*`
- Time callout (blockquote): "Estimated time: 60–90 minutes. Most of it is downloads — go grab tea between sections."
- One-paragraph intro: lists the seven things they're about to install in order; reassures that every step has a verify command they can run to check it worked.

Then a section per tool. Every tool section uses **exactly** these four sub-headings in order:

```markdown
### Tool: <Name>

**What it is.** <one short paragraph with analogy>

**Install steps.**

1. ...
2. ...

**Verify it worked.**

**Run in: <context>**
```
<command>
```
**What you should see:**
```
<expected output>
```

**If it fails.** <2-3 sentences with link into ./06-troubleshooting.md#<anchor>>
```

Tool sections in the following order. For each, every numbered install step must be a single concrete action — no compound "do X and Y". Use the source-of-truth values listed below; do not invent versions or commands.

#### 0. BIOS virtualisation check (anchor `#bios-virtualisation`)

- **What it is.** Modern Windows laptops can run a tiny lightweight Linux side-by-side with Windows. That feature uses a CPU capability called *virtualisation*. Many laptops ship with the capability turned off in the firmware (BIOS) settings — you have to flip a switch before any of the next tools will work.
- **Install steps:** open Task Manager (Ctrl+Shift+Esc) → Performance tab → CPU panel → look for "Virtualization:". If it says **Enabled**, skip to the next tool. If **Disabled**, follow the BIOS section below.
- BIOS sub-section: vendor-specific reboot keys (Lenovo `F1` or `Fn+F2`; HP `Esc` then `F10`; Dell `F2`; Asus `F2` or `Del`; MSI `Del`). Inside BIOS look for `Intel Virtualization Technology` / `VT-x` / `SVM Mode` / `AMD-V` and enable it. Save & Exit (usually `F10`).
- **Verify**: same Task Manager line now reads **Enabled**.
- **If it fails.** Link to `./06-troubleshooting.md#virtualisation-disabled`.

#### 1. WSL2 with Ubuntu (anchor `#wsl2-ubuntu`)

- **What it is.** *WSL* (Windows Subsystem for Linux) lets a real Ubuntu Linux run inside Windows. KhanaBazaar's tooling assumes a Linux shell, so this is the foundation everything else sits on.
- **Install steps:**
  1. Open PowerShell as Administrator (Start → type "PowerShell" → right-click → "Run as administrator").
  2. **Run in: PowerShell (as Administrator)** — `wsl --install`
  3. Wait for the install to finish (5–10 minutes on first run).
  4. Restart Windows when prompted.
  5. After reboot, an Ubuntu window opens automatically asking for a username and password. Enter a lowercase username (no spaces). The password is **not** your Windows password — pick a new one. **Heads-up:** while typing the password the screen shows nothing (no dots, no asterisks). That is normal Linux behaviour. Type carefully.
- **Verify it worked.**
  ```
  wsl --status
  ```
  Run in PowerShell. Expected: `Default Distribution: Ubuntu` and `Default Version: 2`.
  ```
  lsb_release -a
  ```
  Run in the Ubuntu window. Expected: `Description: Ubuntu 24.04.X LTS` (or 22.04 — both fine).
- **If it fails.** Link to `./06-troubleshooting.md#wsl-install-fails`.

#### 2. Docker Desktop (anchor `#docker-desktop`)

- **What it is.** *Docker* is a sealed lunchbox for software. KhanaBazaar uses two lunchboxes: one for the database (*PostgreSQL*), one for the cache (*Redis*). Docker Desktop is the Windows app that runs them.
- **Install steps:**
  1. Open `https://www.docker.com/products/docker-desktop/` in a web browser.
  2. Click "Download for Windows — AMD64".
  3. Run the installer. **Important checkbox:** "Use WSL 2 instead of Hyper-V (recommended)" — leave it ticked.
  4. Click OK and let it install. Restart when prompted.
  5. Open Docker Desktop. Skip sign-in if prompted.
  6. Settings (gear icon) → Resources → WSL Integration → toggle on the **Ubuntu** entry. Click Apply & Restart.
- **Verify it worked.**
  **Run in: WSL2 Ubuntu terminal**
  ```
  docker --version
  ```
  Expected output: `Docker version 27.x.x, build <hash>`.
  ```
  docker compose version
  ```
  Expected: `Docker Compose version v2.x.x`.
  ```
  docker run --rm hello-world
  ```
  Expected: a "Hello from Docker!" paragraph.
- **If it fails.** Link to `./06-troubleshooting.md#docker-wont-start`.

#### 3. Windows Terminal (optional, anchor `#windows-terminal`)

- **What it is.** A nicer terminal app than the default. Tabs, copy-paste, and a darker theme. Recommended but not required.
- **Install:** Microsoft Store → search "Windows Terminal" → Get.
- **Set Ubuntu as default profile:** open Windows Terminal → drop-down arrow next to the `+` → Settings → Default profile → pick `Ubuntu`. Save.

#### 4. Git (anchor `#git`)

- **What it is.** *Git* is the version-control tool that downloads the project and tracks changes. Comes preinstalled on most Ubuntu builds, but not all.
- **Install steps:**
  ```
  sudo apt update
  sudo apt install -y git
  ```
  Plain-English breakdown of the command: `sudo` runs as administrator, `apt` is Ubuntu's app store, `install` installs, `-y` says yes to prompts. Password prompt the first time — type your Ubuntu password (no dots will appear).
- **Verify:** `git --version` → `git version 2.x.x`.
- **If it fails.** Link to `./06-troubleshooting.md#apt-update-hangs`.

#### 5. Node.js 20 via nvm (anchor `#nodejs`)

- **What it is.** *Node.js* runs the frontend. *nvm* (Node Version Manager) lets you install and switch Node versions easily. We use nvm instead of `apt install nodejs` because Ubuntu's apt version is older than what KhanaBazaar needs.
- **Install steps:**
  ```
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  ```
  After the script finishes, **close and reopen** the Ubuntu window. (nvm modifies your shell profile and the new session picks it up.)
  ```
  nvm install 20
  nvm use 20
  nvm alias default 20
  ```
- **Verify:**
  ```
  node --version
  npm --version
  ```
  Expected: `v20.x.x` and `10.x.x`.
- **If it fails.** Link to `./06-troubleshooting.md#nvm-not-found`.

#### 6. Python 3.12 (anchor `#python`)

- **What it is.** *Python* runs the backend. Ubuntu 24.04 ships with Python 3.12 already; older Ubuntu needs a manual install.
- **Install steps:**
  1. Check first:
     ```
     python3 --version
     ```
     If it says `Python 3.12.x`, skip the rest.
  2. If older: install from the Deadsnakes PPA:
     ```
     sudo add-apt-repository ppa:deadsnakes/ppa -y
     sudo apt update
     sudo apt install -y python3.12 python3.12-venv
     ```
- **Verify:** `python3 --version` → `Python 3.12.x`.
- **If it fails.** Link to `./06-troubleshooting.md#python-version-mismatch`.

#### 7. uv (anchor `#uv`)

- **What it is.** *uv* is a fast Python package manager. It replaces `pip` for this project. KhanaBazaar's backend dependencies are managed with uv, not requirements.txt.
- **Install steps:**
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  Close and reopen the Ubuntu window after install (uv modifies your `PATH`).
- **Verify:** `uv --version` → `uv 0.4.x` or newer.
- **If it fails.** Link to `./06-troubleshooting.md#uv-not-found`.

#### 8. Final verification block

A `## All-in-one check` section at the end of the chapter:

**Run in: WSL2 Ubuntu terminal**
```
wsl.exe --version 2>/dev/null || echo "(run wsl --version from PowerShell instead)"
docker --version
docker compose version
git --version
node --version
npm --version
python3 --version
uv --version
```

Expected: each tool prints a real version string, nothing prints `command not found`. If any line fails, scroll up to that tool's section.

#### 9. Cross-cutting concerns (own subsection at end of chapter)

A `## Common install pitfalls` block covering, in this order:
- Slow / hostel networks: what timeouts look like (`Could not resolve archive.ubuntu.com`, `ETIMEDOUT`), retry advice, link to troubleshooting `#network-timeout`.
- Antivirus blocking Docker (Quick Heal, K7, Norton, McAfee): symptom (installer rolls back, "service failed to start"), workaround (temporarily disable real-time protection during install, re-enable after), link `#antivirus-blocks-docker`.
- Corporate / college proxy: symptom (`Could not resolve host`), how to set `HTTP_PROXY` and `HTTPS_PROXY` in `~/.bashrc`, link `#proxy-blocking-installs`.
- Reboots after WSL and after Docker — explicit "save your work and restart now" callouts.

Footer:
`← [Previous: Start Here](./README.md)  |  Next: [Chapter 2 — Get the code and configure secrets](./02-clone-and-env.md) →`

- [ ] **Step 3.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/01-install-tools.md
grep -c '^### Tool:' docs/teammate-guide/01-install-tools.md
```

Expected: first prints nothing; second prints `8` (BIOS check + 7 tools).

- [ ] **Step 3.3: Commit**

```bash
git add docs/teammate-guide/01-install-tools.md
git commit -m "docs(teammate-guide): chapter 01 install tools"
```

---

## Task 4: Chapter 02 — Get the code and configure secrets

**Files:**
- Create: `docs/teammate-guide/02-clone-and-env.md`

- [ ] **Step 4.1: Write the chapter**

Required structure:

1. Heading + breadcrumb + estimated time (~15 minutes).
2. One-paragraph intro: "Three things this chapter does — download the project files, copy two example settings files into real settings files, and fill in two secret values."
3. **Section: Make a place for the project.**
   ```
   mkdir -p ~/projects
   cd ~/projects
   ```
   Plain-English: `~` is your home folder. `mkdir -p` creates the folder if it does not exist. `cd` moves you into it.
4. **Section: Download the code.**
   ```
   git clone https://github.com/rishimule/KhanaBazaar.git
   cd KhanaBazaar
   ```
   Explain *cloning* (italic + glossary link) as "downloading a folder along with its full edit history". Wait time: 1–2 minutes.
   Verify: `ls` → expected to see `backend  CLAUDE.md  docker-compose.yml  docs  frontend  README.md  scripts  TODO.md` (and a few more).
5. **Section: Copy the example env files.**
   ```
   cp backend/app/.env.example backend/app/.env
   cp frontend/.env.example   frontend/.env.local
   ```
   Two-paragraph plain-English explainer of *environment variables* (italic + glossary link): a setting the app reads at startup, kept outside the code so secrets do not leak. The `.env.example` files are templates committed to the repo; the real `.env` files (which you just created) are ignored by Git so your secrets stay on your laptop only.
6. **Section: Generate the two secrets.** (anchor `#generate-secrets`)
   - `JWT_SECRET` — the key that signs login tokens. If anyone learns it they can forge logins.
     ```
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```
     **What you should see:** a 64-character hex string. Copy it.
   - `OTP_PEPPER` — extra randomness mixed into one-time login codes so two laptops do not generate identical codes.
     ```
     python3 -c "import secrets; print(secrets.token_hex(16))"
     ```
     **What you should see:** a 32-character hex string. Copy it.
7. **Section: Edit the backend env file.** (anchor `#edit-backend-env`)
   - Open it: `nano backend/app/.env`.
   - Nano cheat-sheet box: arrow keys to move, type to edit, `Ctrl+O` then Enter to save, `Ctrl+X` to exit. The `^` symbol on the bottom bar means Ctrl.
   - Find the line `JWT_SECRET="change-me-use-secrets-token-hex-32"`.
   - **Replace the entire value between the quotes** — delete `change-me-use-secrets-token-hex-32` (do not just paste next to it), then paste your 64-char hex string. End-state: `JWT_SECRET="<your-64-char-string>"`. Show a before / after side-by-side fenced block.
   - Repeat for `OTP_PEPPER="change-me-use-secrets-token-hex-16"` with the 32-char string.
   - Leave `EMAIL_PROVIDER="console"` as-is. Plain-English: in dev mode, login codes print to a log instead of being emailed. You will see how to read that log in chapter 5.
   - Save (`Ctrl+O`, Enter, `Ctrl+X`).
8. **Section: Maps keys.** (anchor `#maps-skip-block`)
   - Callout block: "**Skip this section if you only need the core e-commerce demo.** The app falls back to manual address entry without maps. Come back here later when you want maps. Forward link: [Chapter 3 — Google Maps API keys](./03-google-maps-keys.md)."
   - Note for those who skip: leave `GOOGLE_MAPS_SERVER_API_KEY=""` and `GOOGLE_MAPS_BROWSER_API_KEY=""` in the backend `.env`, and `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""` in the frontend `.env.local`. Empty strings are fine — the app detects them and switches to manual mode.
   - Footnote: backend's `GOOGLE_MAPS_BROWSER_API_KEY` line is unused vestigial — only the frontend `.env.local` line is read at runtime. Keep it empty.
9. **Section: Sanity check.**
   ```
   cat backend/app/.env | grep -E '^(JWT_SECRET|OTP_PEPPER|EMAIL_PROVIDER)='
   ```
   **What you should see:** `JWT_SECRET="<long hex>"`, `OTP_PEPPER="<long hex>"`, `EMAIL_PROVIDER="console"`. The hex strings must **not** contain the word `change-me`.
   ```
   cat frontend/.env.local
   ```
   **What you should see:** `NEXT_PUBLIC_API_URL=""` and `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""` (until they go through chapter 3).
10. Footer: `← [Previous: Chapter 1 — Install your tools](./01-install-tools.md)  |  Next: [Chapter 3 — Google Maps API keys (optional)](./03-google-maps-keys.md) →`. Note: even though chapter 3 is optional, the linear footer always points to the next file. Skippers go straight to chapter 4 via the chapter-3 skip block.

- [ ] **Step 4.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/02-clone-and-env.md
grep -c 'glossary' docs/teammate-guide/02-clone-and-env.md
```

Expected: first prints nothing; second prints at least `2` (cloning + environment-variable glossary links).

- [ ] **Step 4.3: Commit**

```bash
git add docs/teammate-guide/02-clone-and-env.md
git commit -m "docs(teammate-guide): chapter 02 clone and env"
```

---

## Task 5: Chapter 04 — Run the app for the first time

**Why before chapter 03:** Chapters 02 and 04 share a command-execution pattern; writing them back-to-back keeps voice consistent. Chapter 03 is optional and can be slotted in after.

**Files:**
- Create: `docs/teammate-guide/04-first-run.md`

- [ ] **Step 5.1: Write the chapter**

Required structure:

1. Heading + breadcrumb + estimated time (~25 minutes for first run, mostly waiting).
2. Intro paragraph: "By the end of this chapter the app is running on your laptop. You will type seven commands. Most of them are downloads — go grab tea between sections."
3. **Section: Start Docker Desktop.**
   - Click the Docker Desktop icon in Start menu. Wait until the whale icon appears in the system tray (bottom-right) and the app says "Docker Desktop is running" (Settings → General).
   - **If it fails.** Link `./06-troubleshooting.md#docker-wont-start`.
4. **Section: Bring up Postgres and Redis.**
   - **Run in: WSL2 Ubuntu terminal**
     ```
     cd ~/projects/KhanaBazaar
     docker compose up -d
     ```
   - Plain-English: this downloads two pre-built images and runs them as containers. PostgreSQL is the database, Redis is the cache. Wait time: 1–3 minutes first run while images download (~400 MB).
   - **What you should see:** a series of `Pulling ...`, `Pull complete`, then `Container khanabazaar-postgres  Started` and `Container khanabazaar-redis  Started`.
   - **Wait for Postgres to actually be ready** before moving on — the next step crashes with `connection refused` if the database has not finished booting.
     ```
     docker compose exec postgres pg_isready -U postgres -d khanabazaar
     ```
     Repeat the command until it prints `accepting connections`. Usually 5–20 seconds.
   - Verify both containers are up:
     ```
     docker compose ps
     ```
     **What you should see:** `khanabazaar-postgres` and `khanabazaar-redis` both with `STATUS` `Up <duration>`.
   - **If it fails.** Link `./06-troubleshooting.md#docker-compose-port-in-use` and `#docker-compose-pulls-fail`.
5. **Section: Install backend dependencies.**
   - **Run in: WSL2 Ubuntu terminal** (from repo root)
     ```
     cd backend/app
     uv sync
     ```
   - Plain-English: downloads and installs every Python package the backend needs. Subsequent runs are seconds; first run takes 2–5 minutes.
   - **What you should see:** a long list of `+ <package>` lines, ending in `Resolved <N> packages` and `Installed <N> packages`.
   - **If it fails.** Link `./06-troubleshooting.md#uv-sync-fails`.
6. **Section: Build the database tables.**
   ```
   uv run alembic upgrade head
   ```
   Plain-English: runs *migrations* (italic + glossary link) — scripts that build the empty tables in the freshly-created database, ready to receive data.
   **What you should see:** lines like `INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, <message>`, ending with the most recent migration. No `ERROR` lines.
   **If it fails.** Link `./06-troubleshooting.md#alembic-not-up-to-date`.
7. **Section: Load demo data.**
   ```
   uv run python scripts/seed_database.py
   ```
   Plain-English: fills the database with sample products, stores, and the demo accounts you will use in chapter 5. Idempotent — safe to re-run.
   **What you should see:** a series of `Creating ...`, `Updating ...`, ending in `Seed complete.`.
   **If it fails.** Link `./06-troubleshooting.md#seed-script-crashes`.
8. **Section: Install frontend dependencies.**
   ```
   cd ../../frontend
   npm install
   ```
   Wait time: 2–4 minutes first time.
   **What you should see:** a progress bar, then `added <N> packages, and audited <N> packages in <time>`. A few `npm warn` lines are normal — `npm error` lines are not.
   **If it fails.** Link `./06-troubleshooting.md#npm-install-fails`.
9. **Section: Start everything with one command.**
   ```
   cd ..
   ./scripts/dev.sh start
   ```
   Plain-English breakdown of what this starts: backend on port 8000, the Celery worker (background tasks), frontend on port 3000, log viewer on port 8001. Logs live under `.dev/logs/`.
   **What you should see:** four `Starting <service>...` lines followed by four `<service> started (pid ...)` lines, ending in:
   ```
   All services up.
     Backend:    http://localhost:8000  (docs: /docs)
     Frontend:   http://localhost:3000
     Log viewer: http://localhost:8001
   ```
   **If it fails.** Link `./06-troubleshooting.md#dev-sh-start-fails` and `#port-3000-in-use`.
10. **Section: Verify in the browser.** (Numbered list, each item has a `[Screenshot: ...]` placeholder.)
    1. Open `http://localhost:3000`. **You should see:** the KhanaBazaar storefront with a list of stores (or an empty state if seeded stores aren't visible yet — check log viewer). `[Screenshot: KhanaBazaar storefront homepage in Chrome]`.
    2. Open `http://localhost:8000/docs`. **You should see:** the Swagger API documentation page with a long list of routes grouped under `auth`, `catalog`, `stores`, etc. `[Screenshot: Swagger UI showing /api/v1 routes]`.
    3. Open `http://localhost:8001`. **You should see:** the log viewer with four tabs across the top: `backend`, `celery`, `frontend`, `ngrok`. `[Screenshot: log viewer with backend tab active]`.
11. **Section: Stop the app for the day.**
    ```
    ./scripts/dev.sh stop
    ```
    **What you should see:** four `Stopping <service> (pid ...)...` lines. Note: Docker Postgres + Redis keep running in the background (low RAM cost). To also stop those: `./scripts/dev.sh stop --all`. Forward-link to `./07-daily-use.md#stopping`.
12. Footer: `← [Previous: Chapter 3 — Google Maps API keys (optional)](./03-google-maps-keys.md)  |  Next: [Chapter 5 — Demo accounts and login flow](./05-demo-logins.md) →`.

- [ ] **Step 5.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/04-first-run.md
grep -c 'localhost:' docs/teammate-guide/04-first-run.md
```

Expected: first prints nothing; second prints at least `4` (three browser URLs + boilerplate).

- [ ] **Step 5.3: Commit**

```bash
git add docs/teammate-guide/04-first-run.md
git commit -m "docs(teammate-guide): chapter 04 first run"
```

---

## Task 6: Chapter 03 — Google Maps API keys (optional)

**Files:**
- Create: `docs/teammate-guide/03-google-maps-keys.md`

- [ ] **Step 6.1: Write the chapter**

Required structure:

1. Heading + breadcrumb + estimated time (~30 minutes first time).
2. **Top-of-page skip callout** in a blockquote: "**Skip this chapter if you only want the core e-commerce demo.** The app works without maps — addresses fall back to manual entry, store distances are not shown. Come back when you want maps." Link forward to `./04-first-run.md`.
3. Intro: 2-paragraph plain-English explanation. Paragraph 1 — Google Maps is not free in production, but Google gives a generous monthly free tier the demo will not exceed. Paragraph 2 — what you'll do (create a Google Cloud account, link a payment method, enable three APIs, create two locked-down keys, paste the keys into the env files).
4. **Section: Sign in to Google Cloud.**
   - Visit `https://console.cloud.google.com`.
   - Sign in with any Google account.
5. **Section: Create the project.** (anchor `#create-project`)
   - Project picker → New Project → Name: `khana-bazaar-maps` → Create.
   - Wait for green check, then make sure that project is selected in the picker.
6. **Section: Enable billing.** (anchor `#enable-billing`)
   - Hamburger menu → Billing → Link a billing account → Create billing account.
   - Add payment method. Indian payment notes:
     - **RuPay-only cards may be rejected** — use a Visa or Mastercard credit/debit card.
     - UPI may be supported but is not always available.
     - A free $300 trial credit may appear; accept it.
   - Reassurance paragraph: Maps Platform also gives **$200 of free Maps usage every month** on top of any trial credit. The demo will not come close.
7. **Section: Set a budget alert.** (anchor `#budget-alert`)
   - Billing → Budgets & alerts → Create Budget.
   - Name: "KhanaBazaar dev safety net".
   - Amount: $5 / month. Email alerts at 50% / 90% / 100%.
   - Plain-English: this is a paranoia floor, not the actual ceiling. You'll get warnings long before any real charge.
8. **Section: Enable the three APIs.** (anchor `#enable-apis`)
   - APIs & Services → Library. Search for and Enable each:
     - **Maps JavaScript API** — renders the embedded map in the address picker.
     - **Places API** — powers address autocomplete suggestions.
     - **Geocoding API** — turns a typed address into latitude/longitude (and back).
   - **Do not enable other Maps APIs** (Routes, Roads, Air Quality). They bill separately and the app does not use them.
9. **Section: Create the server key.** (anchor `#server-key`)
   - APIs & Services → Credentials → + Create credentials → API key.
   - The key appears in a modal — copy it, then click "Edit API key" (pencil icon).
   - **Name:** `khana-bazaar-server`.
   - **API restrictions** → Restrict key → tick **Places API** and **Geocoding API** only. Untick everything else (especially Maps JavaScript API — the server never renders maps).
   - **Application restrictions** → leave at **None** for local dev. Plain-English: home internet IP addresses change when your Wi-Fi reconnects, so locking the key to one IP just causes pain. The key only ever runs from your laptop right now; tightening this is a production concern.
   - Save.
10. **Section: Create the browser key.** (anchor `#browser-key`)
    - APIs & Services → Credentials → + Create credentials → API key. Edit the new one.
    - **Name:** `khana-bazaar-browser`.
    - **API restrictions** → Restrict key → tick **only** Maps JavaScript API. Untick Places and Geocoding — the browser never calls those directly; they go through the backend.
    - **Application restrictions** → HTTP referrers → add each of:
      - `http://localhost:3000/*`
      - `http://127.0.0.1:3000/*`
      The trailing `/*` is required.
    - Save.
11. **Section: Paste the keys into your env files.** (anchor `#paste-keys`)
    - Open backend env: `nano backend/app/.env`.
    - Find `GOOGLE_MAPS_SERVER_API_KEY=""`. Replace the empty string with `"<your-server-key>"`. Save.
    - Open frontend env: `nano frontend/.env.local`.
    - Find `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""`. Replace with `"<your-browser-key>"`. Save.
    - Footnote: leave the backend's `GOOGLE_MAPS_BROWSER_API_KEY` line empty — it is not read at runtime.
    - Restart the app so the backend re-reads the env: `./scripts/dev.sh restart`. (Skip this if you are still on chapter 2 — chapter 4 will do the first start.)
12. **Section: Test it works.** (anchor `#test-keys`)
    - On the storefront (`http://localhost:3000`), click the "Deliver to" chip in the navbar. The address picker opens.
    - Type `andheri`. **You should see** Indian autocomplete suggestions in a dropdown. (If not → `./06-troubleshooting.md#request-denied`.)
    - Scroll down inside the picker. **You should see** an embedded map showing Mumbai. (If gray with "For development purposes only" watermark → `./06-troubleshooting.md#dev-watermark`.)
    - Drag the pin. The city/state fields should fill in automatically.
13. **Section: When something goes wrong, look here first.**
    - `./06-troubleshooting.md#request-denied`
    - `./06-troubleshooting.md#referrer-not-allowed`
    - `./06-troubleshooting.md#dev-watermark`
    - For deeper detail, link to engineer doc `../google_maps_setup.md` (cost orientation §10, key rotation §11, local-dev shortcut §12).
14. Footer: `← [Previous: Chapter 2 — Get the code and configure secrets](./02-clone-and-env.md)  |  Next: [Chapter 4 — Run the app for the first time](./04-first-run.md) →`.

- [ ] **Step 6.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/03-google-maps-keys.md
grep -c 'Maps JavaScript API' docs/teammate-guide/03-google-maps-keys.md
grep -c '"Places API (New)"' docs/teammate-guide/03-google-maps-keys.md
```

Expected: first prints nothing; second prints at least `3`; third prints `0` (we use the canonical name "Places API", not the "(New)" variant).

- [ ] **Step 6.3: Commit**

```bash
git add docs/teammate-guide/03-google-maps-keys.md
git commit -m "docs(teammate-guide): chapter 03 google maps keys"
```

---

## Task 7: Chapter 05 — Demo accounts and login flow

**Files:**
- Create: `docs/teammate-guide/05-demo-logins.md`

- [ ] **Step 7.1: Write the chapter**

Required structure:

1. Heading + breadcrumb + estimated time (~20 minutes for the demo script).
2. Intro: "Now that the app is running, this chapter shows you how to log in as the three kinds of user, and walks through a 5-minute end-to-end demo."
3. **Section: How OTP login works in dev.** (anchor `#otp-login-flow`) Three sentences: type your email → backend prints a 6-digit code to its log → paste the code on the login screen → you're in. No real email is sent.
4. **Section: Where the code appears.** (anchor `#read-otp-from-log`)
   - Open `http://localhost:8001` in your browser. **You should see** a log viewer with four tabs.
   - Click the `backend` tab.
   - After requesting an OTP on the storefront, look for a line like:
     ```
     [otp] code for customer@khanabazaar.dev: 123456
     ```
     `[Screenshot: log viewer with backend tab, OTP line highlighted]`. (Exact log format may vary — the line always contains the email plus a 6-digit number.)
   - Tip: Ctrl+F in the log viewer to search by email if scrolling is painful.
5. **Section: Demo accounts.** (anchor `#demo-accounts`)
   Maintenance footnote at the top: "*This list is sourced from `backend/app/src/app/db/dev_seed.py`. If new accounts are added there, update this table.*"
   Full table:
   | Role | Email | What they see / can do |
   |------|-------|----------------------|
   | Admin | `admin@khanabazaar.dev` | Approve seller applications, manage master catalogue (services, categories, products), see all orders and stores. |
   | Customer | `customer@khanabazaar.dev` | Set delivery address, browse stores, add to cart, place orders, track orders. |
   | Seller (approved) | `seller@khanabazaar.dev` | Manage their own store inventory and prices, see incoming orders, mark orders packed/dispatched/delivered. |
   | Seller (approved) | `seller2@khanabazaar.dev` … `seller9@khanabazaar.dev` | Same as above for eight other stores. Useful when demoing multiple sellers. |
   | Seller application — pending | `pending.seller@khanabazaar.dev` | Brand-new application; lands on "awaiting approval" screen. Useful for the admin tour. |
   | Seller application — approved record | `approved.seller@khanabazaar.dev` | Already-approved record; useful in admin's "approvals history". |
   | Seller application — rejected record | `rejected.seller@khanabazaar.dev` | Rejected record; useful in admin's "approvals history". |
6. **Section: First login walkthrough — customer.** (anchor `#customer-first-login`) A click-by-click walkthrough:
   1. Open `http://localhost:3000`.
   2. Click `Login` in the navbar. `[Screenshot: navbar with Login button highlighted]`.
   3. Type `customer@khanabazaar.dev` and click `Send code`.
   4. Switch to your log viewer tab (`http://localhost:8001`, `backend` tab).
   5. Find the OTP line — copy the 6-digit code.
   6. Switch back to the storefront tab. Paste the code into the OTP input.
   7. Click `Verify`. You land on the storefront, logged in as Priya Verma.
7. **Section: 5-minute demo script.** (anchor `#demo-script`) Step-by-step sequence designed to be performed live for a stakeholder.
   1. **As customer.** Set delivery address (skip if maps not configured). Open a store. Add 3 items to cart. Open cart drawer. Click "Checkout". Place order. Note order ID.
   2. **Switch to seller.** Logout. Log in as `seller@khanabazaar.dev` (same OTP-via-log dance). The dashboard shows the new order. Mark it packed → dispatched → delivered.
   3. **Switch to admin.** Logout. Log in as `admin@khanabazaar.dev`. Catalog tab — show the master products list. Sellers tab — show the pending application from `pending.seller@khanabazaar.dev`. Click Approve. The seller becomes active.
8. **Section: Page tour by role.** (anchor `#page-tour`) For each of the three primary roles, list every navigation item with a one-paragraph "what you see" description. Long-form, ~4–6 paragraphs per role. Source the navigation items from the actual frontend (e.g. seller dashboard has Services, Inventory, Orders; admin has Categories, Products, Sellers, Orders; customer has Browse, Cart, Account, Orders).
   - **Customer.** Home / store list, store detail (Instacart-style 3-pane), cart, checkout per-store, account → addresses / orders / settings.
   - **Seller.** Dashboard, services, inventory (per-product per-store), orders, store profile.
   - **Admin.** Catalog (services / categories / subcategories / master products), sellers (applications + approvals), orders (all stores), languages.
   Note: layout details may have shifted since this guide was written — if a button has moved, read it as descriptive intent, not literal location.
9. Footer: `← [Previous: Chapter 4 — Run the app for the first time](./04-first-run.md)  |  Next: [Chapter 6 — When things break](./06-troubleshooting.md) →`.

- [ ] **Step 7.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/05-demo-logins.md
grep -c '@khanabazaar.dev' docs/teammate-guide/05-demo-logins.md
```

Expected: first prints nothing; second prints at least `12` (admin + customer + 9 sellers + 3 application emails appear in the table at minimum, plus walkthrough mentions).

- [ ] **Step 7.3: Commit**

```bash
git add docs/teammate-guide/05-demo-logins.md
git commit -m "docs(teammate-guide): chapter 05 demo logins"
```

---

## Task 8: Chapter 06 — When things break

**Why now:** Earlier chapters reference troubleshooting anchors. Writing them in Task 8 lets us pre-define the exact anchor names (used everywhere) and audit them in Task 12. Anchors must match the cross-references already written in earlier chapters.

**Files:**
- Create: `docs/teammate-guide/06-troubleshooting.md`

- [ ] **Step 8.1: Write the chapter**

Required structure:

1. Heading + breadcrumb. No estimated-time callout (reference chapter, used as needed).
2. Intro: "Look up your error by symptom. Each entry shows what you see, why it happens, and how to fix it."
3. **Symptom-keyed index at top** — alphabetical jump links into the body. Roughly:
   - "Cannot connect to the Docker daemon" → `#docker-wont-start`
   - "Port 3000 already in use" → `#port-3000-in-use`
   - "Port 5432 already in use" → `#docker-compose-port-in-use`
   - "OTP not arriving" → `#otp-not-arriving`
   - "RefererNotAllowedMapError" → `#referrer-not-allowed`
   - "REQUEST_DENIED" → `#request-denied`
   - "For development purposes only" watermark → `#dev-watermark`
   - … (every anchor referenced from earlier chapters must appear in this index).
4. Body — grouped by category, every entry follows this 4-line template:

```markdown
### <Anchor heading>

**What you see.** <exact error quote, fenced if multi-line>

**Why it happens.** <1-2 sentences>

**How to fix.**

1. <step>
2. <step>

**If the fix does not work.** <next escalation or link to another anchor>
```

Required entries (anchor → coverage). Every anchor referenced from earlier chapters MUST appear:

**Install errors**
- `#virtualisation-disabled` — Task Manager shows Disabled; reboot, enter BIOS, enable VT-x/SVM.
- `#wsl-install-fails` — `wsl --install` errors. Sub-cases: not run as Administrator, virtualisation disabled, Windows Home N edition (rare).
- `#wsl-default-version` — `wsl` does not see Ubuntu but it appeared in Microsoft Store. Fix: `wsl --set-default-version 2`, then re-launch Ubuntu.
- `#network-timeout` — `Could not resolve archive.ubuntu.com` or `ETIMEDOUT` during apt/npm/uv. Fix: retry, check Wi-Fi, try mobile hotspot, see proxy entry.
- `#proxy-blocking-installs` — corporate / hostel proxy blocks downloads. Fix: set `HTTP_PROXY` and `HTTPS_PROXY` env in `~/.bashrc`, also set npm proxy (`npm config set proxy <url>`).
- `#antivirus-blocks-docker` — Docker installer rolls back. Fix: temporarily disable real-time protection.
- `#nvm-not-found` — `nvm: command not found` after install. Fix: close and reopen Ubuntu shell, or `source ~/.bashrc`.
- `#uv-not-found` — `uv: command not found` after install. Same fix.
- `#python-version-mismatch` — `uv sync` complains about Python version. Fix: `python3 --version` to confirm 3.12, install via Deadsnakes PPA if older.

**Docker errors**
- `#docker-wont-start` — `Cannot connect to the Docker daemon`. Fix: start Docker Desktop, wait for whale icon "Docker Desktop is running", retry.
- `#docker-wsl-backend` — Settings → General → "Use the WSL 2 based engine" not ticked. Fix: tick it, Apply & Restart.
- `#docker-compose-port-in-use` — `Bind for 0.0.0.0:5432 failed: port is already allocated`. Fix: another Postgres is running. Either stop it (Services → PostgreSQL → Stop) or change the project's `docker-compose.yml` port mapping.
- `#docker-compose-pulls-fail` — `pull access denied` / `manifest unknown`. Fix: rare; usually network. Retry, or `docker logout && docker compose pull`.
- `#docker-disk-full` — Docker Desktop disk-pressure warning. Fix: `docker system prune -a` to reclaim space.

**Backend errors**
- `#asyncpg-password-error` — `asyncpg.InvalidPasswordError` or `connection refused`. Fix: Postgres container not up. `docker compose ps`, then `docker compose up -d postgres`.
- `#dialect-not-supported` — `dialect 'postgres' is not supported`. Fix: `DATABASE_URL` is wrong scheme. Must be `postgresql+asyncpg://...`.
- `#redis-connection-refused` — `redis.exceptions.ConnectionError`. Fix: Redis container not up. `docker compose up -d redis`.
- `#alembic-not-up-to-date` — "Target database is not up to date" or two heads. Fix: `uv run alembic upgrade head`. If two heads, link engineer doc.
- `#seed-script-crashes` — `IntegrityError` on re-running seed. Fix: idempotent in normal use, but if data is corrupted, do `./scripts/dev.sh stop && docker compose down -v && docker compose up -d` then re-run migrate + seed.
- `#uv-sync-fails` — SSL cert error or "failed to fetch". Fix: usually proxy. Set `UV_NATIVE_TLS=1`, or fix proxy env vars. Link to `#proxy-blocking-installs`.
- `#dev-sh-start-fails` — backend or celery fails to start. Fix: read `./scripts/dev.sh logs backend` and `logs celery` to find the actual error.

**Frontend errors**
- `#npm-install-fails` — `ETIMEDOUT` / `ECONNRESET`. Fix: retry. If repeated, switch to Indian mirror: `npm config set registry https://registry.npmmirror.com`.
- `#npm-eacces` — `EACCES` permission denied. Fix: do **not** `sudo npm`. Reinstall Node via nvm so it lives in your home folder.
- `#blank-white-page` — frontend at `localhost:3000` shows blank white page. Fix: open browser console (F12), look for errors. Most often the backend is down — check `./scripts/dev.sh status`.
- `#frontend-cant-reach-api` — frontend loads but every API call 404s. Fix: confirm `NEXT_PUBLIC_API_URL=""` (empty string) in `frontend/.env.local`. Restart `npm run dev` after editing.
- `#hot-reload-broken` — code changes not picked up. Fix: disable Defender real-time scanning of project folder, or move project inside WSL filesystem (`~/projects/`, never `/mnt/c/...`).
- `#port-3000-in-use` — Next.js says port already in use. Fix: another dev server is running, or you started the app twice. `./scripts/dev.sh status` and `./scripts/dev.sh stop`.

**Login / OTP errors**
- `#otp-not-arriving` — login screen says code sent but log viewer is empty. Fix: confirm `EMAIL_PROVIDER="console"` in `backend/app/.env`. Restart with `./scripts/dev.sh restart`. Check log viewer's `backend` tab again.
- `#otp-invalid` — "Invalid OTP" after pasting. Fix: code is 6 digits, no spaces. Expires after 10 minutes. After 5 wrong attempts you are locked out for an hour — wait, then request again.
- `#user-does-not-exist` — "User does not exist" on login. Fix: the email you typed was not seeded. Use one from chapter 5's table.

**Map errors**
- `#referrer-not-allowed` — `RefererNotAllowedMapError` in browser console. Fix: browser key referrer restrictions don't include `http://localhost:3000/*`. Add it in GCP Credentials → key → HTTP referrers.
- `#request-denied` — `REQUEST_DENIED` from `/api/v1/geo/*`. Fix: server key is missing API restrictions (Places + Geocoding) OR billing is not enabled on the GCP project.
- `#dev-watermark` — map renders gray with "For development purposes only" watermark. Fix: same as `#referrer-not-allowed` plus billing check.
- `#over-query-limit` — `OVER_QUERY_LIMIT`. Fix: rare for the demo; raise the per-day quota in GCP Quotas, or wait 24h.

5. **Section: Nothing here matches.** (anchor `#nothing-here-matches`) Slack template:
   ```
   Hey, I'm stuck on the teammate guide.

   Chapter / step: <e.g. Chapter 4, "Bring up Postgres and Redis">

   What I ran:
   <paste command>

   What I see (exact error, full message):
   <paste error>

   Output of `./scripts/dev.sh status`:
   <paste output>

   Output of `docker compose ps`:
   <paste output>

   Last 30 lines of relevant log (`./scripts/dev.sh logs backend | tail -30`):
   <paste log lines>
   ```

6. Footer: `← [Previous: Chapter 5 — Demo accounts and login flow](./05-demo-logins.md)  |  Next: [Chapter 7 — Day-to-day after install](./07-daily-use.md) →`.

- [ ] **Step 8.2: Verify all anchors referenced from earlier chapters exist here**

```bash
# Pull every anchor reference into 06-troubleshooting from other chapter files
grep -hoE '\./06-troubleshooting\.md#[a-z0-9-]+' docs/teammate-guide/*.md \
  | sort -u \
  | sed 's|.*#||' \
  | while read anchor; do
      if ! grep -q "^### .*$" docs/teammate-guide/06-troubleshooting.md; then break; fi
      grep -q "^### .*{#${anchor}}\$\\|^### \(.*\)\$" docs/teammate-guide/06-troubleshooting.md && \
        grep -q -i "^### \(${anchor}\\| ${anchor//-/ }\)" docs/teammate-guide/06-troubleshooting.md \
        || echo "MISSING ANCHOR: ${anchor}"
    done
```

The exact grep pattern is fiddly because GitHub renders `### Anchor heading` to a slug derived from the heading text. The pragmatic check is:

```bash
# 1. List anchor refs found in other chapters
grep -hoE '\./06-troubleshooting\.md#[a-z0-9-]+' docs/teammate-guide/*.md | sort -u

# 2. List anchor headings in chapter 06 (third-level headings, lowercased and hyphenated)
grep -E '^### ' docs/teammate-guide/06-troubleshooting.md \
  | sed 's/^### //; s/[^a-zA-Z0-9 -]//g; s/ /-/g; y/ABCDEFGHIJKLMNOPQRSTUVWXYZ/abcdefghijklmnopqrstuvwxyz/'
```

Compare both lists by eye. Every entry in list 1 must appear in list 2 (or be added — preferred — by adding a missing entry).

Expected: no MISSING-ANCHOR lines (or, in the second pragmatic form, every referenced anchor appears in the list of headings).

- [ ] **Step 8.3: Banned-words check**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/06-troubleshooting.md
```

Expected: nothing prints.

- [ ] **Step 8.4: Commit**

```bash
git add docs/teammate-guide/06-troubleshooting.md
git commit -m "docs(teammate-guide): chapter 06 troubleshooting"
```

---

## Task 9: Chapter 07 — Day-to-day after install

**Files:**
- Create: `docs/teammate-guide/07-daily-use.md`

- [ ] **Step 9.1: Write the chapter**

Required structure:

1. Heading + breadcrumb + estimated time ("Reference chapter — 5 minutes to skim").
2. Intro: "Once chapter 4 has worked once, every following day looks like this."
3. **Section: Open the project for the day.** (anchor `#starting`)
   ```
   cd ~/projects/KhanaBazaar
   ./scripts/dev.sh start
   ```
   Open the three browser tabs from chapter 4. That's it.
4. **Section: Stop for the day.** (anchor `#stopping`)
   ```
   ./scripts/dev.sh stop
   ```
   Optional: `./scripts/dev.sh stop --all` also stops Postgres and Redis if you are short on RAM.
5. **Section: Status and logs.** (anchor `#status-and-logs`)
   ```
   ./scripts/dev.sh status
   ./scripts/dev.sh logs backend
   ```
   Plain-English: status shows what is running. Logs follow the named service (one of `backend`, `celery`, `frontend`, `ngrok`, `log_viewer`). Press `Ctrl+C` to stop following.
6. **Section: Pull new code.** (anchor `#pull-new-code`)
   ```
   git pull
   ```
   - If backend changed (any file under `backend/app/`):
     ```
     cd backend/app
     uv sync
     uv run alembic upgrade head
     cd ../..
     ```
   - If frontend changed (any file under `frontend/`):
     ```
     cd frontend
     npm install
     cd ..
     ```
   - Restart the app: `./scripts/dev.sh restart`.
7. **Section: When to re-seed.** (anchor `#re-seed`) Plain-English: only when the demo data feels broken or the engineer says so.
   ```
   cd backend/app
   uv run python scripts/seed_database.py
   cd ../..
   ```
8. **Section: Updating tools.** (anchor `#updating-tools`)
   - Docker Desktop: built-in updater notifies; click and apply.
   - WSL: **Run in: PowerShell** — `wsl --update`.
   - Node: `nvm install --lts` to install latest LTS, `nvm alias default <version>` to switch.
   - uv: `uv self update`.
9. **Section: Reading logs to find your own answers.** (anchor `#reading-logs`)
   - What to look for: `INFO` is normal; `WARNING` is suspicious; `ERROR` and `CRITICAL` are real problems.
   - One example of each, formatted as fenced log lines.
   - Tip: use the log viewer (`http://localhost:8001`) for colourised tabs, or `./scripts/dev.sh logs <service>` for live tail.
10. **Section: Reset to a clean slate.** (anchor `#reset-everything`) Plain-English warning: "**This deletes all your demo data.** Use only when nothing else has worked. Takes about 5 minutes."
    ```
    ./scripts/dev.sh stop --all
    docker compose down -v
    docker compose up -d
    cd backend/app
    uv run alembic upgrade head
    uv run python scripts/seed_database.py
    cd ../..
    ./scripts/dev.sh start
    ```
11. Footer: `← [Previous: Chapter 6 — When things break](./06-troubleshooting.md)  |  Next: [Appendix — Phone testing (optional)](./appendix-mobile-ngrok.md) →`.

- [ ] **Step 9.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/07-daily-use.md
```

Expected: nothing prints.

- [ ] **Step 9.3: Commit**

```bash
git add docs/teammate-guide/07-daily-use.md
git commit -m "docs(teammate-guide): chapter 07 daily use"
```

---

## Task 10: Appendix — Phone testing (optional ngrok flow)

**Files:**
- Create: `docs/teammate-guide/appendix-mobile-ngrok.md`

- [ ] **Step 10.1: Write the appendix**

Required structure:

1. Heading + breadcrumb + estimated time (~15 minutes first time, ~30 seconds afterwards).
2. **Top-of-page skip callout:** "**Skip this if you only need desktop demos.** This appendix shows you how to open the dev app on your phone over mobile data — useful for showing real shopper experience to stakeholders."
3. **Section: What it does.** Two-paragraph plain-English explanation of what ngrok is — a service that gives your laptop a temporary public URL. Reassurance: only the frontend (`localhost:3000`) is exposed; the backend stays loopback-only and Next.js proxies API calls server-side.
4. **Section: One-time setup.** (anchor `#one-time-setup`)
   1. **Click in: web browser** — go to `https://ngrok.com`, click Sign up (free).
   2. After signing in, dashboard → "Your Authtoken" → copy.
   3. **Run in: WSL2 Ubuntu terminal** — install ngrok via apt:
      ```
      curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
      echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
      sudo apt update
      sudo apt install -y ngrok
      ```
   4. Authenticate (one-time):
      ```
      ngrok config add-authtoken <paste-your-token>
      ```
5. **Section: Each session.** (anchor `#each-session`)
   ```
   ./scripts/dev.sh start --tunnel
   ```
   **What you should see:** the usual `start` output plus a `Tunnel ready: https://abc-123.ngrok-free.app  ->  :3000` line. Copy that URL.
   ```
   ./scripts/dev.sh tunnel-url
   ```
   Reprints the URL whenever you forget.
6. **Section: Open it on the phone.** (anchor `#open-on-phone`)
   1. On the phone, open Chrome (Android) or Safari (iOS).
   2. Type the ngrok URL.
   3. The first time, you see a one-time ngrok interstitial warning — click "Visit Site".
   4. The KhanaBazaar storefront loads. `[Screenshot: ngrok interstitial warning page, Visit Site button highlighted]`.
7. **Section: Install as a Progressive Web App.** (anchor `#install-pwa`)
   - Android Chrome: three-dot menu → "Add to Home Screen". The app installs as an icon on the home screen and opens fullscreen.
   - iOS Safari: Share → "Add to Home Screen".
   - Plain-English: this is a *PWA* — a website that can install like an app. It still runs from your laptop, not the App Store.
8. **Section: Common gotchas.** (anchor `#mobile-gotchas`)
   - The ngrok URL **changes every restart** on the free plan. Re-copy it from `tunnel-url`. The frontend uses relative API paths so the app does not break — only the URL you type.
   - First request through the tunnel sometimes 502s while Next.js compiles the entry route. Reload after 5 seconds.
   - `NEXT_PUBLIC_API_URL` in `frontend/.env.local` **must remain empty**. If you set it to `http://localhost:8000` the phone tries to reach your laptop's localhost (which it cannot) and every API call fails.
   - If the tunnel won't start, check `./scripts/dev.sh logs ngrok`. Most often: token not configured or quota exhausted.
9. Footer: `← [Previous: Chapter 7 — Day-to-day after install](./07-daily-use.md)  |  Next: [Appendix — Glossary](./appendix-glossary.md) →`.

- [ ] **Step 10.2: Verify**

```bash
grep -nE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/appendix-mobile-ngrok.md
```

Expected: nothing prints.

- [ ] **Step 10.3: Commit**

```bash
git add docs/teammate-guide/appendix-mobile-ngrok.md
git commit -m "docs(teammate-guide): appendix mobile ngrok"
```

---

## Task 11: Glossary footer fix-up

The glossary was written first (Task 1) before the linear chapter chain existed. Its footer says "Previous: Mobile testing" — confirm that link still resolves. If Task 1's footer wording differs from the final chain established by tasks 2–10, fix it.

**Files:**
- Modify: `docs/teammate-guide/appendix-glossary.md` (footer line only)

- [ ] **Step 11.1: Open and confirm footer**

Open `docs/teammate-guide/appendix-glossary.md`. Confirm the last line reads exactly:

```
← [Previous: Appendix — Mobile testing](./appendix-mobile-ngrok.md)  |  [Back to start](./README.md)
```

If it differs, edit it to match. If it already matches, no change needed (skip the commit).

- [ ] **Step 11.2: Commit if changed**

```bash
git diff --quiet docs/teammate-guide/appendix-glossary.md || (git add docs/teammate-guide/appendix-glossary.md && git commit -m "docs(teammate-guide): align glossary footer link")
```

---

## Task 12: Cross-link audit + final read-through

**Why last:** Every cross-link target now exists. Catch broken anchors, missing files, banned words, and voice drift before opening a PR.

**Files:**
- No file creation. May modify any chapter to fix a broken link.

- [ ] **Step 12.1: Verify every cross-linked file exists**

```bash
grep -hoE '\]\(\./[a-zA-Z0-9_./#-]+\)' docs/teammate-guide/*.md \
  | sed 's/^](\.\///; s/)$//; s/#.*//' \
  | sort -u \
  | while read f; do
      [ -f "docs/teammate-guide/${f}" ] || echo "MISSING FILE: ${f}"
    done
```

Expected: nothing prints. If `MISSING FILE: <path>` appears, find and fix the bad link in whichever chapter referenced it.

- [ ] **Step 12.2: Verify every cross-link anchor in chapter 06 resolves**

```bash
# Anchors referenced from any chapter pointing at 06-troubleshooting
grep -hoE '\./06-troubleshooting\.md#[a-z0-9-]+' docs/teammate-guide/*.md \
  | sort -u \
  | sed 's|.*#||' > /tmp/refs.txt

# Headings in 06 (level 3, slugified)
grep -E '^### ' docs/teammate-guide/06-troubleshooting.md \
  | sed 's/^### //; s/[^a-zA-Z0-9 -]//g; s/ /-/g' \
  | tr 'A-Z' 'a-z' \
  | sort -u > /tmp/headings.txt

# Refs that do not match any heading
comm -23 /tmp/refs.txt /tmp/headings.txt
```

Expected: nothing prints (no orphan references). If anything prints, either fix the link or add the missing entry to chapter 06.

- [ ] **Step 12.3: Banned-words sweep across the directory**

```bash
grep -rnE '\b(just|simply|obviously|easy)\b' docs/teammate-guide/
```

Expected: nothing prints. If anything appears, rewrite that line. Important nuance: "easy" inside a quoted error message or third-party UI label may need to stay — judge each hit on its own. Banned-word rule applies to *our prose*, not to literal labels.

- [ ] **Step 12.4: Linear footer chain check**

Make sure the previous/next chain matches the chapter order:

```
README.md          → next: 01
01-install-tools   ← README, next: 02
02-clone-and-env   ← 01, next: 03
03-google-maps     ← 02, next: 04
04-first-run       ← 03, next: 05
05-demo-logins     ← 04, next: 06
06-troubleshooting ← 05, next: 07
07-daily-use       ← 06, next: appendix-mobile-ngrok
appendix-mobile-ngrok ← 07, next: appendix-glossary
appendix-glossary  ← appendix-mobile-ngrok, [Back to start]
```

```bash
grep -nE '^(←|Next:)' docs/teammate-guide/*.md
```

Read the output by eye against the chain above. Fix any mismatches.

- [ ] **Step 12.5: Final placeholder scan**

```bash
grep -rnE '(TODO|TBD|XXX|FIXME)' docs/teammate-guide/
```

Expected: zero hits. The `[Screenshot: ...]` markers are intentional and live; do not remove them.

- [ ] **Step 12.6: Add a line to the top-level `README.md` pointing teammates at the new guide**

The repo's main `README.md` is engineer-flavoured. Add a short callout near the top so a teammate cloning a fresh repo finds the guide.

Open `README.md` in the repo root. Find the existing `## Local Setup` heading. Insert a new section *immediately above it*:

```markdown
## For non-engineer teammates

If you are not a developer and have never installed Docker / Node / Python before, follow [the teammate onboarding guide](docs/teammate-guide/README.md) instead. It walks Windows users through every install step from scratch and ends with a working demo.

```

Plain-English single sentence; no fanfare.

- [ ] **Step 12.7: Final commit + push to branch**

```bash
git add README.md
git commit -m "docs: link teammate onboarding guide from main README"
```

(Do not push to `origin` from this plan — the user opens the PR explicitly. Branch already exists at `docs/teammate-onboarding-guide`.)

---

## Self-review (executor: do not skip)

**1. Spec coverage.** Walk every section in `docs/superpowers/specs/2026-05-08-teammate-onboarding-guide-design.md` and tick which task implements it:

| Spec section | Implemented by |
|---|---|
| §4.1 File layout | Tasks 1–11 (one task per file) |
| §4.2 Navigation rules | Tasks 2–10 footers; Task 12.4 chain check |
| §4.3 Voice & style rules | Per-task verify steps; Task 12.3 sweep |
| §5.1 README cover page | Task 2 |
| §5.2 Chapter 01 install tools | Task 3 |
| §5.3 Chapter 02 clone and env | Task 4 |
| §5.4 Chapter 03 maps keys | Task 6 |
| §5.5 Chapter 04 first run | Task 5 |
| §5.6 Chapter 05 demo logins | Task 7 |
| §5.7 Chapter 06 troubleshooting | Task 8 |
| §5.8 Chapter 07 daily use | Task 9 |
| §5.9 Appendix mobile ngrok | Task 10 |
| §5.10 Appendix glossary | Task 1 |
| §6 Implementation order | Task numbering matches spec §6 ordering exactly |
| §7 Validation | Task 12 |
| §8 Open questions / risks | Documented in spec, not actionable in plan; flagged in Task 12.5 placeholder scan and Task 11 footer audit |

If any row is empty when you reach this check, the plan has a gap — flag it before continuing.

**2. Placeholder scan.** Search the plan for forbidden patterns: `TBD`, `TODO`, `implement later`, `add appropriate`, `similar to Task`, `etc.` (used loosely), `fill in details`. Inline `[Screenshot: ...]` markers are intentional and stay.

**3. Type / name consistency.** Compare across tasks:
- File names: every chapter file is referenced in the file structure table (top of plan), the cover page chapter index (Task 2), and at least two footers. They must match exactly. Audit by eye:
  - `README.md`, `01-install-tools.md`, `02-clone-and-env.md`, `03-google-maps-keys.md`, `04-first-run.md`, `05-demo-logins.md`, `06-troubleshooting.md`, `07-daily-use.md`, `appendix-mobile-ngrok.md`, `appendix-glossary.md`.
- Anchor names: every `#anchor` referenced in chapters 02 / 03 / 04 / 05 / 07 must exist as a heading in chapter 06 (Task 8 covers this; Task 12.2 verifies).
- Env-var names match exactly: `JWT_SECRET`, `OTP_PEPPER`, `EMAIL_PROVIDER`, `GOOGLE_MAPS_SERVER_API_KEY`, `GOOGLE_MAPS_BROWSER_API_KEY`, `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`, `NEXT_PUBLIC_API_URL`. Do not invent variants.
- Demo-account email format: every reference uses `<role>@khanabazaar.dev` and `pending.seller`/`approved.seller`/`rejected.seller` for application records.

If any name is inconsistent in your draft, fix it before commit.
