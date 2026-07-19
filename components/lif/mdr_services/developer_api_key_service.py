"""Developer API key management (#1033).

User-owned keys for programmatic access to the LDE /exports API. Keys are workspace-scoped
(they live in the tenant schema, reached via the request's search_path) and user-scoped by
OwnerSub (the Cognito `sub`). The raw key is generated + returned exactly once; only its
SHA-256 hash is stored. Revocation is a soft state (RevokedDate).
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from lif.datatypes.mdr_sql_model import DeveloperApiKey
from lif.mdr_dto.developer_api_key_dto import CreatedDeveloperApiKeyDTO, CreateDeveloperApiKeyDTO, DeveloperApiKeyDTO

KEY_PREFIX = "lifk_"
_PREFIX_DISPLAY_LEN = 12  # leading chars kept for display (never the full key)


def _generate_key() -> Tuple[str, str, str]:
    """Return ``(raw_key, key_prefix, key_hash)``.

    The raw key is high-entropy (``secrets.token_urlsafe(32)``), so a plain SHA-256 at rest is
    sufficient (no salt/KDF needed — unlike low-entropy passwords). The raw key is returned to the
    caller once and never stored.
    """
    raw = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, raw[:_PREFIX_DISPLAY_LEN], key_hash


async def create_developer_api_key(
    session: AsyncSession, owner_sub: str, data: CreateDeveloperApiKeyDTO
) -> CreatedDeveloperApiKeyDTO:
    raw, key_prefix, key_hash = _generate_key()
    key = DeveloperApiKey(OwnerSub=owner_sub, Label=data.Label, KeyPrefix=key_prefix, KeyHash=key_hash)
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return CreatedDeveloperApiKeyDTO(
        Id=key.Id, Label=key.Label, KeyPrefix=key.KeyPrefix, CreationDate=key.CreationDate, Key=raw
    )


async def list_developer_api_keys(session: AsyncSession, owner_sub: str) -> List[DeveloperApiKeyDTO]:
    result = await session.execute(select(DeveloperApiKey).where(DeveloperApiKey.OwnerSub == owner_sub))
    return [DeveloperApiKeyDTO.from_orm(key) for key in result.scalars().all()]


async def revoke_developer_api_key(session: AsyncSession, owner_sub: str, key_id: int) -> None:
    key = await session.get(DeveloperApiKey, key_id)
    # 404 (not 403) when the key isn't the caller's, so we don't reveal other users' key ids.
    if key is None or key.OwnerSub != owner_sub:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.RevokedDate is None:
        key.RevokedDate = datetime.now(timezone.utc)
        session.add(key)
        await session.commit()
