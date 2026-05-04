"""Settings / env parsing (CORS, etc.)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.settings import Settings  # noqa: E402


def test_cors_origin_list_comma_separated():
    s = Settings(cors_origins="http://a, http://b ", _env_file=None)
    assert s.cors_origin_list == ["http://a", "http://b"]


def test_cors_origin_list_json_array_string():
    s = Settings(cors_origins='["http://a","http://b"]', _env_file=None)
    assert s.cors_origin_list == ["http://a", "http://b"]


def test_cors_origin_list_empty_falls_back_to_defaults():
    s = Settings(cors_origins="", _env_file=None)
    out = s.cors_origin_list
    assert "http://localhost:3000" in out
    assert len(out) >= 1
