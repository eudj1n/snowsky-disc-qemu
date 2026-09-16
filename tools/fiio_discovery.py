#!/usr/bin/env python3
"""Passive DISC multicast discovery. No probes, connections or automatic control.

The V2.57 announcement is the literal product name, not a FiiO Link frame.
Addresses are untrusted hints from UDP, not authenticated device identities.
"""
import argparse
import ipaddress
import json
import math
import socket
import time

GROUP = '224.0.0.255'
PORT = 12101
PAYLOAD = b'SNOWSKY DISC'


def interface_address(value):
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_multicast or int(address) == 0xffffffff:
        raise ValueError('choose a specific local unicast IPv4 interface address')
    return str(address)


def announcement(data, peer):
    """Recognize only the observed DISC payload, without trusting arbitrary names."""
    if data != PAYLOAD:
        return None
    address = interface_address(peer[0])
    return {'name': PAYLOAD.decode('ascii'), 'host': address,
            'source_port': peer[1], 'tcp_port': 12100, 'http_port': 12103}


def listen(interface):
    interface = interface_address(interface)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # macOS multicast sockets need port reuse to coexist with other listeners.
        if hasattr(socket, 'SO_REUSEPORT'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(('', PORT))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(GROUP) + socket.inet_aton(interface))
        return sock
    except BaseException:
        sock.close()
        raise


def observe(sock, seconds):
    """Bounded stream; unknown packets are ignored and never auto-connected."""
    if not math.isfinite(seconds) or not 0 < seconds <= 300:
        raise ValueError('observation duration must be in (0, 300] seconds')
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        sock.settimeout(remaining)
        try:
            data, peer = sock.recvfrom(2048)
        except socket.timeout:
            return
        try:
            value = announcement(data, peer)
        except ValueError:
            continue
        if value is not None:
            yield time.monotonic(), value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', required=True, help='local IPv4 address, not device IP')
    parser.add_argument('--seconds', type=float, default=15)
    args = parser.parse_args()
    started = time.monotonic()
    with listen(args.interface) as sock:
        for stamp, value in observe(sock, args.seconds):
            print(json.dumps(dict(value, elapsed=round(stamp - started, 3))), flush=True)


if __name__ == '__main__':
    main()
