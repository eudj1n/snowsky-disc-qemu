#!/usr/bin/env python3
"""Opt-in host-side DISC discovery and TCP/HTTP forwarding for one trusted phone.

Run on the Mac/Linux host, NOT inside Docker Desktop. This exposes unauthenticated
stock control/file APIs to the allowed IP. An IP filter is not authentication.
No WS translation, arbitrary upstream, persistent service or automatic startup.
"""
import argparse
import asyncio
import contextlib
import socket

from fiio_discovery import GROUP, PORT, PAYLOAD, interface_address


async def http_ready(port=12113):
    """Check stock HTTP without occupying its single-client control channel."""
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port), 2)
        writer.write(b'GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n')
        await writer.drain()
        header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)
        return header.split(b'\r\n', 1)[0] in (b'HTTP/1.0 200 OK', b'HTTP/1.1 200 OK')
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        return False
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()


async def pump(reader, writer):
    while True:
        data = await asyncio.wait_for(reader.read(65536), 120)
        if not data:
            if writer.can_write_eof():
                writer.write_eof()
            return
        writer.write(data)
        await asyncio.wait_for(writer.drain(), 30)


class Proxy:
    def __init__(self, allowed, control_port=12100, http_port=12113):
        self.allowed = interface_address(allowed)
        self.ports = {'control': control_port, 'http': http_port}
        self.count = {'control': 0, 'http': 0}
        self.tasks = set()

    async def handle(self, reader, writer, kind):
        peer = writer.get_extra_info('peername')
        limit = 1 if kind == 'control' else 8
        if not peer or peer[0] != self.allowed or self.count[kind] >= limit:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            return
        task = asyncio.current_task()
        self.tasks.add(task)
        self.count[kind] += 1
        upstream = None
        pumps = []
        try:
            remote, upstream = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', self.ports[kind]), 3)
            print(f'{kind}: connected allowed client', flush=True)
            pumps = [asyncio.create_task(pump(reader, upstream)),
                     asyncio.create_task(pump(remote, writer))]
            # Preserve TCP half-close (HTTP/1.0 may finish its response after EOF).
            await asyncio.gather(*pumps)
        except (OSError, asyncio.TimeoutError):
            print(f'{kind}: connection closed/unavailable', flush=True)
        finally:
            for child in pumps:
                child.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            for stream in (writer, upstream):
                if stream is not None:
                    stream.close()
                    with contextlib.suppress(OSError):
                        await stream.wait_closed()
            self.count[kind] -= 1
            self.tasks.discard(task)
            print(f'{kind}: disconnected', flush=True)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def sender(interface):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((interface_address(interface), 0))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


async def announce(sock, proxy):
    while True:
        if not proxy.count['control'] and await http_ready(proxy.ports['http']):
            # Recheck after HTTP await: a phone may have connected meanwhile.
            if not proxy.count['control']:
                await asyncio.get_running_loop().sock_sendto(sock, PAYLOAD, (GROUP, PORT))
        await asyncio.sleep(2)


async def run(interface, allowed, seconds):
    proxy = Proxy(allowed)
    servers = []
    announcement_task = None
    try:
        for kind, port in (('control', 12100), ('http', 12103)):
            servers.append(await asyncio.start_server(
                lambda r, w, k=kind: proxy.handle(r, w, k), interface, port))
        with sender(interface) as sock:
            print(f'LAN bridge on {interface}:12100/12103; only {allowed} allowed; '
                  f'auto-stop in {seconds}s. Unauthenticated control and file access.', flush=True)
            announcement_task = asyncio.create_task(announce(sock, proxy))
            done, _ = await asyncio.wait({announcement_task}, timeout=seconds)
            if done:
                await announcement_task  # Surface errors, do not silently stop announcing.
    finally:
        if announcement_task:
            announcement_task.cancel()
            await asyncio.gather(announcement_task, return_exceptions=True)
        for server in servers:
            server.close()
        for server in servers:
            await server.wait_closed()
        await proxy.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', required=True, type=interface_address)
    parser.add_argument('--allow-client', required=True, type=interface_address)
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--acknowledge-unauthenticated-control', action='store_true')
    args = parser.parse_args()
    if not args.acknowledge_unauthenticated_control:
        parser.error('explicit --acknowledge-unauthenticated-control is required')
    if not 1 <= args.seconds <= 3600:
        parser.error('--seconds must be 1..3600')
    try:
        asyncio.run(run(args.interface, args.allow_client, args.seconds))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
