"""Demo-only endpoints — a base-level demo decoration (ADR 0004).

Serves the curated demo personas from the shared `demo_personas` brick (#1055)
so the LDE test/export playground (#1036) and other demo UIs can populate a
learner picker from a single source, without a second copy that drifts. The data
is synthetic and read-only.

This router is mounted only when demo endpoints are enabled (see core.py), so a
bare/production adopter that doesn't want demo surface can exclude it — MDR's
core logic never depends on this.
"""

from typing import Any

from fastapi import APIRouter

from lif.demo_personas import get_demo_personas_as_dicts

router = APIRouter()


@router.get("/personas", response_model=list[dict[str, Any]])
async def list_demo_personas() -> list[dict[str, Any]]:
    """Return the curated demo learners (the same six the Advisor app uses)."""
    return get_demo_personas_as_dicts()
