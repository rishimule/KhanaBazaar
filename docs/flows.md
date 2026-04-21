# User and Data Flows

## 1. The User Flow: From Browsing to Checkout
This flow ensures the user is never blocked from shopping until the exact moment a transaction needs to happen.

### Step 1: Store Discovery & Context
- The customer opens Khana Bazaar and enters their delivery pin code.
- The app displays available local sellers. The customer clicks on "Store A".

### Step 2: Guest Cart Creation (Store A)
- The customer browses Store A's catalog and taps "Add to Cart".
- A cart specific to Store A is created in the background. The user is still not logged in.

### Step 3: Multi-Store Navigation (Store B)
- The customer navigates back to the main menu and clicks on "Store B".
- They add items to the cart. The app creates a second, separate cart for Store B. The user can view a "Carts" tab showing their active carts for both Store A and Store B.

### Step 4: The Checkout Trigger & Authentication
- The customer goes to their Store A cart and clicks "Proceed to Checkout".
- A bottom sheet or modal pops up: "Enter your email address to continue".
- The user enters their email, receives a 6-digit OTP (via the Khana Bazaar email service), and is verified. New users are prompted to enter their full name to complete registration.

### Step 5: Checkout & Order Tracking
- The user adds their delivery address and confirms the order (simulated payment flow).
- The Store A cart is converted into an active "Order". The Store B cart remains in their account for future checkout.
- The customer is redirected to a live tracking screen.

---

## 2. The Data Flow: How the Backend Handles It
To make guest carts and multi-store carts work seamlessly, your frontend (Next.js) and backend (FastAPI, Redis, PostgreSQL) need to pass data back and forth using anonymous session IDs.

### Phase 1: The Anonymous State (Guest Browsing)
- **Device Fingerprinting:** When a guest first opens the app, Next.js generates a unique random string (a UUID) called a `session_id`. This is saved in the browser's local storage or as a cookie.
- **Adding to Cart:** When the guest adds an item, Next.js sends an API request to FastAPI:
  - **Payload:** `{ session_id: "xyz-123", store_id: 10, product_id: 45, quantity: 1 }`
- **Redis Storage:** Because carts need to be extremely fast and are temporary, FastAPI saves this cart data in Redis. It creates a record linking the `session_id` and the `store_id` to the selected items.

### Phase 2: The Merge State (Logging In)
- **Authentication:** The user logs in via the self-hosted email-OTP system. The backend returns a secure JWT `access_token` and the `user` object.
- **The Merge Request:** Next.js immediately sends a "Merge Cart" request to FastAPI (passing the JWT in the Authorization header).
  - **Payload:** `{ session_id: "xyz-123" }`
- **Data Transfer:** FastAPI identifies the user from the JWT and looks up all Redis carts associated with `session_id: "xyz-123"`. It updates the ownership of those carts, replacing the anonymous `session_id` with the permanent database `user_id`. It then saves these permanent carts into your PostgreSQL database.

### Phase 3: Order Conversion
- **Checkout Initialization:** The user selects an address and hits checkout. FastAPI creates a "Pending Order" in Postgres (payment gateway integration is skipped for now).
- **Payment Simulation:** The system automatically simulates payment success.
- **Fulfillment Routing:** FastAPI marks the order as "Paid" (via simulation), clears the specific Store A cart from the database, and triggers the background Celery task to notify Store A's owner that they have a new order to pack.
