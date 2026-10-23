"""
backend/tests/test_app_config.py
================================
Unit tests for AppSettings validation, origin parsing, and security limits.
"""
import pytest
from pydantic import ValidationError

from backend.app.config import AppSettings


def test_default_app_settings():
    settings = AppSettings()
    assert settings.max_message_characters == 2000
    assert settings.llm_provider == "openai"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.openai_timeout_seconds == 30.0
    assert settings.openai_max_retries == 2
    assert settings.openai_max_output_tokens == 1024
    assert settings.groq_timeout_seconds == 30.0
    assert settings.groq_max_retries == 2
    assert settings.groq_max_output_tokens == 1024
    assert "https://eurekasolutions.in" in settings.allowed_origins
    assert settings.docs_enabled is True  # development default


def test_origins_parsing_and_normalization():
    # Comma-separated string with mixed trailing slashes
    settings = AppSettings(
        allowed_origins="http://localhost:3000/, https://eurekasolutions.in/"
    )
    assert settings.allowed_origins == [
        "http://localhost:3000",
        "https://eurekasolutions.in",
    ]


def test_invalid_origin_rejected():
    with pytest.raises(ValidationError):
        AppSettings(allowed_origins="not-a-valid-url")

    with pytest.raises(ValidationError):
        AppSettings(allowed_origins="javascript:alert(1)")


def test_message_length_bounds():
    # Valid
    s = AppSettings(max_message_characters=1500)
    assert s.max_message_characters == 1500

    # Negative or 0
    with pytest.raises(ValidationError):
        AppSettings(max_message_characters=0)

    # Above 2000
    with pytest.raises(ValidationError):
        AppSettings(max_message_characters=2500)


def test_trusted_proxies_parsing():
    settings = AppSettings(trusted_proxies="127.0.0.1, 10.0.0.1")
    assert settings.trusted_proxies == ["127.0.0.1", "10.0.0.1"]


def test_docs_enabled_production_override():
    settings = AppSettings(app_env="production")
    assert settings.docs_enabled is False

    # Explicit override in production
    settings_forced = AppSettings(app_env="production", enable_docs=True)
    assert settings_forced.docs_enabled is True
