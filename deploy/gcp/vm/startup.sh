#!/usr/bin/env bash
# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# GCE startup script for kb-svc. Idempotent.
set -euxo pipefail

# 1. Docker + compose plugin
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

# 2. Mount the persistent meili data disk (device name 'meili-disk')
DISK=/dev/disk/by-id/google-meili-disk
MOUNT=/mnt/disks/meili
mkdir -p "$MOUNT"
if ! blkid "$DISK" >/dev/null 2>&1; then
  mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard "$DISK"
fi
grep -q "$MOUNT" /etc/fstab || echo "$DISK $MOUNT ext4 discard,defaults,nofail 0 2" >> /etc/fstab
mount -a
chmod a+w "$MOUNT"

# 3. Auth docker to Artifact Registry using the VM service account
gcloud auth configure-docker asia-south1-docker.pkg.dev --quiet || true

# 4. Bring up the stack (compose + .env are pushed to /opt/kb by the operator)
if [ -f /opt/kb/docker-compose.yml ]; then
  cd /opt/kb
  docker compose pull
  docker compose up -d
fi
