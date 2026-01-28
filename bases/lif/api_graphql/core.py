"""
ASGI application generator for LIF GraphQL.

This base wires environment configuration, constructs the HTTP backend,
builds the GraphQL schema via the `lif.graphql.schema_factory`, and mounts
the GraphQL endpoint using Strawberry's FastAPI router.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from lif.graphql.core import HttpBackend
from lif.graphql.schema_factory import build_schema
from lif.logging.core import get_logger
from lif.openapi_schema.core import get_schema_fields
from lif.utils.core import get_required_env_var
from lif.utils.validation import is_truthy

logger = get_logger(__name__)

# Environment variable validation at import time
LIF_QUERY_PLANNER_URL = get_required_env_var("LIF_QUERY_PLANNER_URL")


def create_app() -> FastAPI:
	# Ensure process cwd is the project root so Rich/Strawberry can compute relative paths
	try:
		project_root = Path(__file__).resolve().parents[4]  # lif-main
		os.chdir(project_root)
		logger.debug(f"Set working directory to project root: {project_root}")
	except Exception:
		logger.debug("Could not change working directory to project root", exc_info=True)

	root_type = os.getenv("LIF_GRAPHQL_ROOT_TYPE_NAME", "Person")

	# TODO: The graphql api should only contact the query planner and not the query cache directly
	# HTTP-only backend configuration

	# Back-compat fallback from planner URL if provided
	base_url = LIF_QUERY_PLANNER_URL.rstrip("/")
	query_url = f"{base_url}/query"
	update_url = f"{base_url}/update"

	logger.info(f"GraphQL root type: {root_type}")
	logger.info(f"Query URL: {query_url}")
	logger.info(f"Update URL: {update_url}")

	backend = HttpBackend(query_url=query_url, update_url=update_url)
	fields = get_schema_fields()
	schema = build_schema(schema_fields=fields, root_node=root_type, backend=backend)

	# Optional schema artifact dumping for tooling
	if is_truthy(os.getenv("LIF_GRAPHQL_DUMP_SCHEMA")):
		out_dir = Path(__file__).parent / "_artifacts"
		out_dir.mkdir(parents=True, exist_ok=True)
		(out_dir / "schema.graphql").write_text(schema.as_str(), encoding="utf-8")
		logger.info(f"Wrote schema to {out_dir / 'schema.graphql'}")

	app = FastAPI()
	app.include_router(GraphQLRouter(schema), prefix="/graphql")
	return app
