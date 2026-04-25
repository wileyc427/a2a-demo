"""
Re-exports ObservableA2AClient from the tracentic SDK.

The client implementation lives in tracentic.integrations.a2a — this module
exists only for backwards compatibility with any code that imports from shared.
"""
from tracentic.integrations.a2a import ObservableA2AClient

# Backwards-compatible alias
A2AAgentClient = ObservableA2AClient

__all__ = ["ObservableA2AClient", "A2AAgentClient"]
