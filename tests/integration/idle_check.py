"""Bounded idle-power research on a disposable V2.57 guest, never a LAN bridge."""
import asyncio
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import sqlite3
import subprocess
import time

from tests.integration.remote_control import ROOT, call, snapshot
from tests.integration.queue_check import connection, http_client
from tests.integration.queue_reads_check import prepare
from tests.integration.storage_check import ui
from research.diagnostics.player_memory import PlayerMemory
from firmware.profile import load_profile, validate
from emulator.runtime.keys import Device, Buttons
from tests.integration.guest_check import capture
from emulator.runtime.peripherals import Peripherals


def save_logs(label):
    directory = Path('/work/idle-evidence') / label
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('mq_player.log', 'mq_ui.log'):
        shutil.copyfile(Path('/work') / name, directory / name)


def require_disposable():
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('idle acceptance requires disposable V2.57')
    validate(ROOT, load_profile('2.57'))


def configure(power_save):
    require_disposable()
    if type(power_save) is not int or power_save not in (0, 300):
        raise ValueError('Only reviewed idle fixtures 0 and 300 are allowed')
    if Device(ROOT).processes():
        raise RuntimeError('Fixture settings require a stopped guest')
    with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/sysconfig.db?mode=rw', uri=True) as db:
        if db.execute('SELECT ID FROM SYSCONFIG').fetchall() != [(1,)]:
            raise RuntimeError('Unexpected SYSCONFIG fixture')
        print('Original settings', db.execute(
            'SELECT LIGTH_ON_TIME, POWER_SAVE FROM SYSCONFIG').fetchall(), flush=True)
        db.execute('UPDATE SYSCONFIG SET LIGTH_ON_TIME=3, POWER_SAVE=? WHERE ID=1', (power_save,))


def power_snapshot(memory):
    fields = {'screen': ('83a755', 1), 'mode': ('83a759', 1),
              'idle_limit': ('83a75c', 4), 'marker': ('83a760', 1),
              'usb_detected': ('83a768', 1),
              'sleep_limit': ('83a76c', 4), 'connected': ('898950', 4),
              'sleep_counter': ('899140', 2), 'idle_counter': ('899142', 2),
              'previous_marker': ('899147', 1)}
    result = {k: memory.word(a, n) for k, (a, n) in fields.items()}
    context = memory.word('83dfc4')
    result['state'] = memory.integer(context + 0x48) if context else None
    result['power_request'] = (ROOT / 'emu/power-request').read_bytes()[:1].decode()
    return result


async def watch(memory, seconds, label, client=None):
    start = time.monotonic()
    samples = []
    last_print = last_query = -10
    while time.monotonic() - start < seconds:
        value = power_snapshot(memory)
        elapsed = time.monotonic() - start
        changed = not samples or any(value[k] != samples[-1][1][k]
                                    for k in ('screen', 'marker', 'state', 'power_request'))
        if changed or elapsed - last_print >= 10:
            print(label, round(elapsed, 2), json.dumps(value), flush=True)
            last_print = elapsed
        samples.append((elapsed, value))
        if value['power_request'] == '1':
            return samples
        if client and elapsed - last_query >= 5:
            # Read-only activity, not a fabricated touch/heartbeat or mutation retry.
            try:
                assert (await call(client.settings))['soc_version'] == 257
                print(label, 'settings reply', round(elapsed, 2), flush=True)
            except (OSError, ConnectionError):
                print(label, 'read unavailable during shutdown', flush=True)
            last_query = elapsed
        await asyncio.sleep(.5)
    return samples


