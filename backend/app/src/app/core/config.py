# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import logging

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = ""
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Branding — single source for the displayed company/brand name. Falls back
    # to "Khanabazaar". EMAIL_BRAND_NAME and PROJECT_NAME derive from this when
    # left unset (see _resolve_defaults).
    COMPANY_NAME: str = "Khanabazaar"

    # JWT
    JWT_SECRET: str
    JWT_EXPIRES_HOURS: int = 24

    # Referrals
    REFERRAL_INVITE_EXPIRY_DAYS: int = 14
    REFERRAL_RATE_LIMIT_PER_HOUR: int = 20

    # OTP
    OTP_PEPPER: str
    OTP_TTL_SECONDS: int = 600
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN: int = 60
    OTP_MAX_PER_HOUR: int = 5

    # Delivery-handover OTP (separate from auth OTP; no TTL — valid until delivered)
    DELIVERY_OTP_MAX_ATTEMPTS: int = 5
    DELIVERY_OTP_RESEND_COOLDOWN: int = 60

    # Email: "console" (dev/test) or "resend" (production)
    EMAIL_PROVIDER: str = "console"
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""

    # SMTP (generic; configured for Gmail in local dev). EMAIL_PROVIDER="smtp"
    # or "smtp+console" activates it. See .env.example / docs/development_guide.md.
    # Temporary local-dev alternative to Resend.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = False
    SMTP_TIMEOUT: float = 10.0

    # Support inbox: where /customers/me/support messages get forwarded.
    SUPPORT_EMAIL: str = "support@khanabazaar.example"
    # Reply-to header on customer-facing emails. Falls back to SUPPORT_EMAIL.
    EMAIL_REPLY_TO: str | None = None
    EMAIL_BRAND_NAME: str = ""
    # Base URL used to build CTA links inside email templates.
    EMAIL_FRONTEND_BASE_URL: str = "http://localhost:3000"

    # SMS: "console" (dev/test) or "twilio" (production)
    SMS_PROVIDER: str = "console"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""  # E.164, e.g. "+15005550006"

    # WhatsApp: "none" (disabled) | "console" (mock → dev_whatsapp) | "twilio".
    # `none` is the safe default; OTP falls back to SMS and order-update
    # WhatsApp is skipped when disabled.
    WHATSAPP_PROVIDER: str = "none"
    TWILIO_WHATSAPP_FROM: str = ""  # e.g. "whatsapp:+14155238886" (sandbox/approved)

    # Dev Mailbox (/dev-emails, /dev-sms) — HTTP Basic creds. Empty = feature
    # disabled (endpoints 404). Only honoured when ENVIRONMENT == "development".
    DEV_INBOX_USER: str = ""
    DEV_INBOX_PASSWORD: str = ""

    DATABASE_URL: str
    REDIS_URL: str

    # CORS — comma-separated list of allowed frontend origins
    FRONTEND_ORIGIN: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Geo / Google Maps Platform
    GOOGLE_MAPS_SERVER_API_KEY: str = ""
    GOOGLE_MAPS_BROWSER_API_KEY: str = ""  # exposed to FE; referrer-restricted
    GEO_RATE_LIMIT_PER_MIN: int = 30
    GEO_AUTOCOMPLETE_CACHE_TTL_SECONDS: int = 60
    GEO_REVERSE_CACHE_TTL_SECONDS: int = 86400

    # Meilisearch
    MEILI_URL: str = "http://localhost:7700"
    MEILI_MASTER_KEY: str = "dev-master-key-change-me"

    # Search rate limits (per IP per minute)
    SEARCH_RATE_LIMIT_SUGGEST_PER_MIN: int = 60
    SEARCH_RATE_LIMIT_PRODUCTS_PER_MIN: int = 30
    SEARCH_RATE_LIMIT_BROWSE_PER_MIN: int = 60

    # Search cache TTLs
    SEARCH_SUGGEST_CACHE_TTL_SECONDS: int = 60
    SEARCH_SERVICEABLE_GRID_TTL_SECONDS: int = 60
    SEARCH_BROWSE_CACHE_TTL_SECONDS: int = 60

    # Web Push (VAPID) — generate keys once; see docs/development_guide.md.
    # VAPID_PRIVATE_KEY is the RAW base64url EC private key (~43 chars), NOT a
    # PKCS8 PEM — py_vapid.Vapid.from_string base64url-decodes it to the 32-byte
    # scalar (a PEM fails with "ASN.1 parsing error"). VAPID_PUBLIC_KEY is the
    # base64url-encoded uncompressed EC point the browser uses as
    # applicationServerKey (also exposed to the FE as NEXT_PUBLIC_VAPID_PUBLIC_KEY).
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    # Must be a real, deliverable contact on a real domain — Apple's push
    # service rejects placeholder/reserved TLDs (.example) with 403 BadJwtToken.
    VAPID_SUBJECT: str = "mailto:support@khanabazaar.dev"

    # Product image storage
    # IMAGE_STORAGE_BACKEND: "local" (dev/test, FastAPI StaticFiles) | "gcs" (prod)
    IMAGE_STORAGE_BACKEND: str = "local"
    IMAGE_MAX_UPLOAD_MB: int = 10
    IMAGE_MAX_DIMENSION_PX: int = 2048
    # Decompression-bomb guard: reject images above this many pixels (~40MP).
    IMAGE_MAX_PIXELS: int = 40_000_000
    # Local backend: filesystem dir (relative to backend/app CWD) + URL prefix.
    MEDIA_LOCAL_DIR: str = "var/uploads"
    MEDIA_URL_PREFIX: str = "/media"
    # GCS backend
    GCS_PRODUCT_IMAGES_BUCKET: str = ""
    # Optional override for the public object URL base (CDN/custom domain).
    GCS_PUBLIC_BASE_URL: str = ""
    # Dedicated bucket for user-uploaded media (avatars now, seller banners later).
    GCS_USER_MEDIA_BUCKET: str = ""
    GCS_USER_MEDIA_PUBLIC_BASE_URL: str = ""
    # Avatars are downscaled smaller than catalog product images.
    AVATAR_MAX_DIMENSION_PX: int = 512
    # Store logos are square-ish, downscaled like avatars.
    STORE_LOGO_MAX_DIMENSION_PX: int = 512

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]

    @model_validator(mode="after")
    def _resolve_defaults(self) -> "Settings":
        object.__setattr__(self, "COMPANY_NAME", self.COMPANY_NAME.strip() or "Khanabazaar")
        if not self.EMAIL_BRAND_NAME:
            object.__setattr__(self, "EMAIL_BRAND_NAME", self.COMPANY_NAME)
        if not self.PROJECT_NAME:
            object.__setattr__(self, "PROJECT_NAME", f"{self.COMPANY_NAME} API")
        if self.EMAIL_REPLY_TO is None:
            object.__setattr__(self, "EMAIL_REPLY_TO", self.SUPPORT_EMAIL)
        if self.ENVIRONMENT == "production" and ".example" in self.SUPPORT_EMAIL:
            logging.getLogger(__name__).warning(
                "SUPPORT_EMAIL still uses the .example placeholder in production: %s",
                self.SUPPORT_EMAIL,
            )
        return self

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        # Render Postgres exposes a `postgres://` URL; SQLModel needs asyncpg.
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
