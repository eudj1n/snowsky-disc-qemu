"""Read-only V2.40 netlink/callback/capability probe, run inside the container."""
import json
from pathlib import Path
from keys import Device
from firmware_profile import require_v240_player


def snapshot(rootfs='/work/rootfs'):
    require_v240_player(Path(rootfs) / 'usr/bin/mq_player')
    device = Device(rootfs)
    pid = next(p for p in device.processes()
               if b'/usr/bin/mq_player' in Path(f'/proc/{p}/cmdline').read_bytes().split(b'\0'))
    mapping = next(line for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
                   if '/usr/bin/mq_player' in line and line.split()[2] == '00000000')
    base = int(mapping.split('-')[0], 16) - 0x400000
    with open(f'/proc/{pid}/mem', 'rb', buffering=0) as memory:
        def read(address, size):
            memory.seek(base + address)
            return memory.read(size)
        result = {'pid': pid, 'ready': int.from_bytes(read(0x86c030, 4), 'little'),
                  'ip': read(0x86c020, 16).split(b'\0')[0].decode(),
                  'storage_type': int.from_bytes(read(0x88cb9c, 4), 'little'),
                  'scan_running': int.from_bytes(read(0x88c844, 4), 'little'),
                  'callbacks': {tag: hex(int.from_bytes(read(addr, 4), 'little'))
                                for tag, addr in [('0502', 0x82e634), ('0201', 0x82e638),
                                                  ('volume_device', 0x88cc44)]}}
    status = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines())
    result['capabilities'] = {key: status[key].strip()
                              for key in ('CapEff', 'CapBnd', 'NoNewPrivs')}
    forbidden = sum(1 << bit for bit in (12, 16, 17, 22, 25))
    result['dangerous_caps_dropped'] = all(
        int(status[key].strip(), 16) & forbidden == 0 for key in ('CapEff', 'CapBnd'))
    return result


if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
