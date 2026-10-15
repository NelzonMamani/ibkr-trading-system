"""Hard offline boundary for CI, inherited by Python subprocesses."""
import sys

def offline(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.sendto'}:
        raise OSError('OFFLINE_CI: network acquisition disabled')

sys.addaudithook(offline)
