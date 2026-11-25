from uuid import uuid4


def uid() -> str:
    """Return an opaque identifier shared across module schemas."""
    return str(uuid4())
