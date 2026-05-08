# KhanaBazaar — Teammate Onboarding Guide

*Teammate Guide > Start Here*

KhanaBazaar is an online grocery and food marketplace for Indian neighbourhoods. Shop owners list what they have on the platform, and customers nearby order through the website. Three kinds of people use it — admins who run the catalogue, sellers who run their own shop on the platform, and customers who shop.

## What you'll have at the end

- Full app running on your Windows laptop.
- Demo accounts to log in as admin, seller, and customer.
- Ability to stop and restart the app on later days.
- An optional way to view the app on your phone.
- A troubleshooting reference for when things break.

> **Time estimate:** Plan for 2–3 hours the first time, including downloads. About 5 minutes on subsequent days.

## Before you start

- [ ] Windows 10 or Windows 11.
- [ ] 8 GB RAM minimum (16 GB recommended).
- [ ] 20 GB free disk.
- [ ] Admin rights on the laptop.
- [ ] Virtualisation enabled in BIOS — see [Chapter 1](./01-install-tools.md#bios-virtualisation).
- [ ] Stable internet — about 3 GB of downloads expected.

## The chapters

| Chapter | You'll do |
|---|---|
| [1 — Install your tools](./01-install-tools.md) | Set up *[WSL](./appendix-glossary.md#wsl)*, Docker Desktop, *[Git](./appendix-glossary.md#git)*, Node, Python, and uv. |
| [2 — Get the code and configure secrets](./02-clone-and-env.md) | Clone the *[repository](./appendix-glossary.md#repository)*, copy *[environment variable](./appendix-glossary.md#environment-variable)* files, generate *[JWT](./appendix-glossary.md#jwt)* and *[OTP](./appendix-glossary.md#otp)* secrets. |
| [3 — Google Maps API keys (optional)](./03-google-maps-keys.md) | Provision two restricted Google Maps keys for address autocomplete and the map pin. |
| [4 — Run the app for the first time](./04-first-run.md) | Start the *[database](./appendix-glossary.md#database)*, build tables, load demo data, launch backend + frontend. |
| [5 — Demo accounts and login flow](./05-demo-logins.md) | Sign in as admin, seller, and customer; run a 5-minute demo script. |
| [6 — When things break](./06-troubleshooting.md) | Look up errors by symptom and fix them. |
| [7 — Day-to-day after install](./07-daily-use.md) | Start, stop, update, and reset the app. |
| [Appendix — Phone testing (optional)](./appendix-mobile-ngrok.md) | Open the dev app on your phone via ngrok. |
| [Appendix — Glossary](./appendix-glossary.md) | Plain-English definitions for every technical term. |

## If you get stuck

> Jump to [Chapter 6 — When things break](./06-troubleshooting.md). If nothing there matches, send your engineer the [message template at the bottom of Chapter 6](./06-troubleshooting.md#nothing-here-matches).

Next: [Chapter 1 — Install your tools](./01-install-tools.md) →
