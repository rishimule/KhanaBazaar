# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter

from app.api import (
    admin_actions,
    auth,
    carts,
    catalog,
    catalog_admin,
    customers,
    dev_inbox,
    favorites,
    geo,
    meta,
    notifications,
    orders,
    platform_fees,
    policies,
    referrals,
    search,
    seller_change_requests,
    seller_onboarding,
    seller_phone_change,
    sellers,
    stores,
    tasks,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(catalog_admin.router, prefix="/catalog")
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
api_router.include_router(
    seller_change_requests.router,
    prefix="/sellers",
    tags=["sellers", "change-requests"],
)
api_router.include_router(
    seller_phone_change.router,
    prefix="/sellers",
    tags=["sellers"],
)
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(dev_inbox.router, prefix="/dev", tags=["dev"])
api_router.include_router(carts.router, prefix="/carts", tags=["carts"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(policies.router, prefix="/policies", tags=["policies"])
api_router.include_router(geo.router, prefix="/geo", tags=["geo"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(admin_actions.router, prefix="/admin", tags=["admin"])
api_router.include_router(policies.admin_router, prefix="/admin", tags=["admin", "policies"])
api_router.include_router(platform_fees.admin_router, prefix="/admin", tags=["admin", "fees"])
api_router.include_router(platform_fees.seller_router, prefix="/sellers", tags=["sellers", "fees"])
api_router.include_router(
    seller_onboarding.router,
    prefix="/seller-onboarding-requests",
    tags=["seller-onboarding"],
)
api_router.include_router(favorites.router, prefix="/favorites", tags=["favorites"])
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["notifications"]
)
api_router.include_router(
    notifications.seller_router, prefix="/sellers", tags=["sellers", "notifications"]
)
api_router.include_router(referrals.router, prefix="/referrals", tags=["referrals"])
api_router.include_router(
    referrals.admin_router, prefix="/admin", tags=["admin", "referrals"]
)
