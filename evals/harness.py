"""Authoring eval harness for A2UI golden fixtures."""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

from uirizz_plugin.validate import AdmissionError, admit_jsonl

_EXPRESS_MODULES = (
    "uirizz_plugin.express",
    "a2ui_agent_sdk",
    "a2ui_agent_sdk.express",
    "a2ui_agent_sdk.inference",
)


def _display(path: Path, fixtures_dir: Path) -> str:
    try:
        return path.relative_to(fixtures_dir).as_posix()
    except ValueError:
        return path.name


def _load_expected(fixtures_dir: Path) -> dict[str, str]:
    candidates = (
        fixtures_dir.parent / "expected" / "bad.json",
        fixtures_dir / "expected" / "bad.json",
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        raw = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("expected bad.json must contain an object")
        return {str(name): str(code) for name, code in raw.items()}
    raise FileNotFoundError("expected/bad.json was not found")


def _load_express_compiler() -> Callable[..., Any] | None:
    for module_name in _EXPRESS_MODULES:
        try:
            if importlib.util.find_spec(module_name) is None:
                continue
            module = importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError, ValueError):
            continue
        compiler = getattr(module, "compile_express", None)
        if callable(compiler):
            return compiler
    return None


def _call_compiler(compiler: Callable[..., Any], source: str) -> Any:
    try:
        return compiler(source)
    except TypeError as first_error:
        for keyword in ("text", "source"):
            try:
                return compiler(**{keyword: source})
            except TypeError:
                continue
        raise first_error


def _to_jsonl(value: Any) -> str:
    to_jsonl = getattr(value, "to_jsonl", None)
    if callable(to_jsonl):
        value = to_jsonl()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("jsonl", "output", "text", "messages", "envelopes"):
            if key in value:
                return _to_jsonl(value[key])
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        lines = [
            item if isinstance(item, str) else json.dumps(item)
            for item in value
        ]
        return "\n".join(lines)
    raise TypeError(f"compiler returned unsupported type {type(value).__name__}")


def _admit_fixture(path: Path) -> None:
    admit_jsonl(path.read_text(encoding="utf-8"))


def run_authoring_evals(fixtures_dir: Path | str) -> dict[str, Any]:
    fixtures = Path(fixtures_dir)
    failed: list[dict[str, Any]] = []
    good_passed = 0
    bad_passed = 0

    try:
        expected = _load_expected(fixtures)
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "good_passed": 0,
            "bad_passed": 0,
            "failed": [
                {
                    "fixture": "expected/bad.json",
                    "reason": f"could not load expected codes: {exc}",
                }
            ],
        }

    good_dir = fixtures / "good"
    if good_dir.is_dir():
        for path in sorted(good_dir.glob("*.jsonl")):
            try:
                _admit_fixture(path)
            except AdmissionError as exc:
                failed.append(
                    {
                        "fixture": _display(path, fixtures),
                        "expected": "admitted",
                        "actual": exc.code,
                        "reason": exc.error,
                    }
                )
            except Exception as exc:
                failed.append(
                    {
                        "fixture": _display(path, fixtures),
                        "expected": "admitted",
                        "actual": type(exc).__name__,
                        "reason": str(exc),
                    }
                )
            else:
                good_passed += 1

        compiler = _load_express_compiler()
        if compiler is not None:
            for path in sorted(good_dir.glob("*.express")):
                try:
                    source = path.read_text(encoding="utf-8")
                    admit_jsonl(_to_jsonl(_call_compiler(compiler, source)))
                except AdmissionError as exc:
                    failed.append(
                        {
                            "fixture": _display(path, fixtures),
                            "expected": "admitted",
                            "actual": exc.code,
                            "reason": exc.error,
                        }
                    )
                except Exception as exc:
                    failed.append(
                        {
                            "fixture": _display(path, fixtures),
                            "expected": "admitted",
                            "actual": type(exc).__name__,
                            "reason": str(exc),
                        }
                    )
                else:
                    good_passed += 1

    bad_dir = fixtures / "bad"
    if bad_dir.is_dir():
        for path in sorted(bad_dir.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            expected_code = expected.get(name)
            if expected_code is None:
                failed.append(
                    {
                        "fixture": _display(path, fixtures),
                        "expected": "code in expected/bad.json",
                        "actual": None,
                        "reason": "no expected rejection code was listed",
                    }
                )
                continue
            try:
                _admit_fixture(path)
            except AdmissionError as exc:
                if exc.code == expected_code:
                    bad_passed += 1
                else:
                    failed.append(
                        {
                            "fixture": _display(path, fixtures),
                            "expected": expected_code,
                            "actual": exc.code,
                            "reason": exc.error,
                        }
                    )
            except Exception as exc:
                failed.append(
                    {
                        "fixture": _display(path, fixtures),
                        "expected": expected_code,
                        "actual": type(exc).__name__,
                        "reason": str(exc),
                    }
                )
            else:
                failed.append(
                    {
                        "fixture": _display(path, fixtures),
                        "expected": expected_code,
                        "actual": "admitted",
                        "reason": "fixture was admitted but should have been rejected",
                    }
                )

    ok = not failed and good_passed >= 1 and bad_passed >= 2
    return {
        "ok": ok,
        "good_passed": good_passed,
        "bad_passed": bad_passed,
        "failed": failed,
    }
