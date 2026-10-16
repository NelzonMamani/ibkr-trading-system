"""Copied only to the isolated observation child's PYTHONPATH; no acquisition."""
import os
try:
    import yfinance.cache as cache
    location = os.environ['PR1108_YFINANCE_CACHE']
    if not os.path.isabs(location):
        raise ValueError('Cache location must be absolute')
    cache.set_cache_location(location)
    managers = [getattr(cache, name) for name in ('_TzDBManager', '_CookieDBManager')]
    if hasattr(cache, '_ISINDBManager'):
        managers.append(cache._ISINDBManager)
    configured = [os.path.normcase(os.path.abspath(manager.get_location())) for manager in managers]
    if any(path != os.path.normcase(os.path.abspath(location)) for path in configured):
        raise RuntimeError('Provider cache location was not applied')
    cache._readonly_cache_locations = configured
    cache._readonly_cache_isolated = True
except BaseException:
    # Python normally prints and ignores sitecustomize exceptions. Fail closed.
    os._exit(78)
