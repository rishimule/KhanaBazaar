# Chapter 1 — Install your tools

*Teammate Guide > Chapter 1: Install your tools*

> **Estimated time: 60–90 minutes. Most of it is downloads — go grab tea between sections.**

In this chapter you will install eight things in order: first a BIOS check to make sure your CPU is ready, then *[WSL](./appendix-glossary.md#wsl)* (a Linux layer inside Windows), then Docker Desktop (which runs the *[database](./appendix-glossary.md#database)* and *[cache](./appendix-glossary.md#cache)*), then Windows Terminal (a nicer command window), then *[Git](./appendix-glossary.md#git)* (for downloading and tracking code), then Node.js (which runs the *[frontend](./appendix-glossary.md#frontend)*), then *[Python](./appendix-glossary.md#python)* (which runs the *[backend](./appendix-glossary.md#backend)*), and finally *[uv](./appendix-glossary.md#uv)* (which manages Python packages). Every tool has a verify command at the end so you know for certain it worked before moving on.

---

### Tool: BIOS virtualisation check {#bios-virtualisation}

**What it is.** Modern Windows laptops can run a tiny Linux side-by-side with Windows. That uses a CPU feature called *virtualisation*. Many laptops ship with the feature switched off in firmware (BIOS) — you flip a switch before any next tool will work.

**Install steps.**

1. Open Task Manager: press `Ctrl + Shift + Esc`.
2. Click the **Performance** tab, then click **CPU** in the left panel.
3. Look for the line that reads **Virtualization:**.
4. If it says **Enabled**, skip the rest of this section and move on to WSL2.
5. If it says **Disabled**, reboot your laptop. As the screen goes dark and the manufacturer logo appears, press the BIOS key for your laptop brand:
   - **Lenovo:** `F1` or `Fn + F2`
   - **HP:** `Esc`, then `F10`
   - **Dell:** `F2`
   - **Asus:** `F2` or `Del`
   - **MSI:** `Del`
6. Inside the BIOS menu, look for a setting called one of these names: `Intel Virtualization Technology`, `VT-x`, `SVM Mode`, or `AMD-V`. Enable it (the setting is usually under an **Advanced** or **CPU** tab).
7. Press `F10` to Save & Exit. Your laptop reboots into Windows.

[Screenshot: Task Manager Performance > CPU panel showing "Virtualization: Enabled"]

**Verify it worked.**

Open Task Manager again and confirm the **Virtualization** line now reads **Enabled**.

**If it fails.** If you cannot find the virtualisation setting in your BIOS, or if the option is greyed out, your IT department may have locked the firmware. See [./06-troubleshooting.md#virtualisation-disabled](./06-troubleshooting.md#virtualisation-disabled).

---

### Tool: WSL2 with Ubuntu {#wsl2-ubuntu}

**What it is.** *[WSL](./appendix-glossary.md#wsl)* (Windows Subsystem for Linux) lets a real Ubuntu Linux run inside Windows. KhanaBazaar's tooling assumes a Linux *[shell](./appendix-glossary.md#shell--terminal)*, so this is the foundation everything else sits on.

**Install steps.**

1. Open PowerShell as Administrator: click **Start**, type `PowerShell`, right-click **Windows PowerShell**, and choose **Run as administrator**. Click **Yes** on the UAC prompt.

2. Run this command:

**Run in: PowerShell (as Administrator)**
```
wsl --install
```
**What you should see:**
```
Installing: Windows Subsystem for Linux
Windows Subsystem for Linux has been installed.
Installing: Ubuntu
Ubuntu has been installed.
The requested operation is successful. Changes will not be effective until the system is rebooted.
```

3. This download can take 5–10 minutes depending on your internet speed.

4. **Restart Windows** when prompted. Save any open work first.

5. After the reboot, an Ubuntu window opens automatically and finishes setup. When asked:
   - **Enter new UNIX username:** type a short lowercase name with no spaces (for example: `rishi`).
   - **New password:** type a password. **Heads-up:** the screen shows nothing while you type — no dots, no asterisks. That is normal Linux behaviour. Type carefully, press Enter, then type it again to confirm.

[Screenshot: Ubuntu terminal window showing the "Enter new UNIX username:" prompt]

**Verify it worked.**

**Run in: PowerShell**
```
wsl --status
```
**What you should see:**
```
Default Distribution: Ubuntu
Default Version: 2
```

**Run in: WSL2 Ubuntu terminal**
```
lsb_release -a
```
**What you should see:**
```
Description:    Ubuntu 24.04.x LTS
```
Ubuntu 22.04 is also fine if that is what installed.

**If it fails.** If `wsl --install` errors with "WSL2 requires an update to its kernel component" or the Ubuntu window never opens, see [./06-troubleshooting.md#wsl-install-fails](./06-troubleshooting.md#wsl-install-fails).

---

### Tool: Docker Desktop {#docker-desktop}

**What it is.** *[Docker](./appendix-glossary.md#docker)* is a sealed lunchbox for software. KhanaBazaar uses two lunchboxes in development — one for *[PostgreSQL](./appendix-glossary.md#postgresql)* (the database), one for *[Redis](./appendix-glossary.md#redis)* (the cache). Docker Desktop is the Windows app that runs them.

**Install steps.**

1. **Click in: web browser** — open `https://www.docker.com/products/docker-desktop/`

2. Click **Download for Windows — AMD64**. The file is about 600 MB; the download takes several minutes on a slow connection.

3. Run the installer (`Docker Desktop Installer.exe`).

4. On the configuration screen, make sure the checkbox **"Use WSL 2 instead of Hyper-V (recommended)"** is ticked. Leave it ticked — do not uncheck it.

5. Click **OK** and let the installer finish. This takes 3–5 minutes.

6. Click **Close and restart** when prompted. Save any open work first.

7. After the reboot, open **Docker Desktop** from the Start menu. Skip any sign-in prompt by clicking **Continue without signing in**.

8. Click the **gear icon** (Settings) in the top-right corner. Go to **Resources** → **WSL Integration**. Toggle on the **Ubuntu** entry. Click **Apply & Restart**.

[Screenshot: Docker Desktop installer wizard with the "Use WSL 2 instead of Hyper-V" checkbox highlighted]

[Screenshot: Docker Desktop Settings > Resources > WSL Integration showing Ubuntu toggle switched on]

**Verify it worked.**

**Run in: WSL2 Ubuntu terminal**
```
docker --version
```
**What you should see:**
```
Docker version 27.x.x, build <hash>
```

**Run in: WSL2 Ubuntu terminal**
```
docker compose version
```
**What you should see:**
```
Docker Compose version v2.x.x
```

**Run in: WSL2 Ubuntu terminal**
```
docker run --rm hello-world
```
**What you should see:** A paragraph beginning with "Hello from Docker!" that confirms the installation is working. This command downloads a tiny test image (about 10 seconds on first run) and then removes it automatically.

**If it fails.** If Docker Desktop fails to start or shows "Docker Engine stopped", your antivirus or a missing restart is usually the cause. See [./06-troubleshooting.md#docker-wont-start](./06-troubleshooting.md#docker-wont-start).

---

### Tool: Windows Terminal {#windows-terminal}

**What it is.** Windows Terminal is a nicer command window than the default console. It gives you tabs, reliable copy-paste with `Ctrl + C` / `Ctrl + V`, and a cleaner look. It is recommended but not required — you can use the plain Ubuntu app instead.

**Install steps.**

1. Open the Microsoft Store: click **Start**, type `Microsoft Store`, and press Enter.
2. Search for **Windows Terminal**.
3. Click **Get** (or **Install**). The download is small and takes under a minute.
4. Once installed, open Windows Terminal. Click the small **drop-down arrow** next to the `+` tab button.
5. Click **Settings**. Under **Startup**, find **Default profile** and change it to **Ubuntu**. Click **Save**.

From now on, every time you open Windows Terminal it will open an Ubuntu shell tab automatically.

[Screenshot: Windows Terminal Settings showing "Ubuntu" selected as the Default profile]

---

### Tool: Git {#git}

**What it is.** *[Git](./appendix-glossary.md#git)* is the version-control tool that downloads the project and tracks changes. It comes preinstalled on most Ubuntu builds, but the step below ensures you have it.

**Install steps.**

**Run in: WSL2 Ubuntu terminal**
```
sudo apt update
```
**What you should see:** A list of package sources being refreshed, ending in `Reading package lists... Done`. This step checks for the latest version of every available package. `sudo` runs the command as administrator; `apt` is Ubuntu's built-in app store; `update` refreshes its catalogue. You will be prompted for your Ubuntu password (the one you set during WSL2 setup). No characters appear while you type — press Enter when done.

**Run in: WSL2 Ubuntu terminal**
```
sudo apt install -y git
```
**What you should see:** Lines showing packages being downloaded and installed, ending in `Processing triggers for man-db`. The `-y` flag answers "yes" automatically to any confirmation prompts.

**Verify it worked.**

**Run in: WSL2 Ubuntu terminal**
```
git --version
```
**What you should see:**
```
git version 2.x.x
```

**If it fails.** If `sudo apt update` hangs for more than two minutes without output, your network may be blocking Ubuntu's package servers. See [./06-troubleshooting.md#apt-update-hangs](./06-troubleshooting.md#apt-update-hangs).

---

### Tool: Node.js 20 via nvm {#nodejs}

**What it is.** *[Node.js](./appendix-glossary.md#nodejs)* runs the *[frontend](./appendix-glossary.md#frontend)*. `nvm` (Node Version Manager) installs and switches Node versions without administrator rights. We use nvm instead of `apt install nodejs` because Ubuntu's built-in version is older than what KhanaBazaar needs.

**Install steps.**

**Run in: WSL2 Ubuntu terminal**
```
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```
**What you should see:** Several lines of output ending with:
```
=> Close and reopen your terminal to start using nvm or run the following to use it now:
```

After the script finishes, **close the Ubuntu window completely and reopen it**. nvm adds itself to your shell profile, and a fresh session picks it up.

**Run in: WSL2 Ubuntu terminal**
```
nvm install 20
```
**What you should see:** `Downloading and installing node v20.x.x...` followed by `Now using node v20.x.x`. This takes about 30–60 seconds.

**Run in: WSL2 Ubuntu terminal**
```
nvm use 20
```
**What you should see:**
```
Now using node v20.x.x (npm vx.x.x)
```

**Run in: WSL2 Ubuntu terminal**
```
nvm alias default 20
```
**What you should see:**
```
default -> 20 (-> v20.x.x)
```
This makes Node 20 the version that opens automatically in every new terminal session.

**Verify it worked.**

**Run in: WSL2 Ubuntu terminal**
```
node --version
```
**What you should see:**
```
v20.x.x
```

**Run in: WSL2 Ubuntu terminal**
```
npm --version
```
**What you should see:**
```
10.x.x
```

**If it fails.** If you get `nvm: command not found` after reopening the terminal, the install script did not write to your shell profile correctly. See [./06-troubleshooting.md#nvm-not-found](./06-troubleshooting.md#nvm-not-found).

---

### Tool: Python 3.12 {#python}

**What it is.** *[Python](./appendix-glossary.md#python)* runs the *[backend](./appendix-glossary.md#backend)*. Ubuntu 24.04 ships with Python 3.12 already; older Ubuntu versions need a manual install. Check first before doing anything.

**Install steps.**

**Run in: WSL2 Ubuntu terminal** — check your version first:
```
python3 --version
```

If the output says `Python 3.12.x`, Python is ready. Skip the rest of this section and move on to uv.

If you see an older version (3.10, 3.11, or no output), install Python 3.12 from the Deadsnakes PPA — a trusted third-party source that provides up-to-date Python builds for Ubuntu:

**Run in: WSL2 Ubuntu terminal**
```
sudo add-apt-repository ppa:deadsnakes/ppa -y
```
**What you should see:** Output ending in `Hit:1 ... Done` as apt refreshes.

**Run in: WSL2 Ubuntu terminal**
```
sudo apt update
```

**Run in: WSL2 Ubuntu terminal**
```
sudo apt install -y python3.12 python3.12-venv
```
**What you should see:** Download and install lines, ending in `Processing triggers for man-db`. This takes 1–3 minutes.

**Verify it worked.**

**Run in: WSL2 Ubuntu terminal**
```
python3 --version
```
**What you should see:**
```
Python 3.12.x
```

**If it fails.** If `add-apt-repository` returns `No module named 'apt_pkg'` or similar errors, the Deadsnakes PPA may not be available for your Ubuntu version. See [./06-troubleshooting.md#python-version-mismatch](./06-troubleshooting.md#python-version-mismatch).

---

### Tool: uv {#uv}

**What it is.** *[uv](./appendix-glossary.md#uv)* is a fast Python package manager. KhanaBazaar's backend *[dependencies](./appendix-glossary.md#dependency)* are managed with uv, not the older `pip` tool. It is roughly 10–100× faster than pip at installing packages.

**Install steps.**

**Run in: WSL2 Ubuntu terminal**
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
**What you should see:** Output ending with:
```
 uv  0.x.x installed successfully
To add $HOME/.local/bin to your PATH, either restart your shell or run:
    source $HOME/.local/bin/env (sh, bash, zsh)
```

**Close and reopen the Ubuntu window** after install. uv adds itself to your `PATH` (the list of places your shell looks for programs), and a fresh session picks it up.

**Verify it worked.**

**Run in: WSL2 Ubuntu terminal**
```
uv --version
```
**What you should see:**
```
uv 0.4.x
```
Any version 0.4 or newer is fine.

**If it fails.** If you get `uv: command not found` after reopening the terminal, the installer may not have updated your PATH. See [./06-troubleshooting.md#uv-not-found](./06-troubleshooting.md#uv-not-found).

---

## All-in-one check

Run this single command to confirm every tool is installed and prints a real version number.

**Run in: WSL2 Ubuntu terminal**
```
docker --version && docker compose version && git --version && node --version && npm --version && python3 --version && uv --version
```
**What you should see:** Seven lines of version output, one per tool. Nothing should print `command not found`. If one line fails, scroll back up to that tool's section and re-run its verify step.

---

## Common install pitfalls

- **Slow or unreliable networks.** Symptoms: `Could not resolve archive.ubuntu.com`, `ETIMEDOUT`, or a command that hangs indefinitely. Retry the command. If the problem persists, switch to a mobile hotspot or see [./06-troubleshooting.md#proxy-blocking-installs](./06-troubleshooting.md#proxy-blocking-installs).

- **Antivirus blocks Docker (Quick Heal, K7, Norton, McAfee).** Symptom: the Docker installer rolls back partway through, or Docker Desktop shows "service failed to start" after a reboot. Temporarily disable real-time protection during the Docker install, then re-enable it after. See [./06-troubleshooting.md#antivirus-blocks-docker](./06-troubleshooting.md#antivirus-blocks-docker).

- **Corporate or college proxy.** Symptom: `curl` and `apt` both return `Could not resolve host`. Your network requires you to declare a proxy address before any outbound requests work. Add `HTTP_PROXY` and `HTTPS_PROXY` to `~/.bashrc`. See [./06-troubleshooting.md#proxy-blocking-installs](./06-troubleshooting.md#proxy-blocking-installs).

- **Two restart prompts, one per tool.** WSL2 asks for a restart after `wsl --install`. Docker Desktop asks for another restart after its installer. Both are expected. Save your work before each one.

---

← [Previous: Start Here](./README.md)  |  Next: [Chapter 2 — Get the code and configure secrets](./02-clone-and-env.md) →
