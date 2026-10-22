"""Copied only to the isolated observation child's PYTHONPATH; no acquisition."""
import os
import time


def probe_stage(stage):
    # Opt-in for the isolated diagnostic child only; normal runtime has no trace.
    target = os.environ.get('PR1108_CACHE_PROBE_TRACE')
    if target:
        row = ('{"stage":"%s","pid":%d,"utc_epoch_ns":%d,"monotonic_ns":%d}\n'
               % (stage, os.getpid(), time.time_ns(), time.monotonic_ns())).encode('ascii')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.write(fd, row) != len(row):
                raise OSError('Incomplete diagnostic stage write')
            os.fsync(fd)
        finally:
            os.close(fd)

try:
    probe_stage('sitecustomize_enter')
    probe_stage('yfinance_cache_import_begin')
    import yfinance.cache as cache
    probe_stage('yfinance_cache_import_complete')
    location = os.environ['PR1108_YFINANCE_CACHE']
    if not os.path.isabs(location):
        raise ValueError('Cache location must be absolute')
    probe_stage('cache_location_set_begin')
    cache.set_cache_location(location)
    probe_stage('cache_location_set_complete')
    managers = [getattr(cache, name) for name in ('_TzDBManager', '_CookieDBManager')]
    if hasattr(cache, '_ISINDBManager'):
        managers.append(cache._ISINDBManager)
    probe_stage('cache_location_verify_begin')
    configured = [os.path.normcase(os.path.abspath(manager.get_location())) for manager in managers]
    if any(path != os.path.normcase(os.path.abspath(location)) for path in configured):
        raise RuntimeError('Provider cache location was not applied')
    cache._readonly_cache_locations = configured
    cache._readonly_cache_isolated = True
    probe_stage('cache_isolation_complete')
except BaseException:
    # Python normally prints and ignores sitecustomize exceptions. Fail closed.
    try:
        probe_stage('sitecustomize_failed')
    finally:
        os._exit(78)
