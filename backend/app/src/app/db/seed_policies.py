# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Idempotent seed of v1 Privacy + Terms documents from bundled Markdown.

Inserts version 1 of a kind only if that kind has no document yet, so it is
safe to run on every deploy. Run from `backend/app`:

    uv run python -m app.db.seed_policies
"""
import asyncio
from pathlib import Path

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import engine
from app.models.consent import PolicyDocument, PolicyKind
from app.services.consent import get_current_version

_SEED_DIR = Path(__file__).parent / "policy_seed"
_FILES = {PolicyKind.terms: "terms.md", PolicyKind.privacy: "privacy.md"}


async def seed_policies(session: AsyncSession) -> dict[str, int]:
    created: dict[str, int] = {}
    for kind, filename in _FILES.items():
        current = await get_current_version(session, kind)
        if current > 0:
            created[kind.value] = 0
            continue
        body = (_SEED_DIR / filename).read_text(encoding="utf-8")
        session.add(PolicyDocument(kind=kind, version=1, body=body, published_by=None))
        created[kind.value] = 1
    await session.commit()
    return created


async def _main() -> None:
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            result = await seed_policies(session)
            print({"seeded": result})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
