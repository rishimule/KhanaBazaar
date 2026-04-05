# Technical Architecture

The technology stack for Khana Bazaar is engineered to prioritize speed to market, developer productivity, and enterprise-grade scalability.

## 1. Frontend (User & Seller Interfaces)
- **Framework:** Next.js (React). Enables Server-Side Rendering (SSR) for superior SEO, ensuring organic discovery of the platform.
- **Delivery:** Built as a Progressive Web App (PWA), allowing users to install the application directly to their mobile devices without routing through an app store, saving on commission fees and bypassing complex review processes.

## 2. Backend API
- **Core Framework:** FastAPI (Python). Chosen for its native asynchronous capabilities, automatic API documentation (Swagger/ReDoc), and high performance that rivals NodeJS and Go.
- **ASGI Server:** Uvicorn. Required to run FastAPI and listen for web requests.
- **Asynchronous Processing:** Celery + Redis (Python Client). Offloads heavy tasks such as order routing, seller notifications, and email receipts to background workers, ensuring the customer's interface remains highly responsive.
- **Python Tooling:** Managed via `uv`. Code formatting and linting handled by **Ruff**. Type checking handled by **Mypy**. Testing uses **Pytest** and **pytest-asyncio**. Configuration management acts securely via **Pydantic-Settings**.

## 3. Database & Data Management
- **Primary Relational Database:** PostgreSQL. The industry standard for robust, ACID-compliant relational data. It handles the complex relationships between users, multiple stores, shared products, and localized inventory perfectly.
- **ORM & Migrations:** **SQLModel** (or SQLAlchemy) for database interactions mapped to FastAPI models, and **Alembic** for applying schema changes without losing data.
- **Database Driver:** **asyncpg** for non-blocking asynchronous communication between Python and PostgreSQL.
- **Caching Layer:** Redis. Used to cache the master product catalog and active user shopping carts to guarantee lightning-fast load times.

## 4. Payments & Transactions
- **Payment Gateway:** Integration skipped for the current phase. Planned for a future release using Razorpay or a similar provider for direct UPI integrations.

## 5. Deployment & Scalability Strategy (GCP)
The infrastructure will be exclusively hosted on Google Cloud Platform (GCP).
- **Application Hosting:** GCP Cloud Run. The FastAPI application and Next.js SSR frontend will be containerized using Docker and deployed to Cloud Run. This allows the backend to automatically scale from zero to thousands of instances in response to traffic spikes.
- **Database Hosting:** GCP Cloud SQL for PostgreSQL. A fully managed database service that handles backups, replication, and failover automatically.
- **Media Storage:** GCP Cloud Storage. Provides highly durable, low-cost storage for product images and store assets, served via Google's global CDN for rapid asset delivery to the end user.

## 6. The Developer Toolkit

| Category | Recommended Tool | Why It Fits Your Project |
| :--- | :--- | :--- |
| **Authentication** | Firebase Authentication | Native to the Google ecosystem. It offers a generous free tier and is highly reliable for Phone Number/OTP logins, which are essential for Indian consumers. |
| **Error Tracking** | Sentry | The industry standard for catching application crashes. It integrates seamlessly with both FastAPI and Next.js, showing you the exact line of code that caused a failure. |
| **Centralized Logging** | GCP Cloud Logging | Since you are deploying to GCP Cloud Run, your application logs are automatically aggregated here without any extra setup. |
| **SMS & OTPs** | MSG91 | A heavily relied-upon provider in India. It routes messages much more reliably and affordably to Indian telecom networks compared to international alternatives like Twilio. |
| **Transactional Email** | Resend | A modern, developer-friendly email API. Perfect for sending highly deliverable order receipts and welcome emails to your customers and sellers. |
| **WhatsApp Messaging** | Wati or Interakt | WhatsApp is the primary communication channel in India. These APIs allow you to send automated order tracking updates directly to a customer's WhatsApp. |
| **CI/CD Pipeline** | GitHub Actions | Automates your deployments. Pushing code to your main branch can trigger an automatic build and deployment directly to your GCP environments. |
| **Product Analytics** | PostHog | An open-source analytics tool that is excellent for tracking user behavior, such as identifying exactly where customers are dropping off during the checkout process. |
