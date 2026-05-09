# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for the thin Google Maps Platform client wrapper."""
from typing import Any

import httpx
import pytest

from app.core.google_maps import (
    GoogleMapsClient,
    GoogleMapsError,
    autocomplete,
    place_details,
    reverse_geocode,
)


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self._status = status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status, json=self._payload, request=request)


@pytest.mark.asyncio
async def test_autocomplete_parses_predictions() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "OK",
            "predictions": [
                {"place_id": "p1", "description": "A, India"},
                {"place_id": "p2", "description": "B, India"},
            ],
        }),
    )
    out = await autocomplete(client, query="andheri", session_token="s1")
    await client.aclose()
    assert len(out) == 2
    assert out[0].place_id == "p1"
    assert out[0].description == "A, India"


@pytest.mark.asyncio
async def test_autocomplete_zero_results_returns_empty_list() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({"status": "ZERO_RESULTS", "predictions": []}),
    )
    out = await autocomplete(client, query="xyz", session_token="s1")
    await client.aclose()
    assert out == []


@pytest.mark.asyncio
async def test_place_details_returns_lat_lng() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "OK",
            "result": {
                "place_id": "p1",
                "formatted_address": "X",
                "geometry": {"location": {"lat": 18.9, "lng": 72.8}},
                "address_components": [
                    {"long_name": "Mumbai", "short_name": "Mumbai", "types": ["locality"]},
                ],
            },
        }),
    )
    out = await place_details(client, place_id="p1", session_token="s1")
    await client.aclose()
    assert out.latitude == 18.9
    assert out.longitude == 72.8
    assert out.formatted_address == "X"
    assert out.components[0].long_name == "Mumbai"


@pytest.mark.asyncio
async def test_reverse_geocode_returns_first_result() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Y",
                    "address_components": [],
                    "geometry": {"location": {"lat": 18.9, "lng": 72.8}},
                    "place_id": "p2",
                },
            ],
        }),
    )
    out = await reverse_geocode(client, lat=18.9, lng=72.8)
    await client.aclose()
    assert out.formatted_address == "Y"


@pytest.mark.asyncio
async def test_reverse_zero_results_raises() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({"status": "ZERO_RESULTS", "results": []}),
    )
    with pytest.raises(GoogleMapsError):
        await reverse_geocode(client, lat=0.0, lng=0.0)
    await client.aclose()


@pytest.mark.asyncio
async def test_invalid_status_raises() -> None:
    client = GoogleMapsClient(
        api_key="test",
        transport=_MockTransport({
            "status": "REQUEST_DENIED",
            "error_message": "API key invalid",
        }),
    )
    with pytest.raises(GoogleMapsError, match="REQUEST_DENIED"):
        await autocomplete(client, query="x", session_token="s")
    await client.aclose()
