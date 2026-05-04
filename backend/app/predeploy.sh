#!/usr/bin/env bash
set -o errexit

uv run alembic upgrade head
