# Chapter 2 — Get the code and configure secrets

*Teammate Guide > Chapter 2: Get the code and configure secrets*

> **Estimated time: about 15 minutes.**

Three things this chapter does — download the project files, copy two example settings files into real settings files, and fill in two secret values.

---

## 1. Make a place for the project

**Run in: WSL2 Ubuntu terminal**
```
mkdir -p ~/projects
```
**What you should see:** No output. Success is silence — `mkdir -p` creates the folder if it does not exist and stays quiet if it already does.

**Run in: WSL2 Ubuntu terminal**
```
cd ~/projects
```
**What you should see:** No output. The command moves you into the folder; your prompt changes to show the new path.

`~` is your home folder (the one Ubuntu created for your username when you set up WSL2). Every path that starts with `~` is shorthand for that location.

---

## 2. Download the code

**Run in: WSL2 Ubuntu terminal**
```
git clone https://github.com/rishimule/KhanaBazaar.git
```
**What you should see:**
```
Cloning into 'KhanaBazaar'...
remote: Enumerating objects: ...
remote: Counting objects: 100% (...)
remote: Compressing objects: 100% (...)
Receiving objects: 100% (...), done.
Resolving deltas: 100% (...), done.
```
Then a blank prompt. This can take **1–2 minutes** depending on your connection speed.

*[git](./appendix-glossary.md#git)* clone downloads the folder along with its full edit history — every commit ever made to the project — so you can switch between versions, create branches, and push changes back later.

**If it fails.** See [./06-troubleshooting.md#network-timeout](./06-troubleshooting.md#network-timeout).

**Run in: WSL2 Ubuntu terminal**
```
cd KhanaBazaar
```
**What you should see:** No output. Your prompt now shows `KhanaBazaar` as the current folder.

**Verify the download.**

**Run in: WSL2 Ubuntu terminal**
```
ls
```
**What you should see:** At minimum these names:
```
backend  CLAUDE.md  docker-compose.yml  docs  frontend  README.md  scripts  TODO.md
```
A few other files may also appear. The key ones are `backend` and `frontend`.

---

## 3. Copy the example env files

**Run in: WSL2 Ubuntu terminal**
```
cp backend/app/.env.example backend/app/.env
```
**What you should see:** No output.

**Run in: WSL2 Ubuntu terminal**
```
cp frontend/.env.example frontend/.env.local
```
**What you should see:** No output.

An *[environment variable](./appendix-glossary.md#environment-variable)* is a named value that a running program reads from its surroundings rather than from the code itself. That keeps sensitive values — passwords, API keys, secret tokens — out of the source code.

The `.env.example` files are safe templates checked into *[Git](./appendix-glossary.md#git)* with placeholder values. The real `.env` and `.env.local` files you created in the step above are listed in `.gitignore`, so they will never be uploaded to GitHub. Your secrets stay on your laptop.

---

## 4. Generate the two secrets

Two values in `backend/app/.env` contain obvious placeholder text. You must replace them with real random strings before the app will start.

### JWT_SECRET

This value signs login tokens. The *[backend](./appendix-glossary.md#backend)* stamps every token with this string; if anyone learns it they can forge a login as any user. Keep it private.

*[JWT](./appendix-glossary.md#jwt)* stands for JSON Web Token — the format used for login sessions in KhanaBazaar.

**Run in: WSL2 Ubuntu terminal**
```
python3 -c "import secrets; print(secrets.token_hex(32))"
```
**What you should see:** A single 64-character hex string, for example:
```
a3f1c8e04b2d7f9a5e3c1b0d6f2a4e8c1d5f7b9a2c4e6f8a0b2d4e6f8a0b2d4
```
Copy the full string. You will paste it in section 5.

### OTP_PEPPER

This value adds extra randomness mixed into login codes so two laptops with the same email address do not generate identical *[OTP](./appendix-glossary.md#otp)* codes.

**Run in: WSL2 Ubuntu terminal**
```
python3 -c "import secrets; print(secrets.token_hex(16))"
```
**What you should see:** A 32-character hex string, for example:
```
b4c2d1e0f3a5b7c9d1e3f5a7b9c1d3e5
```
Copy the full string.

---

## 5. Edit the backend env file

**Run in: WSL2 Ubuntu terminal**
```
nano backend/app/.env
```

The file opens in the nano text editor. Use these controls:

> Arrow keys to move the cursor.
> Type to edit.
> Ctrl+O to save (then press Enter to confirm the filename).
> Ctrl+X to quit.
> The `^` symbol on the bottom bar means Ctrl.

### Replace the JWT_SECRET line

Find the line that reads:

```
JWT_SECRET="change-me-use-secrets-token-hex-32"
```

**Delete the placeholder text** `change-me-use-secrets-token-hex-32` first, then paste your 64-character hex string in its place. Do not leave the placeholder text sitting next to your real value.

After editing, the line should look like this (with your real hex string):

```
JWT_SECRET="<your-64-char-hex>"
```

### Replace the OTP_PEPPER line

Find the line that reads:

```
OTP_PEPPER="change-me-use-secrets-token-hex-16"
```

Delete the placeholder text, then paste your 32-character hex string:

```
OTP_PEPPER="<your-32-char-hex>"
```

### Leave EMAIL_PROVIDER as-is

The line `EMAIL_PROVIDER="console"` is correct for local development. In this mode, the app prints login codes to a log file instead of sending real emails — you will see how to read that log in chapter 5.

### Save and exit

Press `Ctrl+O`, then press `Enter` to confirm the filename. Then press `Ctrl+X` to quit.

---

## 6. Maps keys (optional)

> **Skip this section if you only want the core e-commerce demo.** The app falls back to manual address entry without maps. Come back when you want maps. Forward link: [Chapter 3 — Google Maps API keys](./03-google-maps-keys.md).

If you are skipping maps for now, leave these lines in `backend/app/.env` exactly as they are:

```
GOOGLE_MAPS_SERVER_API_KEY=""
GOOGLE_MAPS_BROWSER_API_KEY=""
```

And leave this line in `frontend/.env.local` exactly as it is:

```
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""
```

Empty strings are fine — the app detects them and switches to manual address entry mode.

*The `GOOGLE_MAPS_BROWSER_API_KEY` line in `backend/app/.env` is vestigial and not read at runtime. Only the frontend `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY` is used. Keep the backend line empty.*

---

## 7. Sanity check

**Run in: WSL2 Ubuntu terminal**
```
cat backend/app/.env | grep -E '^(JWT_SECRET|OTP_PEPPER|EMAIL_PROVIDER)='
```
**What you should see:**
```
JWT_SECRET="<your long hex string>"
OTP_PEPPER="<your long hex string>"
EMAIL_PROVIDER="console"
```
The hex strings must **not** contain `change-me`. If they do, open the file with `nano backend/app/.env` and replace the placeholder text again.

**Run in: WSL2 Ubuntu terminal**
```
cat frontend/.env.local
```
**What you should see:**
```
NEXT_PUBLIC_API_URL=""
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""
```
These stay empty until chapter 3 fills in the maps key (if you choose to do that).

---

← [Previous: Chapter 1 — Install your tools](./01-install-tools.md)  |  Next: [Chapter 3 — Google Maps API keys (optional)](./03-google-maps-keys.md) →
