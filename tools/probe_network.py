"""Read-only network/callback/capability probe for fingerprinted V2.40 and V2.57."""
import json
from player_memory import PlayerMemory, arguments


def snapshot(rootfs='/work/rootfs', version=None):
    with PlayerMemory(rootfs, version) as player:
        fields = player.profile['diagnostics']['network']
        result = {key: player.word(fields[key])
                  for key in ('ready', 'storage_type', 'scan_running')}
        result.update(pid=player.pid, firmware=player.profile['version'],
                      ip=player.field(fields['ip'], 16).split(b'\0')[0].decode('ascii'),
                      callbacks={tag: hex(player.word(address))
                                 for tag, address in fields['callbacks'].items()})
        status = dict(line.split(':', 1) for line in (player.proc / 'status').read_text().splitlines())
    result['capabilities'] = {key: status[key].strip()
                              for key in ('CapEff', 'CapBnd', 'NoNewPrivs')}
    forbidden = sum(1 << bit for bit in (12, 16, 17, 22, 25))
    result['dangerous_caps_dropped'] = all(
        int(status[key].strip(), 16) & forbidden == 0 for key in ('CapEff', 'CapBnd'))
    return result


if __name__ == '__main__':
    args = arguments(__doc__)
    print(json.dumps(snapshot(args.rootfs, args.version), indent=2))
