"""
Schema factory for building the Strawberry GraphQL schema from dynamic models.

This module is side-effect free: given a root node name and a backend,
it builds all Pydantic models, Strawberry types/inputs, and returns a Schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Any, Protocol
import os

import strawberry
from strawberry.experimental.pydantic import input as pyd_input
from strawberry.experimental.pydantic import type as pyd_type
from strawberry.types import Info
from strawberry.experimental.pydantic.exceptions import UnregisteredTypeException
from strawberry.scalars import JSON

from lif.datatypes.schema import SchemaField
from lif.dynamic_models.core import build_filter_models, build_full_models, build_mutation_models
from lif.openapi_schema.core import get_schema_fields
from lif.graphql.core import Backend, extract_selected_fields, pydantic_inputs_to_dict
from lif.graphql.utils import to_pascal_case_from_str, unique_type_name
from lif.utils.validation import to_bool





class StrawberryType(Protocol):
    """Mixin for Strawberry types from Pydantic models."""

    @classmethod
    def from_pydantic(cls, data): ...


RootType: StrawberryType | None = None
FilterInput: StrawberryType | None = None
MutationInput: StrawberryType | None = None


def build_schema(*, schema_fields: List[SchemaField], root_node: str, backend: Backend) -> strawberry.Schema:
    """Build a Strawberry GraphQL schema for the given root node and backend.

    Args:
        schema_fields (List[SchemaField]): List of schema fields from OpenAPI/JSON Schema.
        root_node (str): The root node name (e.g., "Person").
        backend (Backend): The backend implementation for queries and mutations.
    Returns:
        strawberry.Schema: The constructed GraphQL schema.
    """
    # Build dynamic Pydantic models
    filter_models = build_filter_models(schema_fields, allow_extra=False, all_optional=False)
    mutation_models = build_mutation_models(schema_fields, allow_extra=False, all_optional=True)
    full_models = build_full_models(schema_fields, allow_extra=False, all_optional=True)

    root_name = to_pascal_case_from_str(root_node)

    # Build dynamic Strawberry types and inputs
    strawberry_types: Dict[str, type[StrawberryType]] = {}
    strawberry_inputs: Dict[str, type[StrawberryType]] = {}

    # ===== Output (Query) Types =====
    for name, model in full_models.items():
        if "wrapper" in name.lower():
            continue  # Skip wrapper types
        tname = to_pascal_case_from_str(name)
        if tname not in strawberry_types:
            strawberry_types[tname] = pyd_type(model=model, all_fields=True)(
                type(tname, (), {})
            )

    # ===== Filter (Input) Types =====
    for name, model in filter_models.items():
        if "wrapper" in name.lower():
            continue  # Skip wrapper types
        iname = unique_type_name(name, "FilterInput", root_node)
        iname = to_pascal_case_from_str(iname)
        if iname not in strawberry_inputs:
            strawberry_inputs[iname] = pyd_input(model=model, all_fields=True)(
                type(iname, (), {})
            )

    # ===== Mutation (Input) Types =====
    for name, model in mutation_models.items():
        if "wrapper" in name.lower():
            continue  # Skip wrapper types
        iname = unique_type_name(name, "MutationInput", root_node)
        iname = to_pascal_case_from_str(iname)
        if iname not in strawberry_inputs:
            strawberry_inputs[iname] = pyd_input(model=model, all_fields=True)(
                type(iname, (), {})
            )


    global RootType, FilterInput, MutationInput
    RootType = strawberry_types[root_name]
    FilterInput = strawberry_inputs[
        to_pascal_case_from_str(unique_type_name(root_name, "FilterInput", root_node))
    ]
    MutationInput = strawberry_inputs[
        to_pascal_case_from_str(unique_type_name(root_name, "MutationInput", root_node))
    ]

    # ===== Strawberry Query & Mutation Roots =====
    @strawberry.type
    class Query:
        @strawberry.field
        async def persons(
            self,
            info: Info,
            filter: FilterInput  # type: ignore[type-arg]
        ) -> List[RootType]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, _ = pydantic_inputs_to_dict(filter_input=filter)
            persons = await backend.query(filter_dict, selected)
            return [RootType.from_pydantic(full_models[root_node](**p)) for p in persons]

        @strawberry.field
        async def person(
            self,
            info: Info,
            filter: FilterInput  # type: ignore[type-arg]
        ) -> Optional[RootType]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, _ = pydantic_inputs_to_dict(filter_input=filter)
            persons = await backend.query(filter_dict, selected)
            return RootType.from_pydantic(full_models[root_node](**persons[0])) if persons else None


    # ===== Strawberry Schema =====

    schema = strawberry.Schema(
        query=Query,
        # mutation=Mutation,
        types=[*strawberry_types.values(), *strawberry_inputs.values()],
    )

    return schema

def build_schema_old(*, root_node: str, backend: Backend) -> strawberry.Schema:
    # Allow a minimal mode for tests or environments where Pydantic-to-Strawberry registration is undesirable
    minimal_mode = to_bool(os.getenv("LIF_GRAPHQL_DISABLE_PYDANTIC_TYPES", "false"))

    # Build dynamic Pydantic models
    fields = get_schema_fields()
    filter_models = build_filter_models(fields, allow_extra=False, all_optional=False)
    mutation_models = build_mutation_models(fields, allow_extra=False, all_optional=True)
    full_models = build_full_models(fields, allow_extra=False, all_optional=True)

    root_name = to_pascal_case_from_str(root_node)
    lc_root = root_node[:1].lower() + root_node[1:]
    # Prefer the lower-camel-case root key inserted by the dynamic model builder (e.g., "person")
    FullModel = full_models.get(lc_root)
    if FullModel is None:
        # Fallback to the suffixed key (e.g., "PersonType") if present
        FullModel = full_models.get(f"{root_name}Type")
    if FullModel is None:
        raise KeyError(f"Cannot locate FullModel for root '{root_node}' in dynamic models")
    
    # print(f"### filter models: {filter_models}")
    # for k, _ in filter_models.items():
    #     print(f"Filter model: {k}")

    FilterModel = filter_models[f"{root_name}Filter"]
    MutationModel = mutation_models[f"{root_name}Mutation"]
    WrapperModel = full_models[f"{root_name.lower()}_wrapper"]

    # Generate Strawberry output types
    # strawberry_types: Dict[str, type] = {}
    # strawberry_inputs: Dict[str, type] = {}
    StrawberryTypes: Dict[str, type[StrawberryType]] = {}
    StrawberryInputs: Dict[str, type[StrawberryType]] = {}

    if not minimal_mode:
        # ===== Output (Query) Types =====

        for name, model in full_models.items():
            if "wrapper" in name.lower():
                continue  # Skip wrapper types
            tname = to_pascal_case_from_str(name)
            if tname not in StrawberryTypes:
                StrawberryTypes[tname] = pyd_type(model=model, all_fields=True)(
                    type(tname, (), {})
                )

        # ===== Filter (Input) Types =====

        for name, model in filter_models.items():
            if "wrapper" in name.lower():
                continue  # Skip wrapper types
            iname = unique_type_name(name, "FilterInput", root_node)
            iname = to_pascal_case_from_str(iname)
            if iname not in StrawberryInputs:
                StrawberryInputs[iname] = pyd_input(model=model, all_fields=True)(
                    type(iname, (), {})
                )

        # ===== Mutation (Input) Types =====

        for name, model in mutation_models.items():
            if "wrapper" in name.lower():
                continue  # Skip wrapper types
            iname = unique_type_name(name, "MutationInput", root_node)
            iname = to_pascal_case_from_str(iname)
            if iname not in StrawberryInputs:
                StrawberryInputs[iname] = pyd_input(model=model, all_fields=True)(
                    type(iname, (), {})
                )

        RootType = StrawberryTypes[root_name]
        FilterInput = StrawberryInputs[
            to_pascal_case_from_str(unique_type_name(root_name, "FilterInput", root_node))
        ]
        MutationInput = StrawberryInputs[
            to_pascal_case_from_str(unique_type_name(root_name, "MutationInput", root_node))
        ]

    # if not minimal_mode:
    #     # Register full models ensuring nested dependencies are available first
    #     pending = [(name, model) for name, model in full_models.items() if "wrapper" not in name.lower()]
    #     attempts = 0
    #     max_attempts = len(pending) * 2 + 1
    #     while pending and attempts < max_attempts:
    #         attempts += 1
    #         next_round = []
    #         for name, model in pending:
    #             tname = to_pascal_case_from_str(name)
    #             if tname in strawberry_types:
    #                 continue
    #             try:
    #                 strawberry_types[tname] = pyd_type(model=model, all_fields=True)(type(tname, (), {}))
    #             except UnregisteredTypeException:
    #                 next_round.append((name, model))
    #         pending = next_round
    #     if pending:
    #         # If still pending, raise the first error contextually
    #         raise UnregisteredTypeException(pending[0][1])

    #     # Filter inputs
    #     for name, model in filter_models.items():
    #         if "wrapper" in name.lower():
    #             continue
    #         iname = to_pascal_case_from_str(unique_type_name(name, "FilterInput", root_node))
    #         if iname not in strawberry_inputs:
    #             strawberry_inputs[iname] = pyd_input(model=model, all_fields=True)(type(iname, (), {}))

    #     # Mutation inputs
    #     for name, model in mutation_models.items():
    #         if "wrapper" in name.lower():
    #             continue
    #         iname = to_pascal_case_from_str(unique_type_name(name, "MutationInput", root_node))
    #         if iname not in strawberry_inputs:
    #             strawberry_inputs[iname] = pyd_input(model=model, all_fields=True)(type(iname, (), {}))

    # if not minimal_mode:
    #     RootType = strawberry_types[root_name]

    # Resolvers
    @strawberry.type
    class QueryJSON:
        @strawberry.field
        async def persons(self, info: Info, filter: JSON) -> List[JSON]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, _ = pydantic_inputs_to_dict(filter_input=filter)
            persons = await backend.query(filter_dict, selected)
            return persons

        @strawberry.field
        async def person(self, info: Info, filter: JSON) -> Optional[JSON]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, _ = pydantic_inputs_to_dict(filter_input=filter)
            persons = await backend.query(filter_dict, selected)
            return persons[0] if persons else None

    @strawberry.type
    class QueryTyped:
        @strawberry.field
        async def persons(
            self,
            info: Info,
            filter: FilterInput  # type: ignore[type-arg]
        ) -> List[RootType]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, _ = pydantic_inputs_to_dict(filter_input=filter)
            persons = await backend.query(filter_dict, selected)
            return [RootType.from_pydantic(FullModel(**p)) for p in persons]

        @strawberry.field
        async def person(
            self,
            info: Info,
            filter: FilterInput  # type: ignore[type-arg]
        ) -> Optional[RootType]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, _ = pydantic_inputs_to_dict(filter_input=filter)
            persons = await backend.query(filter_dict, selected)
            return RootType.from_pydantic(FullModel(**persons[0])) if persons else None

    Query = QueryJSON if minimal_mode else QueryTyped

    @strawberry.type
    class MutationJSON:
        @strawberry.mutation
        async def update_person(
            self, info: Info, filter: JSON, input_: JSON) -> List[JSON]:  # type: ignore[valid-type]
            selected = extract_selected_fields(info)
            filter_dict, input_dict = pydantic_inputs_to_dict(filter_input=filter, mutation_input=input_)
            persons = await backend.update(filter_dict, input_dict, selected)
            return persons

    @strawberry.type
    class MutationTyped:
        @strawberry.mutation
        async def update_person(
            self,
            info: Info,
            filter: FilterInput,
            input_: MutationInput,
        ) -> List[RootType]:  # runtime type is (FilterInput, MutationInput) -> List[RootType]
            selected = extract_selected_fields(info)
            filter_dict, input_dict = pydantic_inputs_to_dict(filter_input=filter, mutation_input=input_)
            persons = await backend.update(filter_dict, input_dict, selected)
            return [RootType.from_pydantic(FullModel(**p)) for p in persons]

    Mutation = MutationJSON if minimal_mode else MutationTyped

    # TODO: remove this debug output
    # if not minimal_mode:
    #     out_dir = Path(__file__).parent / "_artifacts"
    #     out_dir.mkdir(parents=True, exist_ok=True)
    #     (out_dir / "schema.graphql").write_text(Query.as_str(), encoding="utf-8")

    print(f"### Query: {Query}")

    types_arg = [*StrawberryTypes.values(), *StrawberryInputs.values()] if not minimal_mode else []
    # types_arg = [*strawberry_types.values(), *strawberry_inputs.values()] if not minimal_mode else []
    schema = strawberry.Schema(query=Query, mutation=Mutation, types=types_arg)
    return schema
