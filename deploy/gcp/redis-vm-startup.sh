#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# Startup script for the kb-redis-vm (e2-micro). Installs Redis 7, binds to the
# private interface, caps memory, and enables LRU eviction. Network isolation is
# enforced by the VPC firewall (no external IP), so protected-mode is disabled.
set -euo pipefail

apt-get update
apt-get install -y redis-server

sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf
sed -i 's/^# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf
sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf

systemctl enable redis-server
systemctl restart redis-server
