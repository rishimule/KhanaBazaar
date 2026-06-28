# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_COMPANY_NAME=""
ARG NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=""
ARG NEXT_PUBLIC_VAPID_PUBLIC_KEY=""
# Next resolves rewrites() at BUILD time into routes-manifest.json, so the
# prod /api/v1/* -> api proxy destination must be known here (see next.config.ts).
ARG INTERNAL_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_COMPANY_NAME=$NEXT_PUBLIC_COMPANY_NAME \
    NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY=$NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY \
    NEXT_PUBLIC_VAPID_PUBLIC_KEY=$NEXT_PUBLIC_VAPID_PUBLIC_KEY \
    INTERNAL_API_URL=$INTERNAL_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
# INTERNAL_API_URL must also be present at runtime for next start's rewrite proxy.
ARG INTERNAL_API_URL=""
ENV INTERNAL_API_URL=$INTERNAL_API_URL
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts
COPY --from=builder /app/src ./src

# Cloud Run injects $PORT (default 8080).
CMD ["sh", "-c", "npm start -- --port ${PORT:-8080} --hostname 0.0.0.0"]
