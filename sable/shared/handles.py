"""Handle normalization utilities."""


def strip_handle(handle: str) -> str:
    """Strip leading '@' from a handle string.

    >>> strip_handle("@alice")
    'alice'
    >>> strip_handle("alice")
    'alice'
    """
    return handle.lstrip("@")


def normalize_handle(handle: str) -> str:
    """Strip '@' and lowercase for comparison/lookup.

    >>> normalize_handle("@Alice")
    'alice'
    >>> normalize_handle("ALICE")
    'alice'
    """
    return handle.lstrip("@").lower()


def ensure_handle_prefix(handle: str) -> str:
    """Ensure handle starts with '@' (pulse.db contract).

    >>> ensure_handle_prefix("alice")
    '@alice'
    >>> ensure_handle_prefix("@alice")
    '@alice'
    """
    return handle if handle.startswith("@") else f"@{handle}"