async def wait_for(predicate, label, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(.1)
    raise AssertionError(f'Timed out: {label}')


def quiet_trace(samples):
    assert samples[-1][0] >= 134, samples[-1]
    assert samples[0][1]['screen'] == 1 and samples[-1][1]['screen'] == 0
    assert any(value['marker'] == 1 for _, value in samples)
    for _, value in samples:
        assert value['state'] == 2 and value['connected'] == 1, value
        assert value['idle_limit'] == value['idle_counter'] == value['sleep_limit'] == 0, value
        assert value['power_request'] == '0', value


async def refused(fn):
    try:
        await call(fn)
    except (OSError, ConnectionError):
        return
    raise AssertionError('Stopped guest unexpectedly served a protocol read')


def keep_capture(name):
    capture(name)
    # Boot clears /work/shots; retain only these generated-media UI captures.
    directory = Path('/work/idle-shots')
    directory.mkdir(exist_ok=True)
    shutil.copyfile(f'/work/shots/ci-{name}.png', directory / f'{name}.png')


def usb_reads(connected):
    for path, size, expected in (
            ('/dev/aw35615', 1, b'\x01'),
            ('/dev/jz_adc_aux_1', 4, struct.pack('<I', 600 if connected else 0)),
            ('/dev/jz_adc_aux_0', 4, None), ('/dev/jz_adc_aux_2', 4, None),
            ('/dev/jz_adc_aux_3', 4, None)):
        result = subprocess.run(['bash', '-c',
                                 'source /repo/emulator/scripts/lib.sh; guest_run 5 /bin/busybox dd "if=$1" "bs=$2" count=1',
                                 'usb-read', path, str(size)], capture_output=True, timeout=8)
        if expected is None:
            assert result.returncode == 1 and result.stdout == b'', (path, result)
        else:
            assert result.returncode == 0 and result.stdout == expected, (path, result)
    print('USB shim read ABI verified; unrelated ADC sensors remain unavailable', flush=True)


async def usb_power_check():
    """Power-only USB detection; no gadget, DAC, storage or real host device."""
    device = Device(ROOT)
    controls = Peripherals(device)
    buttons = Buttons(ROOT, device)
    assert not controls.snapshot()['usb_connected'], 'Expected fresh disconnected fixture'
    with PlayerMemory(ROOT, '2.57') as memory:
        async with connection('tcp') as client:
            await call(client.set_play_mode, 2)
            await call(client.play_all, 3, 'CI Album')
            await snapshot(client, lambda s: s['state'] == 0)
            await asyncio.sleep(2.1)
            await call(client.play_pause)
            await snapshot(client, lambda s: s['state'] == 1)
            buttons.gesture('power', 'single')
            await wait_for(lambda: not device.screen_on(), 'USB fixture screen sleep')
            try:
                for connected in (False, True, False):
                    controls.set_usb(connected)
                    assert controls.snapshot()['usb_connected'] == connected
                    expected = 'Charging' if connected else 'Discharging'
                    assert (ROOT / 'sys/class/power_supply/cw221X-bat/status').read_text().strip() == expected
                    await wait_for(lambda: power_snapshot(memory)['usb_detected'] == int(connected),
                                   f'native USB detection {connected}')
                    usb_reads(connected)
                    if connected:
                        await wait_for(lambda: power_snapshot(memory)['idle_counter'] == 0,
                                       'USB resets idle counter')
                    else:
                        # Native cable removal wakes the screen and resets LVGL
                        # inactivity. Observe that transition before testing a
                        # deliberately dark, paused, unplugged player again.
                        await asyncio.sleep(2)
                        if device.screen_on():
                            await wait_for(lambda: power_snapshot(memory)['idle_counter'] == 0,
                                           'unplug wake resets idle')
                            buttons.gesture('power', 'single')
                        await wait_for(lambda: not device.screen_on()
                                       and power_snapshot(memory)['screen'] == 0, 'unplugged screen sleep')
                    samples = await watch(memory, 310 if connected else 8, f'usb-power/{connected}')
                    assert all(v['usb_detected'] == int(connected) and v['state'] == 2
                               and v['idle_limit'] == 300 and v['power_request'] == '0'
                               for _, v in samples), samples
                    if connected:
                        assert samples[-1][0] >= 309
                        assert all(v['idle_counter'] == 0 for _, v in samples), samples
                        assert samples[-1][1]['screen'] == 0, samples[-1]
                        buttons.gesture('power', 'single')
                        await wait_for(device.screen_on, 'powered screenshot wake')
                        await asyncio.sleep(2)
                        keep_capture('idle-usb-powered')
                    else:
                        assert samples[-1][1]['idle_counter'] > samples[0][1]['idle_counter'], samples
                print('USB POWER CHECK PASS: 310 seconds paused/screen-off stay alive; unplug restores idle counting', flush=True)
            finally:
                controls.set_usb(False)
            if not device.screen_on():
                buttons.gesture('power', 'single')
            await wait_for(lambda: power_snapshot(memory)['screen'] == 1
                           and power_snapshot(memory)['idle_counter'] == 0, 'USB fixture wake')
            await asyncio.sleep(1)
            keep_capture('idle-usb-unplugged')


async def exercise(transport, shutdown):
    device = Device(ROOT)
    buttons = Buttons(ROOT, device)
    with PlayerMemory(ROOT, '2.57') as memory:
        async with connection(transport) as client:
            await call(client.set_play_mode, 2)
            await call(client.play_all, 3, 'CI Album')
            await snapshot(client, lambda s: s['state'] == 0)
            await asyncio.sleep(2.1)
            if shutdown:
                buttons.gesture('power', 'single')
                await wait_for(lambda: not device.screen_on() and power_snapshot(memory)['screen'] == 0,
                               'manual screen sleep (sysfs and player)')
                playing = await watch(memory, 8, f'{transport}/screen-off-playing')
                assert all(v['state'] == 1 and v['idle_counter'] == 0 and v['screen'] == 0
                           for _, v in playing), playing
            await call(client.play_pause)
            paused = await snapshot(client, lambda s: s['state'] == 1)
            if shutdown:
                manual = await watch(memory, 8, f'{transport}/screen-off-paused', client)
                assert manual[-1][1]['idle_counter'] > manual[0][1]['idle_counter'], manual
                assert manual[-1][1]['power_request'] == '0'
                buttons.gesture('power', 'single')
                await wait_for(lambda: power_snapshot(memory)['screen'] == 1
                               and power_snapshot(memory)['idle_counter'] == 0,
                               'physical wake resets idle counter')
                print(transport, 'wake reset', power_snapshot(memory), flush=True)
                # Use the actual two-minute UI timer and stock 300 value. No
                # accelerated clock, memory writes or forced shutdown command.
                terminal = await watch(memory, 360, f'{transport}/natural-idle', client)
                assert terminal[-1][1]['power_request'] == '1', terminal[-1]
                assert any(v['screen'] == 0 for _, v in terminal)
                assert any(v['idle_counter'] > 0 for _, v in terminal)
                print(transport, 'confined stock shutdown observed', flush=True)
                try:
                    result = await call(client.settings)
                    print(transport, 'pre-supervisor settings still reply', result.get('soc_version'), flush=True)
                except (OSError, ConnectionError):
                    print(transport, 'pre-supervisor connection already unavailable', flush=True)
                # Without the viewer, the intercepted kernel request is pending.
                # Run the SAME chroot-scoped supervisor used by the viewer.
                device.service_requests()
                await wait_for(lambda: not device.processes() and device.transition is None,
                               'guest-only supervisor stop')
                assert device.error is None, device.error
                await refused(client.settings)
            else:
                quiet_trace(await watch(memory, 135, f'{transport}/quiet-paused'))
            if shutdown:
                return
            assert (await call(client.settings))['soc_version'] == 257
            assert (await snapshot(client, lambda s: s['state'] == 1))['song'] == paused['song']
            print(transport, 'same connection survives quiet screen timeout', flush=True)
        async with connection(transport) as client:
            assert (await snapshot(client, lambda s: s['state'] == 1))['song'] == paused['song']
            assert http_client(transport).catalog('curlist/song')['total'] == 2
            print(transport, 'fresh handshake/settings/queue after reconnect', power_snapshot(memory), flush=True)
            await call(client.play_pause)
            await snapshot(client, lambda s: s['state'] == 0)
            resumed = await watch(memory, 4, f'{transport}/remote-resume')
            assert all(v['screen'] == 0 and v['state'] == 1 for _, v in resumed), resumed
            if not device.screen_on():
                buttons.gesture('power', 'single')
            await watch(memory, 2, f'{transport}/physical-wake')
            assert device.screen_on()
            keep_capture(f'idle-{transport}-wake')


async def recover(transport):
    device = Device(ROOT)
    # Probe stock TCP once while fully stopped; do not mistake a failed read for
    # authorization to boot or replay the last playback command.
    from controller.fiio_link import Client
    try:
        with Client(timeout=1):
            raise AssertionError('TCP listener survived guest-only stop')
    except OSError:
        pass
    assert not device.processes()
    Buttons(ROOT, device).gesture('power', 'single')  # Explicit local Power action.
    await wait_for(lambda: device.transition is None, 'explicit local boot', 100)
    assert device.error is None and device.running(), device.status()
    async with connection(transport) as client:
        assert (await call(client.settings))['soc_version'] == 257
        assert (await call(client.tracks))['total'] == 3
        queue = http_client(transport).catalog('curlist/song')
        print(transport, 'explicit boot, fresh handshake/settings/catalog/queue', queue, flush=True)
        assert queue['total'] == 2
        # Resume-memory restoration is not guaranteed by a retained queue. A
        # stopped stock player suppresses 0202 rather than sending empty state.
        # A timeout passes only with the independently verified reply gate AND
        # fresh successful reads/explicit new playback below, never by itself.
        try:
            current = await call(client.now_playing)
        except TimeoutError:
            current = None
        with PlayerMemory(ROOT, '2.57') as memory:
            context = memory.word('83dfc4')
            assert context, 'Missing local player after boot'
            runtime = power_snapshot(memory)
            runtime['metadata_suppressed'] = memory.integer(context + 0x50)
        print(transport, 'fresh playback after boot', current, runtime, flush=True)
        if current is None:
            assert runtime['metadata_suppressed'] == 1, runtime
        assert runtime['mode'] == 8 and runtime['power_request'] == '0', runtime
        assert (await call(client.settings))['soc_version'] == 257
        assert await call(client.play_mode) == 2
        # A NEW deliberate test action after inspecting fresh state, not an
        # automatic reconnect retry of the old selection/toggle.
        await call(client.set_play_mode, 0)
        await asyncio.sleep(2.1)  # Stock boot-time memory selection may be recent.
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await asyncio.sleep(2.1)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        print(transport, 'explicit new selection/play/pause after recovery passed', flush=True)
    keep_capture(f'idle-{transport}-reboot')


async def main(phase='all'):
    require_disposable()
    configure(300 if phase in ('usb', 'power') else 0)
    subprocess.run(['bash', '/repo/emulator/scripts/20_boot.sh'], check=True)
    assert ui({'index': (0x8e1721, 1), 'seconds': (0x83a650, 4)}) == {'index': 3, 'seconds': 120}
    await prepare()
    if phase == 'usb':
        await usb_power_check()
        save_logs('usb-power')
        return
    if phase in ('all', 'quiet'):
        for transport in ('tcp', 'ws'):
            if transport == 'ws':
                subprocess.run(['bash', '/repo/emulator/scripts/20_boot.sh'], check=True)
            await exercise(transport, False)
            save_logs(f'{transport}-quiet')
        if phase == 'quiet':
            print('IDLE QUIET CHECK PASS TCP/WS', flush=True)
            return
    for transport in ('tcp', 'ws'):
        subprocess.run(['python3', '-m', 'emulator.runtime.keys', 'stop'], check=True)
        configure(300)
        subprocess.run(['bash', '/repo/emulator/scripts/20_boot.sh'], check=True)
        subprocess.run(['bash', '/repo/tests/integration/confinement.sh'], check=True)
        await exercise(transport, True)
        save_logs(f'{transport}-shutdown')
        await recover(transport)
        save_logs(f'{transport}-reboot')
    for path in Path('/work/idle-shots').glob('*.png'):
        shutil.copyfile(path, Path('/work/shots') / path.name)
    print(f'IDLE CHECK PASS V2.57 phase={phase}: TCP/WS lifecycle', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('all', 'quiet', 'power', 'usb'), default='all')
    asyncio.run(main(parser.parse_args().phase))
