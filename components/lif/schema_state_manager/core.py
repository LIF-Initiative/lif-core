"""
Schema State Manager Component.

This component encapsulates schema state management for services that need to load
and maintain LIF schema data from the MDR or from bundled files.

Features:
    - Sync and async initialization supporting MDR or file-based schema loading
    - Thread-safe state access via lock
    - Fallback to bundled file when MDR is unavailable
    - Source tracking ("mdr" or "file")
    - Schema refresh capability (async only)

Usage:
    from lif.schema_state_manager import SchemaStateManager

    # Sync initialization (for module-level tool registration)
    manager = SchemaStateManager(config)
    manager.initialize_sync()

    # Or async initialization
    await manager.initialize()

    # Access state
    state = manager.state
    filter_model = state.filter_models.get("Person")
"""

import sys
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

import numpy as np
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

from lif.lif_schema_config import LIFSchemaConfig
from lif.logging import get_logger
from lif.mdr_client import (
    load_openapi_schema,
    get_openapi_lif_data_model_from_file,
    MDRClientException,
    MDRConfigurationError,
)
from lif.openapi_schema_parser import load_schema_leaves
from lif.openapi_schema_parser.core import SchemaLeaf
from lif.semantic_search_service.core import (
    build_embeddings,
    build_dynamic_filter_model,
    build_dynamic_mutation_model,
)

logger = get_logger(__name__)


@dataclass
class SchemaState:
    """
    Immutable state container for schema-derived data.

    Attributes:
        openapi: The raw OpenAPI specification dictionary
        leaves: All schema leaves across all root types
        leaves_by_root: Schema leaves organized by root type name
        filter_models: Dynamic Pydantic filter models keyed by root type
        mutation_models: Dynamic Pydantic mutation models keyed by root type
        embeddings: Pre-computed numpy embeddings for semantic search
        model: The loaded SentenceTransformer model
        source: Source of the schema ("mdr" or "file")
    """

    openapi: dict
    leaves: List[SchemaLeaf]
    leaves_by_root: Dict[str, List[SchemaLeaf]]
    filter_models: Dict[str, Type[BaseModel]]
    mutation_models: Dict[str, Type[BaseModel]]
    embeddings: np.ndarray
    model: SentenceTransformer
    source: str


