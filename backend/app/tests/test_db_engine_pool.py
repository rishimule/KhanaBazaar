# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.db import session as db_session


def test_pool_kwargs_are_constrained_for_cloud_sql():
    kw = db_session._engine_kwargs()
    assert kw["pool_size"] == 2
    assert kw["max_overflow"] == 3
    assert kw["pool_pre_ping"] is True


def test_echo_disabled_in_production(monkeypatch):
    monkeypatch.setattr(db_session.settings, "ENVIRONMENT", "production")
    assert db_session._engine_kwargs()["echo"] is False


def test_echo_enabled_outside_production(monkeypatch):
    monkeypatch.setattr(db_session.settings, "ENVIRONMENT", "development")
    assert db_session._engine_kwargs()["echo"] is True
