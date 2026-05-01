from fastapi import FastAPI


def test_uvicorn_entrypoint_exports_fastapi_app() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)
