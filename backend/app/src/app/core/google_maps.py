"""Thin async Google Maps Platform client.

Direct httpx calls — no Google SDK dependency. Each function returns a
typed dataclass; callers are responsible for caching/rate-limiting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


class GoogleMapsError(Exception):
    """Raised on non-OK status from any Google Maps endpoint."""


class GeocodeNotFoundError(GoogleMapsError):
    """Raised when forward/reverse geocoding finds no result."""


@dataclass(frozen=True)
class AddressComponent:
    long_name: str
    short_name: str
    types: tuple[str, ...]


@dataclass(frozen=True)
class Prediction:
    place_id: str
    description: str


@dataclass(frozen=True)
class Place:
    place_id: str
    formatted_address: str
    latitude: float
    longitude: float
    components: tuple[AddressComponent, ...]


_BASE = "https://maps.googleapis.com/maps/api"


class GoogleMapsClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout: float = 5.0,
    ) -> None:
        self._key = api_key
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        params = {**params, "key": self._key}
        resp = await self._client.get(f"{_BASE}{path}", params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        if body.get("status") not in {"OK", "ZERO_RESULTS"}:
            raise GoogleMapsError(
                f"google maps: {body.get('status')}: {body.get('error_message', '')}"
            )
        return body

    async def aclose(self) -> None:
        await self._client.aclose()


def _components(raw: list[dict[str, Any]]) -> tuple[AddressComponent, ...]:
    return tuple(
        AddressComponent(
            long_name=c.get("long_name", ""),
            short_name=c.get("short_name", ""),
            types=tuple(c.get("types", [])),
        )
        for c in raw
    )


async def autocomplete(
    client: GoogleMapsClient, *, query: str, session_token: str
) -> list[Prediction]:
    body = await client.get(
        "/place/autocomplete/json",
        {
            "input": query,
            "sessiontoken": session_token,
            "components": "country:in",
        },
    )
    if body.get("status") == "ZERO_RESULTS":
        return []
    return [
        Prediction(place_id=p["place_id"], description=p["description"])
        for p in body.get("predictions", [])
    ]


async def place_details(
    client: GoogleMapsClient, *, place_id: str, session_token: str
) -> Place:
    body = await client.get(
        "/place/details/json",
        {
            "place_id": place_id,
            "sessiontoken": session_token,
            "fields": "place_id,formatted_address,geometry/location,address_components",
        },
    )
    if body.get("status") == "ZERO_RESULTS":
        raise GoogleMapsError(f"no place details for {place_id}")
    r = body["result"]
    loc = r["geometry"]["location"]
    return Place(
        place_id=r["place_id"],
        formatted_address=r.get("formatted_address", ""),
        latitude=float(loc["lat"]),
        longitude=float(loc["lng"]),
        components=_components(r.get("address_components", [])),
    )


async def forward_geocode(client: GoogleMapsClient, *, address: str) -> Place:
    body = await client.get(
        "/geocode/json",
        {"address": address, "components": "country:IN"},
    )
    if body.get("status") == "ZERO_RESULTS" or not body.get("results"):
        raise GeocodeNotFoundError(f"no geocode for {address!r}")
    r = body["results"][0]
    loc = r["geometry"]["location"]
    return Place(
        place_id=r.get("place_id", ""),
        formatted_address=r.get("formatted_address", ""),
        latitude=float(loc["lat"]),
        longitude=float(loc["lng"]),
        components=_components(r.get("address_components", [])),
    )


async def reverse_geocode(client: GoogleMapsClient, *, lat: float, lng: float) -> Place:
    body = await client.get(
        "/geocode/json",
        {"latlng": f"{lat},{lng}"},
    )
    if body.get("status") == "ZERO_RESULTS" or not body.get("results"):
        raise GeocodeNotFoundError(f"no reverse geocode for {lat},{lng}")
    r = body["results"][0]
    loc = r["geometry"]["location"]
    return Place(
        place_id=r.get("place_id", ""),
        formatted_address=r.get("formatted_address", ""),
        latitude=float(loc["lat"]),
        longitude=float(loc["lng"]),
        components=_components(r.get("address_components", [])),
    )
