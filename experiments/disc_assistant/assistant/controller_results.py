"""Serialize Controller models into the Assistant's response/journal schema."""
from typing import Any

from controller.models import CommandResult, MODES, PlaybackState


def serialize(result: CommandResult) -> dict[str, Any]:
    value: dict[str, Any] = {'operation_id': result.operation_id, 'status': result.status.value,
             'action': result.action, 'mutation_attempted': result.mutation_attempted}
    for name in ('outcome', 'reason', 'confirmation', 'volume', 'previous_volume', 'error_type'):
        item = getattr(result, name)
        if item is not None:
            value[name] = item
    playback = result.playback
    if playback.track is not None:
        track = playback.track
        song: dict[str, Any] = {'song_name': track.title, 'song_artist_name': track.artist,
                'song_album_name': track.album}
        if track.queue_position is not None:
            song['pos_id'] = track.queue_position + 1
        if track.path is not None:
            song['song_file_path'] = track.path
        state: dict[str, Any] = {'song': song}
        states = {PlaybackState.PLAYING: 0, PlaybackState.PAUSED: 1,
                  PlaybackState.LOADING: 2, PlaybackState.STOPPED: 2}
        if playback.state in states:
            state['state'] = states[playback.state]
        if playback.favorite is not None:
            state['love'] = playback.favorite
        if playback.source is not None:
            state['playerflag'] = int(playback.source)
        value['state'] = state
    if result.queue is not None:
        queue = result.queue
        value['queue'] = {'items': [{'pos': row.position, 'name': row.title, 'author': row.artist}
                                    for row in queue.items],
                          'mark': queue.selected_position if queue.selected_position is not None else -1,
                          'mode': MODES.index(queue.mode), 'continuation': queue.continuation}
    return value
