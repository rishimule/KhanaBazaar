# Chapter 6 — When things break

*Teammate Guide > Chapter 6: When things break*

Look up your error by symptom. Each entry shows what you see, why it happens, and how to fix it. If nothing here matches, use the message template at the bottom of this page to send to your engineer.

---

## Index by symptom

| What you see | Jump to |
|---|---|
| `Cannot connect to the Docker daemon` | [#docker-wont-start](#docker-wont-start) |
| `docker: 'compose' is not a docker command` | [#docker-wont-start](#docker-wont-start) |
| `Port 3000 already in use` | [#port-3000-in-use](#port-3000-in-use) |
| `Port 5432 already in use` | [#docker-compose-port-in-use](#docker-compose-port-in-use) |
| `Port 6379 already in use` | [#docker-compose-port-in-use](#docker-compose-port-in-use) |
| `asyncpg.InvalidPasswordError` or `connection refused (Postgres)` | [#asyncpg-password-error](#asyncpg-password-error) |
| `redis.exceptions.ConnectionError` | [#redis-connection-refused](#redis-connection-refused) |
| `dialect 'postgres' is not supported` | [#dialect-not-supported](#dialect-not-supported) |
| `Target database is not up to date` | [#alembic-not-up-to-date](#alembic-not-up-to-date) |
| `IntegrityError` during seed script | [#seed-script-crashes](#seed-script-crashes) |
| `uv: command not found` | [#uv-not-found](#uv-not-found) |
| `nvm: command not found` | [#nvm-not-found](#nvm-not-found) |
| `uv sync` SSL error or `failed to fetch` | [#uv-sync-fails](#uv-sync-fails) |
| `npm install` times out or `ECONNRESET` | [#npm-install-fails](#npm-install-fails) |
| `npm install` EACCES permission denied | [#npm-eacces](#npm-eacces) |
| `dev.sh start` crashes or hangs | [#dev-sh-start-fails](#dev-sh-start-fails) |
| Frontend shows blank white page | [#blank-white-page](#blank-white-page) |
| Frontend cannot reach the API (`ERR_CONNECTION_REFUSED`) | [#frontend-cant-reach-api](#frontend-cant-reach-api) |
| Hot reload not working | [#hot-reload-broken](#hot-reload-broken) |
| OTP code never arrives | [#otp-not-arriving](#otp-not-arriving) |
| `Invalid OTP` or `Incorrect OTP` | [#otp-invalid](#otp-invalid) |
| `User does not exist` at login | [#user-does-not-exist](#user-does-not-exist) |
| `RefererNotAllowedMapError` | [#referrer-not-allowed](#referrer-not-allowed) |
| `REQUEST_DENIED` from Maps | [#request-denied](#request-denied) |
| "For development purposes only" map watermark | [#dev-watermark](#dev-watermark) |
| `OVER_QUERY_LIMIT` from Maps | [#over-query-limit](#over-query-limit) |
| `Could not resolve archive.ubuntu.com` / `ETIMEDOUT` | [#network-timeout](#network-timeout) |
| Antivirus blocks Docker installer | [#antivirus-blocks-docker](#antivirus-blocks-docker) |
| `apt-get update` hangs | [#apt-update-hangs](#apt-update-hangs) |
| `python3 --version` shows older than 3.12 | [#python-version-mismatch](#python-version-mismatch) |
| `pull access denied` / `manifest unknown` on `docker compose pull` | [#docker-compose-pulls-fail](#docker-compose-pulls-fail) |
| Docker Desktop: "no space left on device" | [#docker-disk-full](#docker-disk-full) |
| WSL install fails | [#wsl-install-fails](#wsl-install-fails) |
| WSL does not see Ubuntu after install | [#wsl-default-version](#wsl-default-version) |
| Docker Desktop "WSL 2 based engine" error | [#docker-wsl-backend](#docker-wsl-backend) |
| Virtualisation-related BIOS error | [#virtualisation-disabled](#virtualisation-disabled) |
| Corporate or college proxy blocks installs | [#proxy-blocking-installs](#proxy-blocking-installs) |
| Nothing here matches | [#nothing-here-matches](#nothing-here-matches) |

---

## Install errors

### Virtualisation disabled in BIOS {#virtualisation-disabled}

**What you see.**

```
Hardware assisted virtualization and data execution protection must be enabled in the BIOS.
```

Or Docker Desktop refuses to start with a message about VT-x / AMD-V not being available.

**Why it happens.** *[Docker](./appendix-glossary.md#docker)* requires hardware virtualisation support. On many new machines it ships turned off in the BIOS/UEFI.

**How to fix.**

1. Restart the machine and enter BIOS/UEFI setup (usually **Delete**, **F2**, or **F10** during boot — your machine's startup screen shows the key).
2. Look for a setting called **Intel VT-x**, **Intel Virtualization Technology**, **AMD-V**, or **SVM Mode**.
3. Enable it and save (usually **F10**).
4. Boot back into Windows, then retry the Docker Desktop installer.

**If the fix does not work.** The BIOS option may be locked by your IT department. Ask them to enable virtualisation for your machine, then retry.

---

### WSL install fails {#wsl-install-fails}

**What you see.**

```
WslRegisterDistribution failed with error: 0x8007019e
```

Or an "Access is denied" error when running `wsl --install`.

**Why it happens.** The three most common causes: you did not run PowerShell as Administrator, hardware virtualisation is disabled (see [#virtualisation-disabled](#virtualisation-disabled)), or the Windows Feature "Virtual Machine Platform" is not enabled. On Windows Home N editions, the "Media Feature Pack" may be required too.

**How to fix.**

1. Right-click the Start menu → **Windows PowerShell (Admin)** or **Terminal (Admin)**.
2. Run:
   ```powershell
   wsl --install
   ```
3. Restart when prompted.
4. After restart, open PowerShell (Admin) again and verify:
   ```powershell
   wsl --list --verbose
   ```
5. If error code `0x80370102` appears, virtualisation is disabled — see [#virtualisation-disabled](#virtualisation-disabled).
6. If you are on Windows Home N, install the **Media Feature Pack** from Settings → Apps → Optional features.

**If the fix does not work.** Run `wsl --status` and share the output with the engineer via the template at [#nothing-here-matches](#nothing-here-matches).

---

### WSL does not see Ubuntu {#wsl-default-version}

**What you see.** After running `wsl --install`, opening Ubuntu from the Start menu shows a blank screen or immediately closes.

**Why it happens.** *[WSL](./appendix-glossary.md#wsl)* may have defaulted to version 1, which does not support the Docker backend. Or the Ubuntu distribution registered but is not set as default.

**How to fix.**

1. Open PowerShell (Admin) and force WSL 2 as the default:
   ```powershell
   wsl --set-default-version 2
   ```
2. Set Ubuntu as the default distribution:
   ```powershell
   wsl --set-default Ubuntu
   ```
3. Re-launch Ubuntu from the Start menu.
4. Confirm the WSL version:
   ```powershell
   wsl --list --verbose
   ```
   The `VERSION` column should show `2` for Ubuntu.

**If the fix does not work.** If Ubuntu shows `Stopped` or `Converting`, run `wsl --shutdown` then reopen Ubuntu. If it still fails, see [#wsl-install-fails](#wsl-install-fails).

---

### Network timeouts during apt / npm / uv {#network-timeout}

**What you see.**

```
Could not resolve 'archive.ubuntu.com'
```

or

```
ETIMEDOUT
npm ERR! network request timed out
```

**Why it happens.** A slow or blocked network connection prevented the package manager from reaching the download server. This often happens on a corporate or college network — see [#proxy-blocking-installs](#proxy-blocking-installs).

**How to fix.**

1. Check that your Wi-Fi or ethernet connection is active.
2. Open a browser and confirm you can reach https://google.com.
3. Try switching to a mobile hotspot.
4. Retry the failing command:
   ```bash
   sudo apt-get update
   ```
5. If you are behind a corporate proxy, set the proxy environment variables first — see [#proxy-blocking-installs](#proxy-blocking-installs).

**If the fix does not work.** Check your DNS by running `nslookup archive.ubuntu.com`. If it returns nothing, edit `/etc/resolv.conf` and add `nameserver 8.8.8.8` on a new line, then retry.

---

### Corporate or college proxy blocks installs {#proxy-blocking-installs}

**What you see.** Package installs time out or return SSL errors even though the browser works fine. This is common on office or campus networks.

**Why it happens.** A proxy server sits between your machine and the internet, and the package managers do not know about it unless told.

**How to fix.**

1. Ask your IT team for the proxy address. It usually looks like `http://proxy.example.com:3128`.
2. Add these lines to `~/.bashrc` (replace the URL with your real proxy):
   ```bash
   export HTTP_PROXY="http://proxy.example.com:3128"
   export HTTPS_PROXY="http://proxy.example.com:3128"
   export NO_PROXY="localhost,127.0.0.1"
   ```
3. Reload the *[shell](./appendix-glossary.md#shell--terminal)*:
   ```bash
   source ~/.bashrc
   ```
4. Configure npm:
   ```bash
   npm config set proxy http://proxy.example.com:3128
   npm config set https-proxy http://proxy.example.com:3128
   ```
5. For *[uv](./appendix-glossary.md#uv)*, set `UV_NATIVE_TLS=1` if the proxy intercepts TLS — see also [#uv-sync-fails](#uv-sync-fails).

**If the fix does not work.** Ask IT whether the proxy requires authentication (username/password) or a custom CA certificate. If a custom CA is needed, add it to your system trust store and set `REQUESTS_CA_BUNDLE` for Python tools.

---

### Antivirus blocks Docker installer {#antivirus-blocks-docker}

**What you see.** The Docker Desktop `.exe` installer is quarantined, deleted, or the install completes but Docker never starts.

**Why it happens.** Some antivirus software (Windows Defender, McAfee, Bitdefender) flags Docker installer or its kernel components as suspicious because they modify system virtualisation settings.

**How to fix.**

1. Open your antivirus dashboard and temporarily disable **real-time protection**.
2. Re-run the Docker Desktop installer.
3. When the installer finishes and Docker Desktop is confirmed running (look for the whale icon in the system tray), re-enable real-time protection.
4. Add the Docker directories to your antivirus exclusion list so future updates do not get blocked:
   - `C:\Program Files\Docker`
   - `C:\Users\<you>\AppData\Local\Docker`

**If the fix does not work.** Your IT policy may block all virtualisation tools. Contact IT and ask them to whitelist Docker Desktop.

---

### apt update hangs {#apt-update-hangs}

**What you see.** Running `sudo apt-get update` freezes and never completes.

**Why it happens.** The package server is unreachable — typically a DNS failure or a proxy blocking the connection. See [#network-timeout](#network-timeout) and [#proxy-blocking-installs](#proxy-blocking-installs).

**How to fix.**

1. Press **Ctrl+C** to cancel.
2. Test DNS:
   ```bash
   nslookup archive.ubuntu.com
   ```
3. If DNS fails, add Google's DNS to WSL:
   ```bash
   echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
   ```
4. Retry:
   ```bash
   sudo apt-get update
   ```
5. If you are on a corporate network, set proxy variables first — see [#proxy-blocking-installs](#proxy-blocking-installs).

**If the fix does not work.** Switch to a mobile hotspot and retry. If it works on hotspot but not the office network, the proxy is blocking you — escalate to IT.

---

### nvm: command not found {#nvm-not-found}

**What you see.**

```
nvm: command not found
```

**Why it happens.** *[npm](./appendix-glossary.md#npm)* / Node are installed via nvm, but nvm's shell initialisation lines have not been loaded yet in the current session.

**How to fix.**

1. Close the Ubuntu terminal window completely.
2. Open a fresh Ubuntu terminal.
3. Run:
   ```bash
   nvm --version
   ```
4. If it still fails, check that these lines exist in `~/.bashrc`:
   ```bash
   export NVM_DIR="$HOME/.nvm"
   [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
   ```
5. If the lines are missing, reinstall nvm following chapter 1, §5, then reload:
   ```bash
   source ~/.bashrc
   ```

**If the fix does not work.** Run `ls ~/.nvm/nvm.sh` — if the file is absent, nvm was not installed. Follow chapter 1 §5 from the beginning.

---

### uv: command not found {#uv-not-found}

**What you see.**

```
uv: command not found
```

**Why it happens.** *[uv](./appendix-glossary.md#uv)* was installed but its binary location was not added to `PATH` in the current session.

**How to fix.**

1. Close the Ubuntu terminal and open a fresh one.
2. Run:
   ```bash
   uv --version
   ```
3. If it still fails, reload your shell config:
   ```bash
   source ~/.bashrc
   ```
4. If uv was never installed, install it now:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source ~/.bashrc
   ```

**If the fix does not work.** Run `which uv` — if blank, uv is not installed. Check chapter 1 §6 and reinstall.

---

### Python version mismatch {#python-version-mismatch}

**What you see.**

```
python3 --version
Python 3.10.12
```

The *[backend](./appendix-glossary.md#backend)* requires Python 3.12 or newer.

**Why it happens.** Ubuntu ships with an older Python. The Deadsnakes PPA provides newer versions without overwriting the system default.

**How to fix.**

1. Add the Deadsnakes PPA and install Python 3.12:
   ```bash
   sudo add-apt-repository ppa:deadsnakes/ppa -y
   sudo apt-get update
   sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
   ```
2. Confirm:
   ```bash
   python3.12 --version
   ```
3. When running uv commands, uv picks up Python 3.12 automatically because `pyproject.toml` declares `requires-python = ">=3.12"`. If it does not, run:
   ```bash
   uv python pin 3.12
   ```
4. Follow chapter 1 §6 if you need a full walkthrough.

**If the fix does not work.** Run `uv python list` to see which Python versions uv can find and share the output with the engineer.

---

## Docker errors

### Cannot connect to the Docker daemon {#docker-wont-start}

**What you see.**

```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
```

**Why it happens.** *[Docker](./appendix-glossary.md#docker)* Desktop is not running, or it has not finished starting up.

**How to fix.**

1. Open Docker Desktop from the Start menu.
2. Wait for the whale icon in the system tray to show "Docker Desktop is running" (it can take 30–60 seconds).
3. If you see `docker: 'compose' is not a docker command`, you have an old Docker without Compose V2. Verify with `docker compose version`. If it fails, reinstall Docker Desktop from https://www.docker.com/products/docker-desktop/ — current versions ship Compose V2 built-in.
4. Retry your command.
5. If Docker Desktop shows an error on launch, restart the machine and try again.

**If the fix does not work.** Check that WSL 2 is installed and working — see [#docker-wsl-backend](#docker-wsl-backend). If Docker Desktop crashes on startup, reinstall it.

---

### Docker WSL 2 backend not enabled {#docker-wsl-backend}

**What you see.**

```
Docker Desktop requires a newer WSL kernel version.
```

Or Docker Desktop opens but shows "WSL 2 installation is incomplete."

**Why it happens.** Docker Desktop on Windows uses *[WSL](./appendix-glossary.md#wsl)* 2 as its engine. If WSL 2 is not the default version, Docker falls back to Hyper-V or fails entirely.

**How to fix.**

1. Open Docker Desktop.
2. Go to **Settings** → **General**.
3. Turn on **Use the WSL 2 based engine**.
4. Click **Apply & Restart**.
5. After Docker restarts, open a WSL terminal and confirm:
   ```bash
   docker --version
   ```

**If the fix does not work.** Run `wsl --update` in PowerShell (Admin) to update the WSL kernel, then restart Docker Desktop.

---

### docker compose up — port already in use {#docker-compose-port-in-use}

**What you see.**

```
Error response from daemon: driver failed programming external connectivity on endpoint ...:
Bind for 0.0.0.0:5432 failed: port is already allocated
```

Port 5432 (*[PostgreSQL](./appendix-glossary.md#postgresql)*) or 6379 (*[Redis](./appendix-glossary.md#redis)*) is already in use.

**Why it happens.** Another PostgreSQL or Redis service is running on your machine — either a leftover container or a native installation.

**How to fix.**

1. Find what is holding the port:
   ```bash
   sudo lsof -i :5432
   # or for Redis:
   sudo lsof -i :6379
   ```
2. If it is a native PostgreSQL service:
   ```bash
   sudo service postgresql stop
   ```
3. If it is another *[Docker](./appendix-glossary.md#docker)* container:
   ```bash
   docker ps
   docker stop <container_id>
   ```
4. Retry:
   ```bash
   docker compose up -d
   ```

**If the fix does not work.** Edit `docker-compose.yml` and change the host-side port mapping (left side of `:`), for example `"5433:5432"`, then update `DATABASE_URL` in `backend/app/.env` to match.

---

### docker compose pulls fail {#docker-compose-pulls-fail}

**What you see.**

```
pull access denied for postgis/postgis, repository does not exist or may require 'docker login'
```

or

```
manifest unknown
```

**Why it happens.** Docker cannot reach Docker Hub to download the image — usually a network problem, occasionally an expired Docker login session.

**How to fix.**

1. Check your network connection.
2. Log out and back in to Docker Hub:
   ```bash
   docker logout
   docker login
   ```
3. Retry:
   ```bash
   docker compose pull
   docker compose up -d
   ```
4. If the network is slow, wait a few minutes and retry — Hub can be temporarily unavailable.

**If the fix does not work.** If you are behind a corporate proxy, configure the Docker daemon proxy settings in Docker Desktop → Settings → Resources → Proxies.

---

### Docker disk full {#docker-disk-full}

**What you see.**

```
no space left on device
```

or Docker Desktop shows a red disk-usage warning.

**Why it happens.** Old images, stopped containers, and unused volumes accumulate over time and fill up Docker's virtual disk.

**How to fix.**

1. Remove all unused Docker data (images, stopped containers, unused volumes and networks):
   ```bash
   docker system prune -a
   ```
   Type `y` when prompted. This is safe — it removes only data not attached to a running container.
2. If prompted for volumes specifically:
   ```bash
   docker volume prune
   ```
   **Warning:** this deletes your local *[database](./appendix-glossary.md#database)* data. Re-run migrations and seed after. See chapter 7 for the reset sequence.
3. Restart Docker Desktop if it was showing disk warnings.

**If the fix does not work.** In Docker Desktop → Settings → Resources → Disk image, increase the virtual disk size limit.

---

## Backend errors

### asyncpg.InvalidPasswordError or connection refused {#asyncpg-password-error}

**What you see.**

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "postgres"
```

or

```
asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation
```

or a bare `Connection refused` on port 5432.

**Why it happens.** The PostgreSQL *[container](./appendix-glossary.md#container)* is not running, or the `DATABASE_URL` in `.env` does not match the container's credentials.

**How to fix.**

1. Check whether the container is running:
   ```bash
   docker compose ps
   ```
2. If the `postgres` service shows `Exit` or is absent, start it:
   ```bash
   docker compose up -d postgres
   ```
3. Confirm the `DATABASE_URL` in `backend/app/.env` matches the values in `docker-compose.yml` (default user: `postgres`, password: `password`, db: `khanabazaar`).
4. Retry starting the backend.

**If the fix does not work.** Run `docker compose logs postgres` to check for startup errors, and share them using the template at [#nothing-here-matches](#nothing-here-matches).

---

### dialect 'postgres' is not supported {#dialect-not-supported}

**What you see.**

```
sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres
```

or

```
Could not parse rfc1738 URL from string 'postgres://...'
```

**Why it happens.** SQLAlchemy 2+ removed the short `postgres://` scheme. The *[backend](./appendix-glossary.md#backend)* requires the `asyncpg` driver and the full scheme.

**How to fix.**

1. Open `backend/app/.env`.
2. Find the `DATABASE_URL` line.
3. Change the scheme from `postgres://` to `postgresql+asyncpg://`:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar
   ```
4. Save and restart the backend.

**If the fix does not work.** Confirm the file was saved and no extra spaces or quotes were introduced around the value.

---

### redis.exceptions.ConnectionError {#redis-connection-refused}

**What you see.**

```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379. Connection refused.
```

**Why it happens.** The *[Redis](./appendix-glossary.md#redis)* *[container](./appendix-glossary.md#container)* is not running.

**How to fix.**

1. Check the container:
   ```bash
   docker compose ps
   ```
2. If `redis` shows `Exit` or is absent:
   ```bash
   docker compose up -d redis
   ```
3. Confirm it is reachable:
   ```bash
   docker compose exec redis redis-cli ping
   ```
   You should see `PONG`.
4. Restart the backend.

**If the fix does not work.** Check `REDIS_URL` in `backend/app/.env` — it should be `redis://localhost:6379/0`.

---

### Alembic — target database is not up to date {#alembic-not-up-to-date}

**What you see.**

```
ERROR [alembic.util.exc] Target database is not up to date.
```

or the backend crashes on startup with `relation "user" does not exist`.

**Why it happens.** You pulled new code that includes a *[migration](./appendix-glossary.md#migration)* file, but you have not applied it to your local *[database](./appendix-glossary.md#database)* yet.

**How to fix.**

1. From `backend/app/`:
   ```bash
   uv run alembic upgrade head
   ```
2. Confirm the migration applied without errors.
3. Restart the backend.

**If the fix does not work.** Run `uv run alembic heads` — if it shows two heads, the migration history has diverged. Do not attempt to merge them yourself; share the output with the engineer.

---

### Seed script crashes {#seed-script-crashes}

**What you see.**

```
sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: ...
```

or

```
asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint
```

**Why it happens.** The *[seed data](./appendix-glossary.md#seed-data)* script was run before, leaving partial or corrupt rows. Running it again hits duplicate-key violations.

**How to fix.**

1. Stop the stack:
   ```bash
   ./scripts/dev.sh stop
   ```
2. Tear down and recreate volumes (this wipes the local database):
   ```bash
   docker compose down -v
   docker compose up -d
   ```
3. Reapply migrations:
   ```bash
   cd backend/app
   uv run alembic upgrade head
   ```
4. Re-run the seed script.

For a full guided reset, follow chapter 7.

**If the fix does not work.** Share the full traceback with the engineer via [#nothing-here-matches](#nothing-here-matches).

---

### uv sync fails {#uv-sync-fails}

**What you see.**

```
error: Failed to fetch: `https://files.pythonhosted.org/...`
```

or an SSL certificate verification error.

**Why it happens.** Either a network problem or — most commonly on corporate networks — a proxy that intercepts TLS connections presents a different certificate than Python's trust store expects.

**How to fix.**

1. Set the native TLS flag so uv uses the system certificate store:
   ```bash
   export UV_NATIVE_TLS=1
   uv sync
   ```
2. To make this permanent, add `export UV_NATIVE_TLS=1` to `~/.bashrc`.
3. If still failing, confirm your proxy is configured — see [#proxy-blocking-installs](#proxy-blocking-installs).
4. Try on a mobile hotspot to rule out the corporate proxy.

**If the fix does not work.** Run `uv sync -v` for verbose output and share it with the engineer.

---

### dev.sh start fails {#dev-sh-start-fails}

**What you see.** `./scripts/dev.sh start` exits early or one of the services (backend, *[celery](./appendix-glossary.md#celery)*) immediately crashes.

**Why it happens.** The actual error is in the service logs, not in the start script output itself. The script stops when any managed process exits with a non-zero code.

**How to fix.**

1. Check the status of all services:
   ```bash
   ./scripts/dev.sh status
   ```
2. Read the logs for the failing service:
   ```bash
   ./scripts/dev.sh logs backend
   ./scripts/dev.sh logs celery
   ```
3. Find the specific error line and look it up in this chapter.
4. Common causes: *[database](./appendix-glossary.md#database)* not running ([#asyncpg-password-error](#asyncpg-password-error)), missing `.env` ([#uv-sync-fails](#uv-sync-fails)), unapplied migration ([#alembic-not-up-to-date](#alembic-not-up-to-date)).

**If the fix does not work.** Paste the full output of `./scripts/dev.sh logs backend | tail -30` into the message template at [#nothing-here-matches](#nothing-here-matches).

---

## Frontend errors

### npm install fails (ETIMEDOUT / ECONNRESET) {#npm-install-fails}

**What you see.**

```
npm ERR! code ETIMEDOUT
npm ERR! network request to https://registry.npmjs.org/... failed
```

or `ECONNRESET`.

**Why it happens.** The *[npm](./appendix-glossary.md#npm)* registry is slow or unreachable — usually a network or proxy problem.

**How to fix.**

1. Retry once — transient network errors often resolve on their own:
   ```bash
   npm install
   ```
2. Try a mirror registry (Indian CDN, works well on Indian ISPs):
   ```bash
   npm config set registry https://registry.npmmirror.com
   npm install
   ```
3. If behind a corporate proxy, set the proxy — see [#proxy-blocking-installs](#proxy-blocking-installs).

**If the fix does not work.** Switch to mobile hotspot. If it works there, the office network is the problem — see [#proxy-blocking-installs](#proxy-blocking-installs).

---

### npm install — EACCES permission denied {#npm-eacces}

**What you see.**

```
npm ERR! code EACCES
npm ERR! syscall mkdir
npm ERR! path /usr/local/lib/node_modules
```

**Why it happens.** Node.js was installed system-wide (via `apt` or with `sudo`), so its `node_modules` folder is owned by root. Installing packages as a regular user is then denied.

**How to fix.**

1. Do **not** run `sudo npm install` — that escalates the problem and makes future installs root-owned too.
2. Uninstall the system Node:
   ```bash
   sudo apt-get remove nodejs npm
   ```
3. Install Node via nvm (which puts it in your home folder, where you own it):
   ```bash
   nvm install --lts
   nvm use --lts
   ```
4. Retry:
   ```bash
   npm install
   ```

**If the fix does not work.** Run `which node` — if it points to `/usr/bin/node` instead of `~/.nvm/...`, nvm is not active. See [#nvm-not-found](#nvm-not-found).

---

### Frontend at localhost:3000 shows blank white page {#blank-white-page}

**What you see.** You open `http://localhost:3000` in the browser and see a completely blank page with no content and no visible error.

**Why it happens.** The most common cause is that the *[backend](./appendix-glossary.md#backend)* is not running, so the *[frontend](./appendix-glossary.md#frontend)* cannot load data. A React rendering crash can also produce a blank page.

**How to fix.**

1. Open browser DevTools (press **F12**) and check the **Console** tab for red errors.
2. Check the **Network** tab — look for API calls that return `ERR_CONNECTION_REFUSED`.
3. Check the dev stack status:
   ```bash
   ./scripts/dev.sh status
   ```
4. If the backend is down, start it — see [#dev-sh-start-fails](#dev-sh-start-fails).
5. If the console shows a JavaScript error, read the message — it usually names the component and the problem.

**If the fix does not work.** Share the full browser console output and the result of `./scripts/dev.sh status` with the engineer.

---

### Frontend cannot reach the API {#frontend-cant-reach-api}

**What you see.**

```
ERR_CONNECTION_REFUSED
```

in browser DevTools when the frontend makes API calls, or API calls return 404 unexpectedly.

**Why it happens.** The `NEXT_PUBLIC_API_URL` *[environment variable](./appendix-glossary.md#environment-variable)* is set to a wrong value. In development, it must be an empty string so Next.js uses relative paths and its built-in proxy to forward requests to `localhost:8000`.

**How to fix.**

1. Open `frontend/.env.local`.
2. Confirm this line is present and the value is empty:
   ```
   NEXT_PUBLIC_API_URL=
   ```
   or

   ```
   NEXT_PUBLIC_API_URL=""
   ```
3. If the value was wrong, save the file.
4. Restart the dev server — environment variables are baked in at build time:
   ```bash
   ./scripts/dev.sh restart
   ```
5. Also confirm the backend is running on port 8000 — see [#dev-sh-start-fails](#dev-sh-start-fails).

**If the fix does not work.** Open `http://localhost:8000/docs` directly in the browser. If *[Swagger](./appendix-glossary.md#swagger)* loads, the backend is up and the problem is in the env file or Next.js config. Share your `frontend/.env.local` (with secrets redacted) with the engineer.

---

### Hot reload not working {#hot-reload-broken}

**What you see.** You edit a file, save, but the browser does not refresh and the frontend does not update.

**Why it happens.** Two main causes on Windows: (1) Windows Defender's real-time protection scans files on write, breaking the file-watcher, or (2) the project lives on the Windows filesystem (`/mnt/c/...`) rather than inside WSL, where inotify events do not propagate correctly.

**How to fix.**

1. Check where the project lives:
   ```bash
   pwd
   ```
   If it starts with `/mnt/c/` or `/mnt/d/`, move it inside WSL:
   ```bash
   cp -r /mnt/c/KhanaBazaar ~/projects/KhanaBazaar
   cd ~/projects/KhanaBazaar
   ```
2. If the project is already inside WSL (`~/...`), add the project folder to Windows Defender's exclusion list:
   - Open Windows Security → Virus & threat protection → Manage settings → Exclusions → Add an exclusion → Folder.
   - Add the WSL path for your project.
3. Restart the frontend dev server after moving or changing exclusions.

**If the fix does not work.** You can force a manual page refresh with **Ctrl+Shift+R** while debugging. Share the terminal output from `./scripts/dev.sh logs frontend` with the engineer.

---

### Port 3000 already in use {#port-3000-in-use}

**What you see.**

```
Error: listen EADDRINUSE: address already in use :::3000
```

**Why it happens.** Another process — usually a previous *[frontend](./appendix-glossary.md#frontend)* dev server — is still running on *[port](./appendix-glossary.md#port)* 3000.

**How to fix.**

1. Check the dev stack:
   ```bash
   ./scripts/dev.sh status
   ```
2. Stop everything:
   ```bash
   ./scripts/dev.sh stop
   ```
3. If the port is still occupied, find and kill the process:
   ```bash
   lsof -i :3000
   kill -9 <PID>
   ```
4. Restart:
   ```bash
   ./scripts/dev.sh start
   ```

**If the fix does not work.** A different app (not KhanaBazaar) might be using port 3000. Run `lsof -i :3000` and share the output with the engineer so they can identify the culprit.

---

## Login / OTP errors

### OTP not arriving {#otp-not-arriving}

**What you see.** You request an *[OTP](./appendix-glossary.md#otp)* in the app, the request succeeds (200 OK), but no email or SMS arrives.

**Why it happens.** In development the default email and SMS providers are `console` — they print the code to the backend log instead of sending a real message.

**How to fix.**

1. Confirm the providers are set to `console` in `backend/app/.env`:
   ```
   EMAIL_PROVIDER=console
   SMS_PROVIDER=console
   ```
2. Look at the backend log for the OTP block:
   ```bash
   ./scripts/dev.sh logs backend
   ```
   Search for a block like:
   ```
   [EMAIL] to=user@example.com
   Your one-time login code is: 482913

   This code expires in 10 minutes.
   ```
   You can search the log directly and see the code on the next lines:
   ```bash
   ./scripts/dev.sh logs backend | grep -A 2 '\[EMAIL\] to='
   ```
   (`-A 2` shows 2 lines after each match, which includes the code line.)
3. Type that code into the app.
4. If the block is absent, restart the backend — a stale process may be running with old config:
   ```bash
   ./scripts/dev.sh restart
   ```

**If the fix does not work.** Run `./scripts/dev.sh logs backend | grep -A 2 '\[EMAIL\] to='` to search more specifically. If still nothing, share the full backend log with the engineer.

---

### Invalid OTP {#otp-invalid}

**What you see.**

```
{"detail": "Invalid OTP"}
```

or `Incorrect OTP` in the UI.

**Why it happens.** OTP codes are 6 digits, expire after 10 minutes, and lock out after 5 failed attempts (1-hour lockout).

**How to fix.**

1. Confirm you are reading the **most recent** OTP line in the backend log — each new request generates a new code and the old one immediately expires.
2. Type the code with no spaces: `482913`, not `482 913`.
3. If you entered the wrong code 5 times, wait 1 hour, then request a new code.
4. Request a fresh OTP and use it within 10 minutes.

**If the fix does not work.** Check the exact timestamp on the OTP log line — if it is more than 10 minutes old, the code has expired. Request a new one.

---

### User does not exist {#user-does-not-exist}

**What you see.**

```
{"detail": "User does not exist"}
```

or a similar 404 response when trying to log in.

**Why it happens.** The email address you typed was never seeded into the local *[database](./appendix-glossary.md#database)*.

**How to fix.**

1. Use one of the pre-seeded email addresses from chapter 5's demo-accounts table.
2. If you want a new account, request an OTP with any email — first-time login creates the account automatically.
3. If the seeded accounts are missing, re-run the seed script (see [#seed-script-crashes](#seed-script-crashes) if that fails).

**If the fix does not work.** Confirm the seed ran successfully by checking `./scripts/dev.sh logs backend` for seed-completion messages, then retry with an address from chapter 5.

---

## Map errors

### RefererNotAllowedMapError {#referrer-not-allowed}

**What you see.**

```
Google Maps JavaScript API error: RefererNotAllowedMapError
```

or the map area shows a grey/blank tile with an error overlay.

**Why it happens.** The browser *[API](./appendix-glossary.md#api)* key has HTTP referrer restrictions that do not include `http://localhost:3000`. The browser sends the page URL as the referrer, and Google rejects keys that do not list it.

**How to fix.**

1. Open the [GCP Credentials console](https://console.cloud.google.com/apis/credentials).
2. Click on your **browser** API key.
3. Under **Application restrictions** → **HTTP referrers (web sites)**, add:
   ```
   http://localhost:3000/*
   http://127.0.0.1:3000/*
   ```
4. Save. Changes propagate in a few minutes — reload the app.

**If the fix does not work.** Confirm you edited the **browser** key (not the server key). Also check that `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` in `frontend/.env.local` matches this key.

---

### REQUEST_DENIED {#request-denied}

**What you see.**

```
Google Maps JavaScript API error: InvalidKeyMapError
```

or API calls return `{ "status": "REQUEST_DENIED" }`.

**Why it happens.** Two possible causes: (1) the server-side key does not have the **Places API** and **Geocoding API** enabled, or (2) billing is not enabled on the GCP project (Google requires a billing account even for free-tier usage).

**How to fix.**

1. Go to [GCP APIs & Services → Library](https://console.cloud.google.com/apis/library).
2. Enable these APIs on your project:
   - Maps JavaScript API
   - Places API
   - Geocoding API
3. Go to [GCP Billing](https://console.cloud.google.com/billing) and confirm a billing account is linked to the project.
4. Wait 2–3 minutes, then reload.

**If the fix does not work.** Check whether the **server** key is also missing API enablement — the backend calls Maps server-side. See chapter 3 for the full key-setup walkthrough.

---

### "For development purposes only" watermark {#dev-watermark}

**What you see.** The map loads, but every tile has a grey "For development purposes only" watermark text overlaid.

**Why it happens.** This watermark appears when billing is not enabled on the GCP project, or when the browser API key's referrer restrictions block the current origin. It is Google's way of showing the key is not fully configured.

**How to fix.**

1. Enable billing on the GCP project — see [#request-denied](#request-denied), step 3.
2. Confirm the browser key allows `http://localhost:3000/*` — see [#referrer-not-allowed](#referrer-not-allowed).
3. Hard-refresh the browser (**Ctrl+Shift+R**) after making changes.

**If the fix does not work.** Wait 5 minutes for GCP changes to propagate and try again.

---

### OVER_QUERY_LIMIT {#over-query-limit}

**What you see.**

```
{"status": "OVER_QUERY_LIMIT", "error_message": "You have exceeded your daily request quota..."}
```

or the map stops loading and the browser console shows this status.

**Why it happens.** The demo or the seed script made too many calls to the Google Maps API within 24 hours, exhausting the free-tier quota.

**How to fix.**

1. Wait 24 hours — quotas reset at midnight Pacific Time.
2. In the meantime, use the app flows that do not require a map (browse products, view orders) to continue testing.
3. If you need more capacity immediately, raise the per-day quota in [GCP Quotas](https://console.cloud.google.com/iam-admin/quotas) for the Places API and Geocoding API.

**If the fix does not work.** If the quota was raised and errors persist, check that the billing account has a valid payment method attached — Google can cap usage even on paid tiers if the account has an overdue balance.

---

## Nothing here matches {#nothing-here-matches}

Send this to your engineer. Fill in every section — an incomplete report will slow things down.

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

---

← [Previous: Chapter 5 — Demo accounts and login flow](./05-demo-logins.md)  |  Next: [Chapter 7 — Day-to-day after install](./07-daily-use.md) →
