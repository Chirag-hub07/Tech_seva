"""Pytest test configuration and fixtures for ExacerbAlert Backend."""

import os
import pytest
from fastapi.testclient import TestClient

# Set testing environment before importing app
os.environ["ENVIRONMENT"] = "testing"

from backend.app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provide a TestClient instance for API integration tests."""
    with TestClient(app) as test_client:
        yield test_client
