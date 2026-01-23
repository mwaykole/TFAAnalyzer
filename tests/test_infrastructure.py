"""Tests for infrastructure components."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.cache import MemoryCache
from src.infrastructure.llm import LLMFactory


class TestMemoryCache:
    """Tests for MemoryCache implementation."""

    @pytest.fixture
    def cache(self):
        """Create a memory cache instance."""
        return MemoryCache(default_ttl=60)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache):
        """Test get returns None for missing key."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, cache):
        """Test exists method."""
        await cache.set("key1", "value1")
        assert await cache.exists("key1") is True
        assert await cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_delete(self, cache):
        """Test delete method."""
        await cache.set("key1", "value1")
        await cache.delete("key1")
        assert await cache.exists("key1") is False

    @pytest.mark.asyncio
    async def test_clear_all(self, cache):
        """Test clear_all method."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        count = await cache.clear_all()
        assert count == 2
        assert await cache.exists("key1") is False
        assert await cache.exists("key2") is False

    @pytest.mark.asyncio
    async def test_clear_pattern(self, cache):
        """Test clear_pattern method."""
        await cache.set("prefix:key1", "value1")
        await cache.set("prefix:key2", "value2")
        await cache.set("other:key3", "value3")
        count = await cache.clear_pattern("prefix:*")
        assert count == 2
        assert await cache.exists("other:key3") is True

    def test_size(self, cache):
        """Test size method."""
        assert cache.size() == 0

    @pytest.mark.asyncio
    async def test_complex_values(self, cache):
        """Test storing complex values."""
        data = {
            "classification": "Product Bug",
            "confidence": 0.85,
            "nested": {"key": "value"},
        }
        await cache.set("complex", data)
        result = await cache.get("complex")
        assert result == data

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, cache):
        """Test that expired entries are not returned."""
        # Set with 0 TTL (immediate expiry)
        import time
        cache._cache["expired_key"] = ("value", time.time() - 1)
        result = await cache.get("expired_key")
        assert result is None


class TestLLMFactory:
    """Tests for LLMFactory."""

    def test_available_providers(self):
        """Test getting available providers."""
        providers = LLMFactory.available_providers()
        assert isinstance(providers, list)
        assert "anthropic" in providers
        assert "groq" in providers
        assert "ollama" in providers
        assert "claude-cli" in providers

    def test_register_provider(self):
        """Test registering a custom provider."""
        mock_provider_class = MagicMock()
        LLMFactory.register("custom", mock_provider_class)
        assert "custom" in LLMFactory.available_providers()
        # Cleanup
        del LLMFactory._providers["custom"]

    def test_create_unknown_provider_raises(self):
        """Test that creating unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown"):
            LLMFactory.create("unknown_provider")

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_create_anthropic_provider(self):
        """Test creating anthropic provider."""
        provider = LLMFactory.create("anthropic")
        assert provider.provider_name == "anthropic"

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    def test_create_groq_provider(self):
        """Test creating groq provider."""
        provider = LLMFactory.create("groq")
        assert provider.provider_name == "groq"

    def test_create_ollama_provider(self):
        """Test creating ollama provider."""
        provider = LLMFactory.create("ollama")
        assert provider.provider_name == "ollama"

    def test_create_claude_cli_provider(self):
        """Test creating claude-cli provider."""
        provider = LLMFactory.create("claude-cli")
        assert provider.provider_name == "claude-cli"


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    @pytest.fixture
    def cache(self):
        return MemoryCache()

    @pytest.mark.asyncio
    async def test_different_keys_for_different_data(self, cache):
        """Test that different data produces different keys."""
        await cache.set("failure:123:abc", "result1")
        await cache.set("failure:456:def", "result2")
        
        assert await cache.get("failure:123:abc") == "result1"
        assert await cache.get("failure:456:def") == "result2"

    @pytest.mark.asyncio
    async def test_key_with_special_characters(self, cache):
        """Test keys with special characters."""
        key = "failure:test_with_special!@#$%"
        await cache.set(key, "value")
        assert await cache.get(key) == "value"


class TestLLMProviderInterface:
    """Tests for LLM provider interface compliance."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_anthropic_has_required_methods(self):
        """Test AnthropicAdapter implements required interface."""
        from src.infrastructure.llm import AnthropicAdapter
        
        provider = AnthropicAdapter(api_key="test-key")
        assert hasattr(provider, "provider_name")
        assert hasattr(provider, "model_name")
        assert hasattr(provider, "analyze")
        assert hasattr(provider, "is_available")
        assert hasattr(provider, "think")
        assert hasattr(provider, "critique")
        assert hasattr(provider, "refine")

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    def test_groq_has_required_methods(self):
        """Test GroqAdapter implements required interface."""
        from src.infrastructure.llm import GroqAdapter
        
        provider = GroqAdapter(api_key="test-key")
        assert hasattr(provider, "provider_name")
        assert hasattr(provider, "model_name")
        assert hasattr(provider, "analyze")
        assert hasattr(provider, "is_available")

    def test_ollama_has_required_methods(self):
        """Test OllamaAdapter implements required interface."""
        from src.infrastructure.llm import OllamaAdapter
        
        provider = OllamaAdapter()
        assert hasattr(provider, "provider_name")
        assert hasattr(provider, "model_name")
        assert hasattr(provider, "analyze")
        assert hasattr(provider, "is_available")

    def test_claude_cli_has_required_methods(self):
        """Test ClaudeAdapter implements required interface."""
        from src.infrastructure.llm import ClaudeAdapter
        
        provider = ClaudeAdapter()
        assert hasattr(provider, "provider_name")
        assert hasattr(provider, "model_name")
        assert hasattr(provider, "analyze")
        assert hasattr(provider, "is_available")


class TestMemoryCacheInterface:
    """Tests for MemoryCache interface compliance."""

    def test_implements_cache_repository(self):
        """Test that MemoryCache implements CacheRepository interface."""
        from src.domain.interfaces.repositories import CacheRepository
        
        cache = MemoryCache()
        assert isinstance(cache, CacheRepository)
