"""Load the `aigame` build selected by AIGAME_IMPL (default: c_capi).

Every implementation lives in bindings/build/<impl>/ and must expose a module
literally named `aigame`, so only one can be imported per process. The Makefile
runs pytest once per implementation.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1] / "build"
IMPL = os.environ.get("AIGAME_IMPL", "c_capi")


def pytest_report_header(config):
    return f"aigame implementation: {IMPL} ({BUILD / IMPL})"


@pytest.fixture(scope="session")
def aigame():
    path = BUILD / IMPL
    if not path.is_dir():
        pytest.exit(f"no build for {IMPL!r} at {path}; run `make -C bindings {IMPL}`", returncode=2)
    sys.path.insert(0, str(path))
    mod = importlib.import_module("aigame")
    assert Path(mod.__file__).resolve().is_relative_to(path), f"imported wrong aigame: {mod.__file__}"
    mod.init(False)
    return mod
