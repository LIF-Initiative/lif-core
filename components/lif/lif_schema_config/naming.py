"""
Naming conventions for LIF schema and GraphQL.

This centralizes naming logic used across:
- openapi_to_graphql/type_factory.py (root_name[0].lower() + root_name[1:])
- openapi_schema_parser/core.py (to_camel_case)
- string_utils.py (various case conversions)

Conventions:
- Schema entity names: PascalCase (Person, Course, Organization)
- GraphQL query names: camelCase (person, course, organization)
- GraphQL mutation names: camelCase with verb prefix (updatePerson, createCourse)
- MongoDB document keys: PascalCase (Person, Course)
- Python attribute names: snake_case (person_id, course_name)
"""

import re
from typing import Optional


def to_graphql_query_name(schema_name: str) -> str:
    """
    Convert schema entity name to GraphQL query field name.

    Args:
        schema_name: PascalCase entity name (e.g., "Person", "Course")

    Returns:
        camelCase query name (e.g., "person", "course")

    Example:
        >>> to_graphql_query_name("Person")
        'person'
        >>> to_graphql_query_name("CourseLearningExperience")
        'courseLearningExperience'
    """
    if not schema_name:
        return schema_name
    return schema_name[0].lower() + schema_name[1:]


def to_schema_name(graphql_name: str) -> str:
    """
    Convert GraphQL query name back to schema entity name.

    Args:
        graphql_name: camelCase query name (e.g., "person", "course")

    Returns:
        PascalCase entity name (e.g., "Person", "Course")

    Example:
        >>> to_schema_name("person")
        'Person'
        >>> to_schema_name("courseLearningExperience")
        'CourseLearningExperience'
    """
    if not graphql_name:
        return graphql_name
    return graphql_name[0].upper() + graphql_name[1:]


def to_mutation_name(schema_name: str, action: str = "update") -> str:
    """
    Generate GraphQL mutation name for a schema entity.

    Args:
        schema_name: PascalCase entity name (e.g., "Person")
        action: Mutation action verb (e.g., "update", "create", "delete")

    Returns:
        Mutation name (e.g., "updatePerson", "createPerson")

    Example:
        >>> to_mutation_name("Person", "update")
        'updatePerson'
        >>> to_mutation_name("Course", "create")
        'createCourse'
    """
    return f"{action}{schema_name}"


def to_camel_case(s: str) -> str:
    """
    Convert a string to camelCase.

    Handles snake_case, kebab-case, and space-separated strings.

    Args:
        s: Input string

    Returns:
        camelCase string

    Example:
        >>> to_camel_case("hello_world")
        'helloWorld'
        >>> to_camel_case("hello-world")
        'helloWorld'
    """
    s = re.sub(r"([_\-\s]+)([a-zA-Z])", lambda m: m.group(2).upper(), s)
    if not s:
        return s
    return s[0].lower() + s[1:]


def to_pascal_case(*parts: str) -> str:
    """
    Convert parts to PascalCase and join them.

    Args:
        *parts: String parts to join

    Returns:
        PascalCase string

    Example:
        >>> to_pascal_case("person", "identifier", "enum")
        'PersonIdentifierEnum'
    """
    result = []
    for part in parts:
        if part:
            result.append(part[0].upper() + part[1:])
    return "".join(result)


def to_snake_case(s: str) -> str:
    """
    Convert a string to snake_case.

    Args:
        s: Input string (PascalCase or camelCase)

    Returns:
        snake_case string

    Example:
        >>> to_snake_case("PersonIdentifier")
        'person_identifier'
        >>> to_snake_case("personIdentifier")
        'person_identifier'
    """
    # Insert underscore before uppercase letters (except at start)
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", s)
    return s.lower()


def safe_identifier(name: str) -> str:
    """
    Convert a name to a safe Python identifier.

    Replaces non-alphanumeric characters with underscores and ensures
    the result is a valid Python identifier.

    Args:
        name: Original name

    Returns:
        Safe Python identifier

    Example:
        >>> safe_identifier("x-queryable")
        'x_queryable'
        >>> safe_identifier("123field")
        '_123field'
    """
    # Replace non-alphanumeric with underscore
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # Ensure doesn't start with digit
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe


def normalize_identifier_type(raw_type: str) -> str:
    """
    Normalize an identifier type string to enum format.

    Used by adapters to convert identifier types to a consistent format.

    Args:
        raw_type: Raw identifier type string

    Returns:
        Normalized identifier type (uppercase with underscores)

    Example:
        >>> normalize_identifier_type("School-assigned number")
        'SCHOOL_ASSIGNED_NUMBER'
        >>> normalize_identifier_type("INSTITUTION_ASSIGNED_NUMBER")
        'INSTITUTION_ASSIGNED_NUMBER'
    """
    return re.sub(r"[^A-Za-z0-9]+", "_", raw_type).upper()
