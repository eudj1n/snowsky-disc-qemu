"""Persistent web-facing selections/edits on disposable generated CI media."""
from controller import DeviceConfig, DiscSession, QueueItem
from controller.catalog import CatalogReader
from controller.fiio_http import HTTPClient


def check():
    http = HTTPClient(port=12103)
    with DiscSession(DeviceConfig('127.0.0.1', http_port=12103)) as session:
        session.connect()
        assert session.wait_ready(35), session.snapshot()
        with session.operation():
            rows = CatalogReader(http).rows('album/song', album='CI Album')
        expected = tuple(QueueItem(r['pos'], r['name'], r['author']) for r in rows)
        assert len(expected) == 2
        result = session.play_album('CI Album', index=1, expected=expected)
        assert result.status == 'playing' and result.queue.selected_position == 1, result
        queue = result.queue.items
        result = session.play_queue_index(0, expected=queue)
        assert result.status == 'confirmed' and result.queue.selected_position == 0, result
        stale = (QueueItem(0, 'Stale synthetic title', 'CI Artist'),) + queue[1:]
        rejected = session.play_queue_index(0, expected=stale)
        assert rejected.status == 'not_sent' and not rejected.mutation_attempted, rejected
        assert session.create_playlist('Web CI').status == 'confirmed'
        assert session.add_playlist_track('Web CI', 1, expected=expected, album='CI Album').status == 'confirmed'
        assert session.rename_playlist('Web CI', 'Web CI renamed').status == 'confirmed'
        with session.operation():
            playlists = CatalogReader(http).rows('custom')
            position = next(r['pos'] for r in playlists if r['name'] == 'Web CI renamed')
            members = CatalogReader(http).rows('custom/song', src_list_id=position)
        selected = tuple(QueueItem(r['pos'], r['name'], r['author']) for r in members)
        result = session.remove_playlist_track('Web CI renamed', 0, expected=selected)
        assert result.status == 'confirmed', result
        # This entire stack is disposable; remove only this generated empty list.
        with session.operation():
            http.delete_playlist(position)
            assert all(r['name'] != 'Web CI renamed' for r in CatalogReader(http).rows('custom'))
        assert session.pause().status in ('confirmed', 'already_satisfied')
    print('WEB SESSION ACCEPTANCE PASSED: indexed album, queue, stale-source rejection and playlist edits', flush=True)


if __name__ == '__main__':
    check()
