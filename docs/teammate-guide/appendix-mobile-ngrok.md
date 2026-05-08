# Appendix — Phone testing (optional)

*Teammate Guide > Appendix: Phone testing (optional)*

> Estimated time: about 15 minutes the first time. About 30 seconds on each later session.

> **Skip this if you only need desktop demos.** This appendix shows you how to open the dev app on your phone over mobile data — useful for showing a real shopper experience to stakeholders.

---

## What it does

ngrok is a service that gives your laptop a temporary public URL. When you start the dev app with `--tunnel`, ngrok creates a tunnel to your local frontend (`localhost:3000`) and assigns it a web address like `https://abc-123.ngrok-free.app`. You then type this URL into your phone's browser and see the same KhanaBazaar app running on your laptop, as if it were a live website.

The frontend is the only piece exposed. The *[backend](./appendix-glossary.md#backend)* stays loopback-only and unreachable from the phone. The *[frontend](./appendix-glossary.md#frontend)* uses relative *[API](./appendix-glossary.md#api)* paths for all requests, so Next.js proxies each call server-side to `http://localhost:8000` (the backend on your laptop). From the phone's perspective, API calls happen through the same origin as the website — there is no CORS trouble, and the backend never needs a public IP.

---

## One-time setup {#one-time-setup}

1. **Click in: web browser** — go to `https://ngrok.com` and click **Sign up** (free tier is enough).

2. After signing in, navigate to your dashboard, find **Your Authtoken** under the account menu, and click to copy it.

3. **Run in: WSL2 Ubuntu terminal** — install ngrok from the official apt repository:

   ```
   curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
   echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
   sudo apt update
   sudo apt install -y ngrok
   ```

   **What you should see:** a series of `Get:` lines ending with `done` and `Reading package lists...`.

4. Authenticate ngrok with your token (one-time):

   **Run in: WSL2 Ubuntu terminal**

   ```
   ngrok config add-authtoken <paste-your-token>
   ```

   Replace `<paste-your-token>` with the value you copied from the dashboard. Quotes are not required.

   **What you should see:** `Authtoken saved to configuration file`.

---

## Each session {#each-session}

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh start --tunnel
```

**What you should see:** the usual `start` output — listing backend, celery, frontend, and log_viewer starting — plus a new line near the end:

```
Tunnel ready: https://abc-123.ngrok-free.app  ->  :3000
```

Copy that URL (the one ending in `ngrok-free.app`). This is your temporary public address.

If you forget the URL later, print it again:

**Run in: WSL2 Ubuntu terminal**

```
./scripts/dev.sh tunnel-url
```

**What you should see:** the current tunnel URL.

---

## Open it on the phone {#open-on-phone}

1. On your phone, open a web browser — Chrome on Android or Safari on iOS.

2. Tap the address bar and type (or paste) the ngrok URL from the previous step.

3. Hit Enter. The first visit shows a one-time ngrok interstitial warning page with a message like "You are visiting a preview link." Tap **Visit Site** to proceed.

   [Screenshot: ngrok interstitial warning page on a phone, with the "Visit Site" button highlighted]

4. The KhanaBazaar storefront loads. You can now browse stores, add items to the cart, and test the app as if you were a customer on a phone.

---

## Install as a Progressive Web App {#install-pwa}

Once the app loads, you can install it as an icon on your phone's home screen — no App Store needed.

- **Android:** Tap the three-dot menu in Chrome, select **Add to Home Screen**, and tap **Add**. The app installs as an icon and opens fullscreen.
- **iOS:** Tap the Share button in Safari, scroll down, and tap **Add to Home Screen**. Choose a name and tap **Add**.

This is a *[PWA](./appendix-glossary.md#frontend)* — a website that behaves like an installed app. It still runs on your laptop under the hood; the phone is a display. There is no App Store, no waiting for builds, and updates happen instantly when you change the frontend code.

---

## Common gotchas {#mobile-gotchas}

- **The ngrok URL changes every restart** (on the free plan). When you run `./scripts/dev.sh start --tunnel` again tomorrow, you get a new URL. Re-copy it from `./scripts/dev.sh tunnel-url`. The frontend uses relative API paths, so the app still works — only the URL you type into the phone changes.

- **The first request through the tunnel sometimes 502s** while Next.js compiles the entry route. Give it about 5 seconds and reload. The second request always works.

- **`NEXT_PUBLIC_API_URL` in `frontend/.env.local` must remain empty.** If you set it to `http://localhost:8000`, the phone will try to reach your laptop's localhost (which it cannot) and every *[API](./appendix-glossary.md#api)* call fails.

- **Tunnel will not start?** Check the ngrok logs:

  **Run in: WSL2 Ubuntu terminal**

  ```
  ./scripts/dev.sh logs ngrok
  ```

  Common reasons: authtoken not configured, free-tier quota exhausted for the day (reset at 4 PM UTC), or an old ngrok process still holding the port. If stuck, ask an engineer.

---

← [Previous: Chapter 7 — Day-to-day after install](./07-daily-use.md)  |  Next: [Appendix — Glossary](./appendix-glossary.md) →
