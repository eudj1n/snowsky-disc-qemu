"""Reviewed DISC protocol contracts, selected from fresh device version readback.

No version ranges or implicit inheritance: new firmware needs explicit validation.
This registry describes existing guarded operations, not every raw protocol call.
"""

CONTRACTS = {
    240: frozenset({'network_check'}),
    257: frozenset({'favorite_positions', 'playlist_playback', 'genre_playback',
                    'artist_playback', 'folder_playback', 'network_check'}),
}


def supports(version, feature):
    return type(version) is int and feature in CONTRACTS.get(version, ())


def require(version, feature):
    if not supports(version, feature):
        raise ValueError(f'{feature} is not verified for DISC firmware {version!r}')
