# Khana Bazaar

Khana Bazaar is a centralized, multi-vendor e-commerce platform designed specifically for the Indian market, operating on a model similar to Instacart. It bridges the gap between local sellers and consumers by providing a seamless, hyperlocal shopping experience.

## Overview
To ensure quality and consistency, the core product catalog is managed centrally by an internal administrative team, while independent sellers manage their localized inventory and fulfillment. The platform is optimized for mobile-first users and native UPI integrations to ensure frictionless transactions.

## Core Operational Flow
The platform operates through a tripartite ecosystem:
- **Product Administrators (Internal)**: Maintain the master catalog of all allowable products on the platform, ensuring high-quality images, accurate descriptions, and standardized categorizations.
- **Sellers/Vendors**: Access a dedicated portal to browse the master catalog, select the items they carry, update their local stock levels, and receive order notifications for fulfillment.
- **Customers**: Access the storefront via web or mobile, select their preferred local store, build a cart from that store's available inventory, and seamlessly check out using UPI.

## Local Development Setup

To run the Khana Bazaar application locally, follow these steps to set up the environment, run the backend, seed the database, and start the frontend.

### 1. Start Services
First, ensure you have Docker installed and start the required database services (PostgreSQL and Redis):
```bash
docker compose up -d
```

### 2. Backend Setup & Database Seeding
Navigate to the backend directory, run migrations (if any), seed the database with dummy data, and start the FastAPI server:

```bash
cd backend/app

# Run the seed script to create Firebase users and populate PostgreSQL
PYTHONPATH=src uv run python scripts/seed_database.py

# Start the uvicorn development server on port 8000
PYTHONPATH=src uv run uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend Setup
In a new terminal window, navigate to the frontend directory, install dependencies, and start the Next.js development server:

```bash
cd frontend

# Install Node dependencies
npm install

# Start the Next.js app on port 3000
npm run dev
```
You can now access the application at `http://localhost:3000`.

## Test Accounts

The `seed_database.py` script automatically creates the following Firebase Auth accounts with their corresponding roles in the backend. You can use these to test the various dashboards:

| Role | Email | Password |
| :--- | :--- | :--- |
| **Admin** | `admin@khanabazaar.dev` | `Test@12345` |
| **Seller** (Sharma Store) | `seller@khanabazaar.dev` | `Test@12345` |
| **Seller** (Krishna Store)| `seller2@khanabazaar.dev` | `Test@12345` |
| **Seller** (Balaji Store) | `seller3@khanabazaar.dev` | `Test@12345` |
| **Customer** | `customer@khanabazaar.dev` | `Test@12345` |

*(Note: The frontend login page also features quick-login buttons for these test accounts for rapid development.)*

## Documentation
- [Architecture Details](docs/architecture.md)
- [Local Development Setup](docs/local_setup.md)
- [User & Data Flows](docs/flows.md)
- [Task Tracker (TODO)](TODO.md)

