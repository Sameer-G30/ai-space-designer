"""Independent deterministic design auditing."""

# audit_design is the public Phase 3 critic entry point.
from spacedesigner.critic.deterministic import audit_design

# Expose only the independent audit function.
__all__ = ["audit_design"]
