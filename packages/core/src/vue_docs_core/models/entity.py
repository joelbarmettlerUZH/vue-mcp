"""API entity models."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    LIFECYCLE_HOOK = "lifecycle_hook"
    COMPOSABLE = "composable"
    DIRECTIVE = "directive"
    COMPONENT = "component"
    COMPILER_MACRO = "compiler_macro"
    GLOBAL_API = "global_api"
    OPTION = "option"
    INSTANCE_METHOD = "instance_method"
    INSTANCE_PROPERTY = "instance_property"
    STORE = "store"
    MIDDLEWARE = "middleware"
    UTILITY = "utility"
    NAVIGATION_GUARD = "navigation_guard"
    OTHER = "other"


class ApiEntity(BaseModel):
    name: Annotated[str, Field(description="The API entity name")]
    source: Annotated[str, Field(description="Source framework identifier")] = "vue"
    entity_type: Annotated[EntityType, Field(description="Classification of the entity type")] = (
        EntityType.OTHER
    )
    page_path: Annotated[
        str, Field(description="Path to the documentation page defining this entity")
    ] = ""
    section: Annotated[str, Field(description="Section heading where this entity is defined")] = ""
    related: Annotated[
        list[str], Field(description="Names of related API entities", default_factory=list)
    ]


class EntityIndex(BaseModel):
    """Maps API entity names to their metadata and chunk references."""

    entities: Annotated[
        dict[str, ApiEntity],
        Field(description="Map of entity name to entity metadata", default_factory=dict),
    ]
    entity_to_chunks: Annotated[
        dict[str, list[str]],
        Field(
            description="Map of entity name to list of chunk IDs referencing it",
            default_factory=dict,
        ),
    ]
