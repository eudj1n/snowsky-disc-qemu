#!/usr/bin/env python3
"""Live WebSocket protocol check. --control temporarily changes volume/playback."""
import argparse
import asyncio
import json
import time
from aiohttp import ClientSession, WSServerHandshakeError
from fiio_link import Client
from fiio_ws import WSClient


async def playback_snapshot(client, state=None, song_id=None, timeout=8):
    """Wait for a complete, settled query snapshot, not a state-only a202 event.

    The protocol has no correlation IDs. Only repeat read-only queries; never
    retry play_all/play_pause while waiting for metadata or a state transition.
    """
    async with asyncio.timeout(timeout):
        while True:
            result = await client.now_playing()
            song = result.get('song')
            if (isinstance(song, dict) and 'id' in song and 'state' in result
                    and (state is None or result['state'] == state)
                    and (song_id is None or song['id'] == song_id)):
                return result
            await asyncio.sleep(.1)


async def verify(url, tcp_host, control=False):
    # Independent TCP connection, closed before WS: stock permits one active client.
    def baseline():
        deadline = time.monotonic() + 3
        while True:
            try:
                with Client(tcp_host) as client:
                    return {'protocol': client.handshake(), 'settings': client.settings(), 'tracks': client.tracks()}
            except OSError:
                # Read-only baseline only: stock reopens its listener after a previous client.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
    tcp = await asyncio.to_thread(baseline)
    result = {'transport': 'emulator-ws-to-tcp', 'url': url}
    async with WSClient(url) as client:
        result['protocol'] = await client.handshake()
        result['settings'] = await client.settings()
        result['tracks'] = await client.tracks()
        assert result['protocol'] == tcp['protocol'] == '0306'
        assert result['settings'] == tcp['settings']
        assert result['tracks'] == tcp['tracks']
        result['matches_direct_tcp'] = True
        async with ClientSession() as second:
            try:
                await second.ws_connect(url)
            except WSServerHandshakeError as error:
                assert error.status == 409
                result['second_client_status'] = error.status
            else:
                raise AssertionError('second client should be rejected')
        if control:
            volume = result['settings']['currentVolume']
            target = volume - 1 if volume else 1
            try:
                await client.set_volume(target)
                await asyncio.sleep(.2)
                changed = (await client.settings())['currentVolume']
                assert changed == target
            finally:
                await client.set_volume(volume)
                await asyncio.sleep(.2)
            restored = (await client.settings())['currentVolume']
            assert restored == volume
            result['volume'] = [volume, changed, restored]
            assert result['tracks']['total'], 'Run Update media lib first'
            await client.play_all()
            try:
                await asyncio.sleep(.4)  # Let the decoder produce PCM before pausing.
                before = await playback_snapshot(client, state=0)
                await client.play_pause()
                after = await playback_snapshot(client, state=1, song_id=before['song']['id'])
                assert before['song']['id'] == after['song']['id']
                result['playing'], result['paused'] = before, after
            finally:
                state = await playback_snapshot(client)
                if state['state'] == 0:
                    await client.play_pause()
                    state = await playback_snapshot(client, state=1)
                assert state['state'] == 1, 'Could not leave playback paused'
                result['final_state'] = state['state']
    await asyncio.sleep(.2)  # release the stock single-client channel before reconnecting
    async with WSClient(url) as client:
        result['reconnect_protocol'] = await client.handshake()
        assert result['reconnect_protocol'] == '0306'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='ws://127.0.0.1:12103/api/websocket')
    parser.add_argument('--tcp-host', default='127.0.0.1')
    parser.add_argument('--control', action='store_true', help='select library, test controls, leave paused')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.url, args.tcp_host, args.control)), indent=2, ensure_ascii=False))
