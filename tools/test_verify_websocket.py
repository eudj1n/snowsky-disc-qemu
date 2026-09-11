import unittest

try:
    from verify_websocket import playback_snapshot
except ImportError:
    playback_snapshot = None


class ReadOnlyPlayer:
    def __init__(self, values):
        self.values = list(values)
        self.reads = 0

    async def now_playing(self):
        self.reads += 1
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


@unittest.skipUnless(playback_snapshot, 'aiohttp required; use the Docker CI image')
class PlaybackSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_ignores_state_only_notification(self):
        complete = {'state': 0, 'song': {'id': 1}}
        client = ReadOnlyPlayer([{'state': 0}, complete])
        self.assertEqual(await playback_snapshot(client, state=0), complete)
        self.assertEqual(client.reads, 2)

    async def test_waits_for_requested_state_and_track(self):
        complete = {'state': 1, 'song': {'id': 3}}
        client = ReadOnlyPlayer([{'state': 0, 'song': {'id': 3}},
                                 {'state': 1, 'song': {'id': 2}}, complete])
        self.assertEqual(await playback_snapshot(client, state=1, song_id=3), complete)
        self.assertEqual(client.reads, 3)

    async def test_partial_notifications_are_bounded(self):
        with self.assertRaises(TimeoutError):
            await playback_snapshot(ReadOnlyPlayer([{'state': 1}]), timeout=.02)

    async def test_wrong_stable_state_fails_without_control_retries(self):
        client = ReadOnlyPlayer([{'state': 0, 'song': {'id': 3}}])
        with self.assertRaises(TimeoutError):
            await playback_snapshot(client, state=1, timeout=.02)
