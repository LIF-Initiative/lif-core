"""
Centralized type registry for GraphQL schema generation.
Manages dynamic creation and caching of Pydantic and Strawberry types.
"""

from typing import Dict, Type, Optional
# import strawberry
from strawberry.experimental.pydantic import input as pyd_input
from strawberry.experimental.pydantic import type as pyd_type

from lif.dynamic_models.core import build_filter_models, build_full_models, build_mutation_models
from lif.openapi_schema.core import get_schema_fields
from lif.graphql.utils import to_pascal_case_from_str, unique_type_name

class TypeRegistry:
    """Singleton registry for managing dynamically generated types."""
    
    _instance: Optional['TypeRegistry'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'TypeRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.strawberry_types: Dict[str, Type] = {}
            self.strawberry_inputs: Dict[str, Type] = {}
            self.pydantic_models: Dict[str, Type] = {}
            self._initialized = True
    
    def initialize_types(self, root_node: str, minimal_mode: bool = False):
        """Initialize all dynamic types for the given root node."""
        if self.strawberry_types:  # Already initialized
            return
            
        # Build dynamic Pydantic models
        fields = get_schema_fields()
        filter_models = build_filter_models(fields, allow_extra=False, all_optional=False)
        mutation_models = build_mutation_models(fields, allow_extra=False, all_optional=True)
        full_models = build_full_models(fields, allow_extra=False, all_optional=True)
        
        # Store Pydantic models
        self.pydantic_models.update({
            'filter_models': filter_models,
            'mutation_models': mutation_models,
            'full_models': full_models
        })
        
        if not minimal_mode:
            # Generate Strawberry types
            self._create_strawberry_types(full_models, filter_models, mutation_models, root_node)
    
    def _create_strawberry_types(self, full_models, filter_models, mutation_models, root_node):
        """Create Strawberry types from Pydantic models."""
        # Output types
        for name, model in full_models.items():
            if "wrapper" in name.lower():
                continue
            tname = to_pascal_case_from_str(name)
            if tname not in self.strawberry_types:
                self.strawberry_types[tname] = pyd_type(model=model, all_fields=True)(
                    type(tname, (), {})
                )
        
        # Filter input types
        for name, model in filter_models.items():
            if "wrapper" in name.lower():
                continue
            iname = unique_type_name(name, "FilterInput", root_node)
            iname = to_pascal_case_from_str(iname)
            if iname not in self.strawberry_inputs:
                self.strawberry_inputs[iname] = pyd_input(model=model, all_fields=True)(
                    type(iname, (), {})
                )
        
        # Mutation input types
        for name, model in mutation_models.items():
            if "wrapper" in name.lower():
                continue
            iname = unique_type_name(name, "MutationInput", root_node)
            iname = to_pascal_case_from_str(iname)
            if iname not in self.strawberry_inputs:
                self.strawberry_inputs[iname] = pyd_input(model=model, all_fields=True)(
                    type(iname, (), {})
                )
    
    def get_models_for_root(self, root_node: str):
        """Get the main models for a root node."""
        root_name = to_pascal_case_from_str(root_node)
        lc_root = root_node[:1].lower() + root_node[1:]
        
        full_models = self.pydantic_models['full_models']
        filter_models = self.pydantic_models['filter_models']
        mutation_models = self.pydantic_models['mutation_models']
        
        # Get FullModel
        full_model = full_models.get(lc_root) or full_models.get(f"{root_name}Type")
        if full_model is None:
            raise KeyError(f"Cannot locate FullModel for root '{root_node}' in dynamic models")
        
        return {
            'FullModel': full_model,
            'FilterModel': filter_models[f"{root_name}Filter"],
            'MutationModel': mutation_models[f"{root_name}Mutation"],
            'WrapperModel': full_models[f"{root_name.lower()}_wrapper"]
        }
    
    def get_strawberry_types_for_root(self, root_node: str):
        """Get Strawberry types for a root node."""
        root_name = to_pascal_case_from_str(root_node)
        
        return {
            'RootType': self.strawberry_types[root_name],
            'FilterInput': self.strawberry_inputs[
                to_pascal_case_from_str(unique_type_name(root_name, "FilterInput", root_node))
            ],
            'MutationInput': self.strawberry_inputs[
                to_pascal_case_from_str(unique_type_name(root_name, "MutationInput", root_node))
            ]
        }

# Global registry instance
type_registry = TypeRegistry()