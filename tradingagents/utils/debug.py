from __future__ import annotations

"""Debug utility module for controlling debug mode globally."""

_debug_enabled = False


def set_debug(enabled: bool) -> None:
    """Set global debug mode."""
    global _debug_enabled
    _debug_enabled = enabled


def is_debug() -> bool:
    """Check if debug mode is enabled."""
    return _debug_enabled


def handle_exception(e: Exception, logger=None) -> None:
    """Handle exception based on debug mode.
    
    Args:
        e: The exception to handle
        logger: Optional logger instance. If None, prints to stderr.
    """
    if is_debug():
        import traceback
        traceback.print_exc()
    else:
        if logger:
            logger.error(str(e))
        else:
            print(f"Error: {e}", file=sys.stderr)


import sys