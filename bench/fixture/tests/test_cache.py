from textkit.cache import LRUCache


def test_keeps_up_to_capacity():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert len(cache) == 2
    assert cache.get("a") == 1


def test_evicts_least_recently_used():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
