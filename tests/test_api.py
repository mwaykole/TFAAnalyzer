"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.api.server import app


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_health_check(self, client):
        """Test health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_check_structure(self, client):
        """Test health response structure."""
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert "cache_available" in data
        assert "rp_configured" in data
        assert "llm_providers" in data


class TestRootEndpoint:
    """Tests for root endpoint."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_root_returns_info(self, client):
        """Test root endpoint returns service info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "TFA" in data["name"]


class TestAPISchemas:
    """Tests for API request/response schemas."""

    def test_analyze_request_validation(self):
        """Test AnalyzeRequest validation."""
        from src.api.schemas import AnalyzeRequest
        
        # Valid request
        req = AnalyzeRequest(
            launch_id="9657",
            component="Model_server",
        )
        assert req.launch_id == "9657"
        assert req.component == "Model_server"
        assert req.push_to_rp is False
        assert req.use_cache is True

    def test_analyze_request_defaults(self):
        """Test AnalyzeRequest default values."""
        from src.api.schemas import AnalyzeRequest
        
        req = AnalyzeRequest(
            launch_id="123",
            component="test",
        )
        assert req.test_id is None
        assert req.push_to_rp is False
        assert req.use_cache is True
        assert req.use_llm is True
        assert req.provider == "claude-cli"

    def test_investigate_request_validation(self):
        """Test InvestigateRequest validation."""
        from src.api.schemas import InvestigateRequest
        
        req = InvestigateRequest(
            launch_id="9657",
            component="Model_server",
            push_to_rp=True,
        )
        assert req.launch_id == "9657"
        assert req.push_to_rp is True

    def test_health_response(self):
        """Test HealthResponse schema."""
        from src.api.schemas import HealthResponse
        
        resp = HealthResponse(
            status="healthy",
            version="2.0.0",
            cache_available=True,
            rp_configured=True,
            llm_providers=["claude-cli", "anthropic"],
        )
        assert resp.status == "healthy"
        assert len(resp.llm_providers) == 2

    def test_error_response(self):
        """Test ErrorResponse schema."""
        from src.api.schemas import ErrorResponse
        
        resp = ErrorResponse(
            error="Not found",
            status_code=404,
            detail="Resource not found",
        )
        assert resp.error == "Not found"
        assert resp.status_code == 404


class TestAnalyzeEndpoint:
    """Tests for analyze endpoint."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_analyze_missing_required_fields(self, client):
        """Test analyze endpoint requires launch_id and component."""
        response = client.post(
            "/api/v1/analyze",
            json={},
        )
        assert response.status_code == 422  # Validation error

    def test_analyze_invalid_json(self, client):
        """Test analyze endpoint handles invalid JSON."""
        response = client.post(
            "/api/v1/analyze",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestInvestigateEndpoint:
    """Tests for investigate endpoint."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_investigate_missing_required_fields(self, client):
        """Test investigate endpoint requires launch_id and component."""
        response = client.post(
            "/api/v1/investigate",
            json={},
        )
        assert response.status_code == 422

    def test_investigate_validation(self, client):
        """Test investigate endpoint validates input."""
        response = client.post(
            "/api/v1/investigate",
            json={"launch_id": "123"},  # Missing component
        )
        assert response.status_code == 422
