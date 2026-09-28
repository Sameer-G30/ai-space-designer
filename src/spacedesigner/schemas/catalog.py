"""Furniture catalog item from blueprint section 38."""

# Field and field_validator express price, size, and embedding rules.
from pydantic import Field, field_validator

# SchemaModel rejects keys that are not part of this contract.
from spacedesigner.schemas.base import SchemaModel


# Physical size of one catalog item, in metres.
class CatalogDimensions(SchemaModel):
    # Item length in metres.
    length: float = Field(gt=0)
    # Item width in metres.
    width: float = Field(gt=0)
    # Item height in metres.
    height: float = Field(gt=0)


# One furniture item the recommender can select.
class CatalogItem(SchemaModel):
    # Identifier for this catalog item.
    item_id: str = Field(min_length=1)
    # Taxonomy category, such as "desk".
    category: str = Field(min_length=1)
    # Real dimensions of the item.
    dims: CatalogDimensions
    # Price in Indian rupees.
    price: float = Field(ge=0)
    # Style labels used for similarity scoring.
    style_tags: list[str]
    # Primary material used for the sustainability score.
    material: str = Field(min_length=1)
    # Optional embedding stored once a model is chosen in a later phase.
    embedding: list[float] | None = None

    # Reject blank style tags.
    @field_validator("style_tags")
    @classmethod
    def style_tags_must_be_non_empty(cls, value: list[str]) -> list[str]:
        # Inspect each style label.
        for tag in value:
            # A blank tag cannot be matched.
            if not tag.strip():
                # Fail validation with a stable message.
                raise ValueError("style tags must be non-empty strings")
        # Return the list unchanged when every tag has text.
        return value

    # Reject an embedding that was provided but contains no values.
    @field_validator("embedding")
    @classmethod
    def embedding_must_contain_values(cls, value: list[float] | None) -> list[float] | None:
        # None means this item has no embedding yet.
        if value is None:
            # Keep the field empty.
            return value
        # An empty list is not a usable vector.
        if len(value) == 0:
            # Fail validation with a stable message.
            raise ValueError("embedding must be omitted or contain values")
        # Keep a vector that has at least one component.
        return value
