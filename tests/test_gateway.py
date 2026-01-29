"""Tests for Gateway API."""

import pytest
from fastapi.testclient import TestClient

from src.gateway.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_healthz(client):
    """Test health endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_list_models(client):
    """Test listing models."""
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0


def test_list_voices(client):
    """Test listing voices."""
    response = client.get("/v1/voices")
    assert response.status_code == 200
    data = response.json()
    assert "voices" in data
    assert len(data["voices"]) > 0
