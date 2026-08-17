from __future__ import annotations

import re
from pathlib import Path

FUNCTION_RE = re.compile(r"\b(mac_[a-z0-9_]+)\s*\(")


def _declared_functions(text: str) -> set[str]:
    return set(FUNCTION_RE.findall(text))


def test_cffi_declarations_match_native_headers() -> None:
    """Keep the Python-visible CFFI API synchronized with the native headers."""
    root = Path(__file__).resolve().parents[3]
    cffi_source = root / "libqtile/backend/macos/cffi/build.py"
    native_source = root / "libqtile/backend/macos/src"

    cdef_functions = _declared_functions(cffi_source.read_text())
    header_functions = set()
    for header in native_source.glob("*.h"):
        header_functions.update(_declared_functions(header.read_text()))

    assert cdef_functions == header_functions
