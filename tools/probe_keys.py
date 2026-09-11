"""Read-only button/player-state probe for fingerprinted V2.40 and V2.57 builds."""
import json
from player_memory import PlayerMemory, arguments


def snapshot(rootfs='/work/rootfs', version=None):
    with PlayerMemory(rootfs, version) as player:
        fields = player.profile['diagnostics']['keys']
        result = {key: player.word(fields[key], 1)
                  for key in ('volume', 'screen_on', 'single', 'double', 'hold')}
        context = player.word(fields['player_context'])
        if not context or context % 4:
            raise ValueError('Player context is not initialized/aligned')
        state = player.integer(context + int(fields['state_offset'], 16))
        # A snapshot spans several reads; never claim an atomic state transition.
        if context != player.word(fields['player_context']):
            raise ValueError('Player context changed during snapshot; retry')
        return dict(pid=player.pid, firmware=player.profile['version'], **result,
                    player_state=state, gain=player.device.gains())


if __name__ == '__main__':
    args = arguments(__doc__)
    print(json.dumps(snapshot(args.rootfs, args.version), indent=2))
