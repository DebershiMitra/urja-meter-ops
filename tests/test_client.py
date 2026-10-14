"""Unit tests for UrjaClient and HMAC signature engine."""
import hashlib
import hmac
import pytest
from src.client.urja_client import UrjaClient


def test_hmac_export_signature():
    """Verifies HMAC-SHA256 signature generation against known test vectors."""
    client = UrjaClient()
    secret = "test-secret-key-12345"
    method = "GET"
    path = "/portal/export"
    query = "page=1"

    ts, signature = client.generate_export_signature(method, path, query, secret)
    assert ts.isdigit()
    assert len(signature) == 64  # SHA256 hex string is 64 characters

    # Verify signature independently
    expected_msg = f"{method}\n{path}\n{query}\n{ts}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), expected_msg, hashlib.sha256).hexdigest()
    assert signature == expected_sig


def test_client_headers():
    """Verifies that mandatory SvelteKit CSRF headers are properly set."""
    client = UrjaClient(base_url="https://urja-ops.flockenergy.tech")
    assert client._default_headers["Origin"] == "https://urja-ops.flockenergy.tech"
    assert client._default_headers["Referer"] == "https://urja-ops.flockenergy.tech/login"
