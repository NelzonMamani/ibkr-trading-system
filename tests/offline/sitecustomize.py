"""Hard offline boundary for CI, inherited by Python subprocesses."""
import socket
import sys

# Windows implements socketpair with a private TCP listener. Permit only the
# original stdlib function's own client -> listener connection, not loopback in
# general. No event-loop policy changes or thread-wide bypass are necessary.
_fallback = getattr(socket, '_fallback_socketpair', None)
_fallback_code = getattr(_fallback, '__code__', None)
_broker_ports = frozenset({4001, 4002, 7496, 7497})


def _internal_socketpair(args, caller):
    if _fallback_code is None or caller.f_code is not _fallback_code:
        return False
    client, target = args
    local = caller.f_locals
    listener = local.get('lsock')
    if client is not local.get('csock') or not isinstance(listener, socket.socket):
        return False
    address = listener.getsockname()[:2]
    return (
        target == address == (local.get('addr'), local.get('port'))
        and address[0] in {'127.0.0.1', '::1'}
        and 0 < address[1] <= 65535
        and address[1] not in _broker_ports
        and listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
    )


def offline(event, args):
    if event == 'socket.connect' and _internal_socketpair(args, sys._getframe(1)):
        return
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.sendto'}:
        raise OSError('OFFLINE_CI: network acquisition disabled')


sys.addaudithook(offline)

# yfinance uses native libcurl, which does not emit Python socket audit events.
# Stop its synchronous and asynchronous transfer entry points before native I/O.
def _deny_native_transfer(*args, **kwargs):
    raise OSError('OFFLINE_CI: native network acquisition disabled')


try:
    from curl_cffi import Curl, AsyncCurl
except ImportError:
    pass  # Optional only when yfinance/curl_cffi is not installed.
else:
    Curl.perform = _deny_native_transfer
    AsyncCurl.add_handle = _deny_native_transfer
