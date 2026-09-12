"""Read-only, exact-build QEMU guest memory access for diagnostic snapshots."""
import argparse
import os
from pathlib import Path
import struct

from firmware_profile import identify_player
from keys import Device


def load_segments(data):
    if len(data) < 52 or data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected ELF32 little-endian')
    phoff = struct.unpack_from('<I', data, 28)[0]
    size, count = struct.unpack_from('<HH', data, 42)
    if size < 32 or not count or phoff + size * count > len(data):
        raise ValueError('Invalid ELF program headers')
    segments = [struct.unpack_from('<8I', data, phoff + i * size) for i in range(count)]
    for kind, offset, va, _, filesz, memsz, flags, align in segments:
        if kind == 1 and (filesz > memsz or offset + filesz > len(data) or va + memsz > 2**32):
            raise ValueError('Invalid PT_LOAD range')
    return [s for s in segments if s[0] == 1]


def parse_maps(text):
    result = []
    for line in text.splitlines():
        address, perms, offset, dev, inode, *path = line.split(maxsplit=5)
        start, end = (int(n, 16) for n in address.split('-'))
        result.append(dict(start=start, end=end, perms=perms, offset=int(offset, 16),
                           dev=tuple(int(n, 16) for n in dev.split(':')),
                           inode=int(inode), path=path[0] if path else ''))
    return result


def guest_base(maps, segments, stat):
    """Bind translations to the running file's inode and ELF PT_LOAD mapping."""
    dev = (os.major(stat.st_dev), os.minor(stat.st_dev))
    candidates = None
    executable = set()
    for m in maps:
        if m['inode'] != stat.st_ino or m['dev'] != dev:
            continue
        possible = set()
        for _, offset, va, _, filesz, _, flags, _ in segments:
            # /proc maps offsets are page-aligned, including the ELF data segment.
            if (offset & ~4095) <= m['offset'] < offset + filesz:
                base = m['start'] - (va + m['offset'] - offset)
                possible.add(base)
                if flags & 1 and 'r' in m['perms']:
                    executable.add(base)
        # V2.40's segments share a file page but map it at two different VAs.
        # Each map can have several interpretations; all maps must agree on one.
        candidates = possible if candidates is None else candidates & possible
    # QEMU translates guest instructions; its host file mapping can be r--p.
    if not candidates or len(candidates) != 1 or not candidates <= executable:
        raise ValueError('Cannot identify a unique mapped mq_player ELF')
    return candidates.pop()


def read_memory(memory, maps, base, address, size):
    if address <= 0 or size <= 0 or address + size > 2**32:
        raise ValueError('Invalid guest address')
    start, end = base + address, base + address + size
    cursor = start
    for m in sorted(maps, key=lambda m: m['start']):
        if m['start'] <= cursor < m['end'] and 'r' in m['perms']:
            cursor = min(end, m['end'])
            if cursor == end:
                break
    if cursor != end:
        raise ValueError(f'Guest range {address:#x}+{size} is not readable')
    memory.seek(start)
    data = memory.read(size)
    if len(data) != size:
        raise ValueError('Short guest memory read; process may have exited')
    return data


class PlayerMemory:
    def __init__(self, rootfs='/work/rootfs', version=None):
        self.device = Device(rootfs)
        binary = self.device.root / 'usr/bin/mq_player'
        if binary.is_symlink():
            raise ValueError('Expected regular mq_player binary')
        with binary.open('rb') as source:
            stat = os.fstat(source.fileno())
            data = source.read()
        self.profile = identify_player(data, version)
        self.segments = load_segments(data)
        pids = []
        for pid in self.device.processes():
            try:
                # popen children can briefly retain the parent's argv. Select
                # the main thread, not a fork from echo_powerMG/other workers.
                if Path(f'/proc/{pid}/comm').read_text().strip() == 'mq_player' and \
                        b'/usr/bin/mq_player' in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0'):
                    pids.append(pid)
            except FileNotFoundError:
                continue
        if len(pids) != 1:
            raise ValueError(f'Expected one running mq_player in {self.device.root}, found {len(pids)}')
        self.pid = pids[0]
        self.proc = Path(f'/proc/{self.pid}')
        self.maps = parse_maps((self.proc / 'maps').read_text())
        self.base = guest_base(self.maps, self.segments, stat)

    def __enter__(self):
        self.memory = (self.proc / 'mem').open('rb', buffering=0)
        return self

    def __exit__(self, *args):
        self.memory.close()

    def read(self, address, size):
        return read_memory(self.memory, self.maps, self.base, address, size)

    def integer(self, address, size=4):
        return int.from_bytes(self.read(address, size), 'little')

    def field(self, address, size=4):
        address = int(address, 16)
        if not any(flags & 2 and va <= address and address + size <= va + memsz
                   for _, _, va, _, _, memsz, flags, _ in self.segments):
            raise ValueError('Diagnostic field is outside writable guest PT_LOAD')
        return self.read(address, size)

    def word(self, address, size=4):
        return int.from_bytes(self.field(address, size), 'little')


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--rootfs', default='/work/rootfs')
    parser.add_argument('--version', help='Require this exact reviewed version (default: fingerprint detection)')
    return parser.parse_args()
