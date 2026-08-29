"""Backward-compatible wrapper for the safe invalid-job cleanup command."""

from .cleanup_invalid import main


if __name__ == "__main__":
    main()
