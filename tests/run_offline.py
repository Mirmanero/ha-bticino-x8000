"""Run unit tests outside HA's integration package using a temporary test folder.

Usage from outside the repository: python path/to/tests/run_offline.py
Requires pytest. Does not install or connect to Home Assistant.
"""
import pathlib
import tempfile

import pytest

root = pathlib.Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="x8000-offline-tests-") as directory:
    target = pathlib.Path(directory)
    for name in ("test_cloud.py", "test_resume_automatic.py", "test_read_program.py", "test_create_program.py", "test_program_manager.py", "test_program_api.py"):
        source = (root / "tests" / name).read_text(encoding="utf-8")
        # Keep source lookup anchored to the checkout when staging test modules.
        source = source.replace("pathlib.Path(__file__).resolve().parent.parent",
                                "pathlib.Path(" + repr(str(root)) + ")")
        (target / name).write_text(source, encoding="utf-8")
    raise SystemExit(pytest.main([str(target), "--import-mode=importlib", "-q"]))
