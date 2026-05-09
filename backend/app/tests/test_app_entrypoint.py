# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import FastAPI


def test_uvicorn_entrypoint_exports_fastapi_app() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)
