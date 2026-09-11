"""Read-only V2.40 button-state probe; run inside the container, never writes guest memory."""
import json
from pathlib import Path

from keys import Device


def snapshot(rootfs='/work/rootfs'):
    device = Device(rootfs)
    pid = next(p for p in device.processes()
               if b'/usr/bin/mq_player' in Path(f'/proc/{p}/cmdline').read_bytes().split(b'\0'))
    mapping = next(line for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
                   if '/usr/bin/mq_player' in line and line.split()[2] == '00000000')
    base = int(mapping.split('-')[0], 16) - 0x400000
    with open(f'/proc/{pid}/mem', 'rb', buffering=0) as memory:
        def read(address, size=1):
            memory.seek(base + address)
            return int.from_bytes(memory.read(size), 'little')
        return dict(pid=pid, volume=read(0x82e98c), screen_on=read(0x82e995),
                    single=read(0x82e9d2), double=read(0x82e9d3), hold=read(0x82e9d4),
                    player_state=read(read(0x8321f4, 4) + 0x48, 4), gain=device.gains())


if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
