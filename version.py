"""Tool identity and version - neutral (no country/standard content).

The regulation editions a standard encodes live in ``standards.py`` (they are
national); the tool name and version here are universal. ``provenance`` combines
them with the active standard's edition stamp so every output is traceable.
"""

from __future__ import annotations

TOOL_NAME = "Earthwork Studio GH"
__version__ = "0.9.4"


def tool_stamp() -> str:
    """Short, neutral tool identifier, e.g. ``Earthwork Studio GH v0.7.0``."""

    return "{} v{}".format(TOOL_NAME, __version__)


def provenance(standard=None) -> str:
    """A one-line provenance stamp: tool version + the standard's edition.

    ``standard`` is an active ``Standard`` (or anything exposing
    ``edition_stamp()``); when omitted only the tool stamp is returned.
    """

    if standard is None:
        return tool_stamp()
    edition = ""
    getter = getattr(standard, "edition_stamp", None)
    if callable(getter):
        edition = getter()
    return "{} - {}".format(tool_stamp(), edition) if edition else tool_stamp()
