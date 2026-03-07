"""API entity models."""

from enum import Enum

from pydantic import BaseModel


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
    OTHER = "other"


class ApiEntity(BaseModel):
    name: str
    entity_type: EntityType = EntityType.OTHER
    page_path: str = ""
    section: str = ""
    related: list[str] = []


class EntityIndex(BaseModel):
    """Maps API entity names to their metadata and chunk references."""

    entities: dict[str, ApiEntity] = {}
    entity_to_chunks: dict[str, list[str]] = {}