class SchemaStateManager:
    """
    Manages schema state lifecycle with sync/async initialization and thread-safe access.

    This class handles:
    - Loading schema from MDR (with fallback to file)
    - Building filter and mutation models for each root type
    - Computing embeddings for semantic search
    - Thread-safe state access

    Args:
        config: LIFSchemaConfig instance with schema configuration
        attribute_keys: Attribute keys to extract from schema leaves
    """

    def __init__(
        self,
        config: LIFSchemaConfig,
        attribute_keys: Optional[List[str]] = None,
    ):
        self._config = config
        self._attribute_keys = attribute_keys or [
            "dataType",
            "xQueryable",
            "xMutable",
            "x-mutable",
            "enum",
            "x-queryable",
        ]
        self._state: Optional[SchemaState] = None
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def state(self) -> SchemaState:
        """Get the current schema state. Raises if not initialized."""
        with self._lock:
            if self._state is None:
                raise RuntimeError("SchemaStateManager not initialized. Call initialize() first.")
            return self._state

    @property
    def is_initialized(self) -> bool:
        """Check if the manager has been initialized."""
        with self._lock:
            return self._initialized

    def initialize_sync(self, force_file: bool = False) -> None:
        """
        Synchronously initialize the schema state by loading from MDR or file.

        This is the preferred method for module-level initialization where async
        is not available (e.g., FastMCP tool registration at import time).

        Args:
            force_file: If True, skip MDR and load directly from file

        Raises:
            SystemExit: If critical initialization fails (required root not found)
        """
        logger.info("Initializing SchemaStateManager (sync)...")

        # Load OpenAPI schema synchronously
        openapi, source = self._load_openapi_schema_sync(force_file)
        if openapi is None:
            logger.critical("Failed to load OpenAPI schema from both MDR and file")
            sys.exit(1)

        # Type narrowing: openapi is guaranteed to be dict after the check above
        assert openapi is not None

        # Complete the initialization with the loaded schema
        self._complete_initialization(openapi, source)

    async def initialize(self, force_file: bool = False) -> None:
        """
        Asynchronously initialize the schema state by loading from MDR or file.

        Args:
            force_file: If True, skip MDR and load directly from file

        Raises:
            SystemExit: If critical initialization fails (required root not found)
        """
        logger.info("Initializing SchemaStateManager (async)...")

        # Load OpenAPI schema asynchronously
        openapi, source = await self._load_openapi_schema_async(force_file)
        if openapi is None:
            logger.critical("Failed to load OpenAPI schema from both MDR and file")
            sys.exit(1)

        # Type narrowing: openapi is guaranteed to be dict after the check above
        assert openapi is not None

        # Complete the initialization with the loaded schema
        self._complete_initialization(openapi, source)

    def _complete_initialization(self, openapi: dict, source: str) -> None:
        """Complete initialization with the loaded OpenAPI schema."""
        # Load schema leaves for all root nodes
        leaves, leaves_by_root = self._load_schema_leaves(openapi)

        # Build filter and mutation models
        filter_models, mutation_models = self._build_models(leaves_by_root)

        # Load SentenceTransformer model
        model = self._load_sentence_transformer()

        # Build embeddings
        embeddings = self._build_embeddings(leaves, model)

        # Create and store state
        state = SchemaState(
            openapi=openapi,
            leaves=leaves,
            leaves_by_root=leaves_by_root,
            filter_models=filter_models,
            mutation_models=mutation_models,
            embeddings=embeddings,
            model=model,
            source=source,
        )

        with self._lock:
            self._state = state
            self._initialized = True

        logger.info(
            f"SchemaStateManager initialized successfully. "
            f"Source: {source}, Leaves: {len(leaves)}, "
            f"Filter models: {list(filter_models.keys())}"
        )

    async def refresh(self) -> Dict[str, Any]:
        """
        Refresh the schema by reloading from MDR.

        Returns:
            Dict with refresh status and metadata

        Note:
            If refresh fails, the existing state is preserved.
        """
        if not self._initialized:
            return {"success": False, "error": "Manager not initialized"}

        logger.info("Refreshing schema from MDR...")

        try:
            openapi, source = await self._load_openapi_schema_async(force_file=False)
            if openapi is None:
                return {
                    "success": False,
                    "error": "Failed to load schema from MDR",
                    "current_source": self._state.source if self._state else None,
                }

            leaves, leaves_by_root = self._load_schema_leaves(openapi)
            filter_models, mutation_models = self._build_models(leaves_by_root)

            # Reuse existing model for performance
            model = self._state.model if self._state else self._load_sentence_transformer()
            embeddings = self._build_embeddings(leaves, model)

            new_state = SchemaState(
                openapi=openapi,
                leaves=leaves,
                leaves_by_root=leaves_by_root,
                filter_models=filter_models,
                mutation_models=mutation_models,
                embeddings=embeddings,
                model=model,
                source=source,
            )

            with self._lock:
                old_leaf_count = len(self._state.leaves) if self._state else 0
                self._state = new_state

            return {
                "success": True,
                "source": source,
                "leaf_count": len(leaves),
                "previous_leaf_count": old_leaf_count,
                "filter_models": list(filter_models.keys()),
            }

        except Exception as e:
            logger.error(f"Schema refresh failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "current_source": self._state.source if self._state else None,
            }

    def get_status(self) -> Dict[str, Any]:
        """Get current schema status and metadata."""
        with self._lock:
            if not self._initialized or self._state is None:
                return {
                    "initialized": False,
                    "source": None,
                    "leaf_count": 0,
                    "roots": [],
                }

            return {
                "initialized": True,
                "source": self._state.source,
                "leaf_count": len(self._state.leaves),
                "roots": list(self._state.leaves_by_root.keys()),
                "filter_models": list(self._state.filter_models.keys()),
                "mutation_models": list(self._state.mutation_models.keys()),
            }

    def _load_openapi_schema_sync(self, force_file: bool) -> tuple[Optional[dict], str]:
        """
        Load OpenAPI schema synchronously.

        Uses the config-based load_openapi_schema() which does NOT fall back
        to file if MDR is configured but fails. This prevents silent use of
        stale data.

        Args:
            force_file: If True, load from file regardless of config

        Returns:
            Tuple of (openapi_dict, source) or (None, source) on failure
        """
        if force_file:
            logger.info("Loading OpenAPI schema from bundled file (force_file=True)")
            try:
                openapi = get_openapi_lif_data_model_from_file(
                    self._config.openapi_json_filename
                )
                return openapi, "file"
            except Exception as e:
                logger.error(f"Failed to load OpenAPI schema from file: {e}")
                return None, "file"

        # Use config-based loading (no silent fallback to file)
        try:
            openapi, source = load_openapi_schema(self._config)
            return openapi, source
        except MDRConfigurationError as e:
            logger.critical(f"MDR configuration error: {e}")
            return None, "mdr"
        except MDRClientException as e:
            logger.critical(f"Failed to load schema from MDR: {e}")
            return None, "mdr"
        except Exception as e:
            logger.critical(f"Unexpected error loading OpenAPI schema: {e}")
            return None, "unknown"

    async def _load_openapi_schema_async(self, force_file: bool) -> tuple[Optional[dict], str]:
        """
        Load OpenAPI schema asynchronously.

        Note: Currently uses sync loading since the config-based function is sync.
        For true async, would need to add async versions of the MDR functions.

        Args:
            force_file: If True, load from file regardless of config

        Returns:
            Tuple of (openapi_dict, source) or (None, source) on failure
        """
        # For now, delegate to sync version since load_openapi_schema is sync
        # A future enhancement could add async MDR fetch
        return self._load_openapi_schema_sync(force_file)

    def _load_schema_leaves(
        self, openapi: dict
    ) -> tuple[List[SchemaLeaf], Dict[str, List[SchemaLeaf]]]:
        """Load schema leaves for all configured root types."""
        all_leaves: List[SchemaLeaf] = []
        leaves_by_root: Dict[str, List[SchemaLeaf]] = {}

        for root_node in self._config.all_root_types:
            try:
                root_leaves = load_schema_leaves(
                    openapi, root_node, attribute_keys=self._attribute_keys
                )
                leaves_by_root[root_node] = root_leaves
                all_leaves.extend(root_leaves)
                logger.info(f"Loaded {len(root_leaves)} schema leaves for root '{root_node}'")
            except Exception as e:
                # Primary root is required; additional roots are optional
                if root_node == self._config.root_type_name:
                    logger.critical(
                        f"Failed to load schema leaves for required root '{root_node}': {e}"
                    )
                    sys.exit(1)
                else:
                    logger.warning(
                        f"Failed to load schema leaves for optional root '{root_node}': {e}"
                    )

        logger.info(f"Total schema leaves loaded: {len(all_leaves)}")
        return all_leaves, leaves_by_root

    def _build_models(
        self, leaves_by_root: Dict[str, List[SchemaLeaf]]
    ) -> tuple[Dict[str, Type[BaseModel]], Dict[str, Type[BaseModel]]]:
        """Build filter and mutation models for each root type."""
        filter_models: Dict[str, Type[BaseModel]] = {}
        mutation_models: Dict[str, Type[BaseModel]] = {}

        for root_node, root_leaves in leaves_by_root.items():
            # Build filter model
            try:
                filter_model = build_dynamic_filter_model(root_leaves)
                if root_node in filter_model:
                    filter_models[root_node] = filter_model[root_node]
                    logger.info(f"Built dynamic filter model for '{root_node}'")
            except Exception as e:
                logger.warning(f"Failed to build dynamic filter model for '{root_node}': {e}")

            # Build mutation model
            try:
                mutation_model = build_dynamic_mutation_model(root_leaves)
                if root_node in mutation_model:
                    mutation_models[root_node] = mutation_model[root_node]
                    logger.info(f"Built dynamic mutation model for '{root_node}'")
            except Exception as e:
                logger.warning(f"Failed to build dynamic mutation model for '{root_node}': {e}")

        # Verify required root has filter model
        if self._config.root_type_name not in filter_models:
            logger.critical(
                f"Failed to build filter model for required root '{self._config.root_type_name}'"
            )
            sys.exit(1)

        return filter_models, mutation_models

    def _load_sentence_transformer(self) -> SentenceTransformer:
        """Load the SentenceTransformer model."""
        model_name = self._config.semantic_search_model_name
        logger.info(f"Loading SentenceTransformer model: {model_name}")
        try:
            return SentenceTransformer(model_name)
        except Exception as e:
            logger.critical(f"Failed to load SentenceTransformer model: {e}")
            sys.exit(1)

    def _build_embeddings(
        self, leaves: List[SchemaLeaf], model: SentenceTransformer
    ) -> np.ndarray:
        """Build embeddings for all schema leaves."""
        logger.info(f"Building embeddings for {len(leaves)} schema leaves")
        embedding_texts = [leaf.description for leaf in leaves]
        try:
            return build_embeddings(embedding_texts, model)
        except Exception as e:
            logger.critical(f"Failed to build embeddings: {e}")
            sys.exit(1)
