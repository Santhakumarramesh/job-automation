"""services/api_cors.py — parse API_CORS_ORIGINS."""

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def clear_cors_env():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("API_CORS_ORIGINS", None)
        yield


def test_parse_cors_unset(clear_cors_env):
    from services.api_cors import parse_api_cors_origins

    assert parse_api_cors_origins() is None


def test_parse_cors_star(clear_cors_env):
    from services.api_cors import parse_api_cors_origins

    with patch.dict(os.environ, {"API_CORS_ORIGINS": "*"}):
        assert parse_api_cors_origins() == ["*"]


def test_parse_cors_list_trims(clear_cors_env):
    from services.api_cors import parse_api_cors_origins

    with patch.dict(
        os.environ,
        {"API_CORS_ORIGINS": " http://localhost:8501 , https://x.test "},
    ):
        assert parse_api_cors_origins() == ["http://localhost:8501", "https://x.test"]


def test_parse_cors_empty_string(clear_cors_env):
    from services.api_cors import parse_api_cors_origins

    with patch.dict(os.environ, {"API_CORS_ORIGINS": "  ,  , "}):
        assert parse_api_cors_origins() is None
