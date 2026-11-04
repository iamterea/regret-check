from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache


@pytest.fixture
def memory_cache():
    """An in-memory cache no other test can see."""
    return LocMemCache(f"test-{uuid4()}", {})


@pytest.fixture(autouse=True)
def clear_default_cache():
    cache.clear()
    yield
    cache.clear()
