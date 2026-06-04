<!--
Copyright (c) 2026 Rishi Mule. All Rights Reserved.
This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
-->
# Glossary

*Teammate Guide > Appendix: Glossary*

Plain-English definitions for every technical term used elsewhere in this guide. Each entry is short and avoids more jargon. If you bump into a word that is missing here, ping the engineer — they will add it.

---

## API

An API (Application Programming Interface) is a set of instructions that lets one piece of software talk to another piece of software. The KhanaBazaar backend exposes an API so the frontend, mobile apps, and external partners can request data (like "show me this store's products") without needing to know how the database works. Think of it like a restaurant menu — the menu tells you what dishes you can order without explaining the kitchen's recipes.

## Backend

The backend is the machinery behind the scenes that makes KhanaBazaar work: the server, the database, and all the business logic that rings up orders, checks inventory, and sends emails. When you use the app on your phone or browser, you are talking to the backend through an *[API](#api)*. The backend runs on servers, not on your device.

## Branch

A branch is a sandbox copy of the entire codebase where engineers can develop a feature or fix a bug without messing up the main code. Imagine a house renovation: the main branch is the finished house everyone depends on, and a feature branch is like setting up a temporary construction site in one room. When the work is done and tested, the branch is merged back into main.

## Cache

A cache is a small, fast memory bank that stores copies of data the app has already looked up, so the next request is answered instantly instead of querying the database again. The KhanaBazaar backend uses *[Redis](#redis)* as its cache — it's like keeping a memo pad of frequently asked questions on your desk instead of running to the filing cabinet every time.

## Celery

Celery is a tool that runs tasks in the background — things like sending emails, processing images, or cleaning up old data — without making the customer wait. KhanaBazaar uses Celery to dispatch order confirmation emails and OTP messages so the app stays snappy. Think of it like a to-do list: a customer makes a request, you write it down, and a worker (the Celery worker) completes it later.

## Cluster

A cluster is a group of servers working together as one unit, sharing the load and backing each other up so the app keeps running even if one server hiccups. The KhanaBazaar production deployment on Google Cloud is a cluster — multiple machines running the same app, all coordinated, so shoppers never see downtime.

## Commit

A commit is a snapshot of code changes, with a message describing what changed and why. Engineers make commits regularly as they write and test code; each commit is like a save-point in a video game. The entire history of commits is kept in *[Git](#git)*, so the team can see who changed what and when.

## Container

A container is a sealed lunchbox that holds an app together with the small slice of operating system the app needs to run. The same container behaves the same way on your laptop, on a teammate's laptop, and on the production server — there are no "works on my machine" surprises. KhanaBazaar uses containers in development (one for *[PostgreSQL](#postgresql)*, one for *[Redis](#redis)*); both are started by *[Docker](#docker)*.

## Database

A database is an organized warehouse of data: customer accounts, orders, inventory, product names, prices — everything the app needs to remember. KhanaBazaar uses *[PostgreSQL](#postgresql)*, which stores data in tables (like spreadsheets) and lets you query specific rows and columns with *[SQL](#sql)*. The database lives in a *[container](#container)* on your machine during development and on a server in production.

## Dependency

A dependency is a piece of code (usually someone else's library) that another piece of code needs to work. When you install dependencies, you are downloading software packages — think of it like buying ingredients for a recipe. KhanaBazaar's backend lists its dependencies in a file called `pyproject.toml`; the frontend lists them in `package.json`.

## Docker

Docker is a tool that packages up software into *[containers](#container)* so it runs the same way everywhere. You use Docker to spin up a *[PostgreSQL](#postgresql)* database and a *[Redis](#redis)* cache on your laptop without having to install them on your machine directly — they run inside containers instead. Containers are started with `docker compose up`.

## Environment variable

An environment variable is a configuration value that changes depending on where the code runs (your machine, a teammate's machine, production). Instead of hardcoding secrets and settings into the code, you store them in environment variables — things like the database password, email provider key, or backend URL. Environment variables live in `.env` files and are loaded when the app starts. Because `.env` files are never committed to Git, secrets stay safe and separate from the codebase.

## Frontend

The frontend is the part of KhanaBazaar that customers and sellers see and touch: the website, buttons, product pages, shopping cart, checkout flow. It runs in your web browser. The frontend is built in *[Node.js](#nodejs)* and *React* (using *[npm](#npm)*), and it talks to the *[backend](#backend)* through an *[API](#api)* to fetch data and submit orders.

## Git

Git is a version-control system that tracks every change to code and keeps a history of all commits. Think of it like an audit log that records who wrote what, when they wrote it, and why. Engineers use Git to collaborate without stepping on each other's work: one person works on a *[branch](#branch)* while another works on a different branch, then changes are merged together when they are ready.

## Hot reload

Hot reload is a developer feature that automatically restarts or refreshes the app when code changes, so engineers do not have to stop and restart the server manually. When you are working on the frontend in development mode, changing a button label updates the page in your browser instantly. This speeds up the development loop dramatically.

## JSON

JSON (JavaScript Object Notation) is a simple text format for storing and sending structured data — like a menu written in a universal language that every system understands. An API response is usually JSON: it might contain a customer's name, address, order history, all formatted in a consistent way. It looks a bit like Python *dictionaries* or spreadsheets, but more compact.

## JWT

A JWT (JSON Web Token) is a tamper-proof string that proves who you are and what you are allowed to do. When a customer logs in to KhanaBazaar via OTP, they receive a JWT that the app passes along on every request to the *[backend](#backend)* — like a digital ID badge. The backend decodes the JWT to verify you are really you and to know your role (customer, seller, or admin).

## Localhost

Localhost (or `127.0.0.1`) is the address of your own machine, used for testing during development. When you start the KhanaBazaar backend, it runs at `http://localhost:8000`; the frontend runs at `http://localhost:3000`. You are the only person who can reach localhost on your machine — it is not visible on the internet.

## Migration

A migration is a set of instructions that modifies the structure of the database — adding a new column to a table, creating a new table, renaming a field, etc. Every migration is a file that engineers commit to Git, so the whole team can track schema changes. KhanaBazaar uses *Alembic*: when you pull new code, you run `alembic upgrade head` to apply any pending migrations to your *[database](#database)*.

## Node.js

Node.js is a runtime environment that runs *JavaScript* code outside the browser — on servers or your local machine. The KhanaBazaar frontend uses Node.js tooling (like *[npm](#npm)*) to bundle, develop, and build the web app. You do not write Node.js code directly; you write *React* components in TypeScript, and Node.js runs the tools that translate and optimize them.

## npm

npm (Node Package Manager) is the package manager for *[Node.js](#nodejs)* and *JavaScript* — it downloads and installs code libraries. Think of it as the store where you buy ingredients for a recipe. The KhanaBazaar frontend's dependencies (like React, TypeScript, linters) are listed in `package.json`, and you install them all by running `npm install`.

## OTP

An OTP (One-Time Password) is a short code (like a 6-digit number) sent to your phone or email that you enter to prove you are the owner of that account, no password needed. KhanaBazaar customers and sellers log in via OTP: you request one, receive a code via SMS or email, and type it in to confirm your identity. Each code expires after a few minutes and works only once.

## Port

A port is a virtual doorway on your machine that a running app listens on. The KhanaBazaar backend listens on port 8000 (`http://localhost:8000`), and the frontend listens on port 3000 (`http://localhost:3000`). If two apps try to use the same port, there is a conflict — one of them has to move to a different port.

## PostgreSQL

PostgreSQL is the database system that stores all of KhanaBazaar's data: customers, orders, products, inventory, seller profiles. It is a *[database](#database)* engine that runs inside a *[container](#container)* and understands *[SQL](#sql)* queries. PostgreSQL includes PostGIS, an extension that understands geographic coordinates, so KhanaBazaar can calculate which stores are near a customer's address.

## Python

Python is the programming language used to write the KhanaBazaar *[backend](#backend)*. It is readable, close to English, and great for web servers, scripts, and data work. The backend is written in Python using a web framework called *FastAPI*.

## Redis

Redis is a fast in-memory data store used for *[caching](#cache)* and as a task broker for *[Celery](#celery)*. Think of it as a chalkboard in the cafe: information is written and erased quickly, but it is not permanent. KhanaBazaar uses Redis to cache frequently looked-up data (like product lists) and to queue background tasks (like sending emails).

## Repository

A repository (or "repo") is a folder that *[Git](#git)* tracks — it holds all the code, documentation, and history for a project. The KhanaBazaar repository lives on GitHub, and every engineer clones it to their machine so they can read, modify, and commit code. The repo contains the backend, frontend, tests, documentation, and infrastructure-as-code.

## Seed data

Seed data is a starter set of data (customers, orders, products, prices) that you load into the *[database](#database)* for testing or demonstration. Instead of typing in a thousand dummy products by hand, you run a seed script that populates the database instantly. This lets engineers and product teammates test the app against realistic data without waiting.

## Shell / Terminal

The shell (or terminal) is a text-based interface where you type commands to control your machine instead of clicking buttons. You use the shell to start servers, run tests, commit code, navigate folders — all by typing. On Windows, you might use *[WSL](#wsl)* to get a Unix-style shell where you can run Linux commands.

## SQL

SQL (Structured Query Language) is the language you use to ask a *[database](#database)* for information: "show me all orders placed today," "list products under $5," etc. Engineers and database analysts write SQL queries to fetch, insert, update, or delete data. The KhanaBazaar backend uses an ORM called *SQLModel* that translates Python code into SQL, so engineers do not have to write raw SQL as often.

## SSL / TLS

SSL and TLS are protocols that encrypt data traveling between your browser and a server so hackers cannot eavesdrop. When you visit `https://khana-bazaar.com` (note the `https` and the padlock icon), your connection is protected by TLS. In development on localhost, you skip TLS because there is no internet; in production, TLS is mandatory.

## Swagger

Swagger (now called OpenAPI) is a standard format for documenting an *[API](#api)*. The KhanaBazaar backend automatically generates interactive Swagger documentation at `http://localhost:8000/docs` where you can see every endpoint, what inputs it needs, what it returns, and you can test endpoints directly in your browser. It is like a living, clickable manual for the API.

## uv

uv is a fast package manager for Python — it downloads and installs Python libraries. Think of it as the Python equivalent of *[npm](#npm)* for *[Node.js](#nodejs)*. The KhanaBazaar backend uses uv to install dependencies listed in `pyproject.toml`. Instead of using the older `pip` command, engineers run `uv sync` to set up the environment.

## WSL

WSL (Windows Subsystem for Linux) is a compatibility layer on Windows 10 and 11 that lets you run Linux commands and tools directly on your Windows machine without needing a virtual machine. KhanaBazaar teammates on Windows use WSL to run bash scripts, Python, Docker, and Git — all the same tools that Mac and Linux engineers use. It bridges the gap between Windows and the Unix-style development environment.

---

← [Previous: Appendix — Mobile testing](./appendix-mobile-ngrok.md)  |  [Back to start](./README.md)
