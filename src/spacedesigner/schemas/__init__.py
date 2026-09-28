"""Public Pydantic contracts for the PhotoSpace foundation."""

# Catalog item and its dimensions.
from spacedesigner.schemas.catalog import CatalogDimensions, CatalogItem

# Candidate design record.
from spacedesigner.schemas.design import Design

# Requirement record and its objective weights.
from spacedesigner.schemas.requirement import ObjectiveWeights, Requirement

# Scene graph and the nested types from blueprint section 11.
from spacedesigner.schemas.scene import Confidence, Opening, RoomDimensions, SceneGraph, SceneObject

# Optimizer decision trace and its nested types.
from spacedesigner.schemas.trace import (
    BindingConstraint,
    ObjectiveTerms,
    OptimizerTrace,
    RejectedItem,
)

# Append-only design version.
from spacedesigner.schemas.version import DesignVersion

# Names re-exported when a caller imports the schemas package.
__all__ = [
    "BindingConstraint",
    "CatalogDimensions",
    "CatalogItem",
    "Confidence",
    "Design",
    "DesignVersion",
    "ObjectiveTerms",
    "ObjectiveWeights",
    "Opening",
    "OptimizerTrace",
    "RejectedItem",
    "Requirement",
    "RoomDimensions",
    "SceneGraph",
    "SceneObject",
]
