#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install uv

uv sync --frozen --no-dev
