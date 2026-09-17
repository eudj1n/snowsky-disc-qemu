import json
import struct
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from controller.fiio_link import Client, Frames, frame
from controller.fiio_ws import WSClient
from controller.fiio_settings import (SETTINGS, SETTING_FIELDS, GAIN_LABELS, FILTER_LABELS, EQ_LABELS,
                           setting_command, setting_value, peq_payload, peq_value)


class SettingTests(unittest.IsolatedAsyncioTestCase):
    def test_device_eq_labels_use_network_values_without_guessed_bypass(self):
        expected = [(255, 'Off'), (0, 'Jazz'), (2, 'Rock'), (4, 'R&B'),
                    (6, 'HIP-HOP'), (1, 'Pop'), (3, 'Dance'), (5, 'Classical'),
                    (8, 'Retro'), (9, 'Sibilance attenuation 1'),
                    (10, 'Sibilance attenuation 2')]
        self.assertEqual(list(EQ_LABELS.items())[:11], expected)
        self.assertEqual(set(EQ_LABELS), set(SETTINGS['eq_type'][2]))
        for value, name in expected + [(160 + i, f'USER{i + 1}') for i in range(10)]:
            self.assertEqual(EQ_LABELS[value], name)
            self.assertEqual(setting_command('eq_type', value), ('0690', f'{value:04X}'))
        for unknown in (7, 240, 254):
            with self.assertRaises(ValueError):
                setting_command('eq_type', unknown)

    async def test_physical_peq_presets_and_bypass_echo_do_not_expand_supported_modes(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_peq_presets.json').read_text())
        transitions = observed['transitions']
        self.assertEqual([t['value'] for t in transitions],
                         [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, *range(160, 170), 240, 255])
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        for transition in transitions:
            value = transition['value']
            [(tag, payload)] = Frames().feed(transition['reply']['wire'].encode())
            self.assertEqual(tag, 'a639')
            self.assertEqual(setting_value('eq_type', payload), value)
            if value == 240:
                self.assertEqual(transition['owner_confirmed_app_label'], 'BYPASS')
                tcp.socket.reset_mock()
                ws.send.reset_mock()
                with self.assertRaises(ValueError):
                    tcp.set_device_setting('eq_type', value)
                with self.assertRaises(ValueError):
                    await ws.set_device_setting('eq_type', value)
                tcp.socket.sendall.assert_not_called()
                ws.send.assert_not_called()
                continue
            self.assertEqual(transition['stock_label'], EQ_LABELS[value])
            tcp.set_device_setting('eq_type', value)
            await ws.set_device_setting('eq_type', value)
            expected = Frames().feed(transition['request']['wire'].encode())
            self.assertEqual(Frames().feed(tcp.socket.sendall.call_args.args[0]), expected)
            self.assertEqual(Frames().feed(frame(*ws.send.call_args.args)), expected)
        profiles = []
        for transition in transitions[-3:]:
            replies = [parsed for reading in transition['reads']
                       for parsed in Frames().feed(reading['wire'].encode())]
            profiles.append(next(peq_value(body) for tag, body in replies if tag == 'a628'))
            self.assertEqual([setting_value('eq_master_db', body)
                              for tag, body in replies if tag == 'a629'], [0.0])
        self.assertEqual([b['qValue'] for b in profiles[0]], [.71] * 10)
        self.assertEqual(profiles[1], [dict(b, qValue=.7) for b in profiles[0]])
        self.assertEqual(profiles[2], profiles[1])

    async def test_all_filter_rows_match_physical_ios_capture_and_restore(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_filters.json').read_text())
        self.assertEqual(observed['firmware'], 257)
        transitions = observed['transitions']
        self.assertEqual([t['row'] for t in transitions], [3, 4, 5, 6, 1, 2])
        self.assertEqual({t['value'] for t in transitions}, set(FILTER_LABELS))
        english = observed['english_labels_by_row']
        self.assertEqual(len(english), 6)
        self.assertEqual(english[1], 'Minimum phase slow roll-off')
        self.assertEqual(english[4:], ['Reference super slow roll-off'] * 2)
        self.assertEqual([t['value'] for t in transitions if english[t['row'] - 1] == english[4]], [4, 5])
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        for transition in transitions:
            value = transition['value']
            self.assertEqual(transition['row'], value + 1)
            self.assertEqual(transition['stock_label'], FILTER_LABELS[value])
            self.assertEqual(transition['label_truncated'], transition['row'] in (5, 6))
            tcp.set_device_setting('filter', value)
            await ws.set_device_setting('filter', value)
            expected = Frames().feed(transition['request'].encode())
            self.assertEqual(Frames().feed(tcp.socket.sendall.call_args.args[0]), expected)
            self.assertEqual(Frames().feed(frame(*ws.send.call_args.args)), expected)
            [(tag, payload)] = Frames().feed(transition['reply'].encode())
            self.assertEqual(tag, 'a603')
            self.assertEqual(setting_value('filter', payload), value)
        self.assertEqual(transitions[-1]['value'], 1)
        for reading in observed['reads']:
            self.assertEqual(Frames().feed(reading['request'].encode()), [('0603', b'0000')])
            replies = Frames().feed(''.join(reading['replies']).encode())
            self.assertEqual(replies, [('a603', b'0001'), ('a603', b'000A')])
            self.assertEqual([setting_value('filter', payload) for _, payload in replies], [1, 1])

    def test_physical_peq_compact_edit_master_and_reset_reads(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_peq_save_reset.json').read_text())
        latest, earlier = observed['captures']

        def frames(capture, tag):
            return [Frames().feed(f['wire'].encode())[0][1]
                    for f in capture['frames'] if f['tag'] == tag]

        # Captured form has an extension, one 8-byte record and a trailing 00
        # ignored by this firmware's floor(hex-length / 16) record count.
        for capture, gain, frequency in [(latest, -34, 32), (earlier, 0, 2036)]:
            [payload] = frames(capture, '0678')
            self.assertEqual(payload[:4], b'0000')
            raw = bytes.fromhex(payload[4:].decode())
            self.assertEqual(struct.unpack('>BBhHHB', raw), (0, 0, gain, frequency, 70, 0))
            # Existing JSON writes express the same fields without the compact
            # form's different layout and trailing byte.
            band = dict(position=0, filterType=0, frequency=frequency,
                        gain=gain / 10, qValue=.7)
            encoded = peq_payload([band])
            self.assertEqual(encoded[:4], '0001')
            self.assertEqual(json.loads(encoded[4:]),
                             [dict(band, gain=str(gain / 10), qValue='0.7')])
        [master] = frames(latest, '0630')
        self.assertEqual(setting_value('eq_master_db', master), -6.1)
        self.assertEqual(setting_command('eq_master_db', -6.1), ('0630', master.decode()))
        self.assertEqual(frames(latest, '0626'), [b'0000'] * 3)
        self.assertEqual(frames(latest, '0675'), [b'0000'])
        self.assertEqual(frames(earlier, '0626'), [])
        reset_index = next(i for i, f in enumerate(latest['frames']) if f['tag'] == '0675')
        after = {'frames': latest['frames'][reset_index + 1:]}
        profiles = [peq_value(body) for body in frames(after, 'a628')]
        defaults = [dict(position=p, filterType=0, frequency=f, gain=0.0, qValue=.71)
                    for p, f in enumerate((32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000))]
        self.assertEqual(profiles, [defaults, defaults, [dict(b, qValue=.7) for b in defaults]])
        self.assertEqual([setting_value('eq_master_db', b) for b in frames(after, 'a629')],
                         [0.0, 0.0, 0.0])

    def test_stock_gain_filter_label_values(self):
        self.assertEqual(GAIN_LABELS, {0: 'Low', 1: 'High'})
        self.assertEqual(list(FILTER_LABELS.values()),
                         ['FAST_LL', 'SLOW_LL', 'SLOW_PC', 'FAST_PC', 'NON_OS', 'Wideband_FF'])
        for value in GAIN_LABELS:
            self.assertEqual(setting_command('gain', value), ('0649', f'{value:04X}'))
            self.assertEqual(setting_value('gain', f'{value:04X}'.encode()), value)
        for value in FILTER_LABELS:
            self.assertEqual(setting_command('filter', value), ('0653', f'{value + 9:04X}'))
            for wire in (value, value + 9):
                self.assertEqual(setting_value('filter', f'{wire:04X}'.encode()), value)

    async def test_local_apply_range_payload_is_not_replayed_as_a_supported_setter(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_peq_local_apply.json').read_text())
        [(master_tag, master_body)] = Frames().feed(fixture['apply'][0]['wire'].encode())
        [(band_tag, band_body)] = Frames().feed(fixture['apply'][1]['wire'].encode())
        self.assertEqual((master_tag, band_tag), ('0630', '0678'))
        self.assertEqual(setting_value('eq_master_db', master_body), -6.5)
        intended = peq_value(band_body)
        self.assertEqual([b['frequency'] for b in intended],
                         [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000])
        self.assertEqual([b['gain'] for b in intended], [-3.5] + [0.0] * 9)
        # App supplies the getter's 72-byte range layout; the reviewed setter's
        # compact decoder instead consumes nine 8-byte records. The first
        # record targets position 9, explaining why this must not be replayed.
        raw = bytes.fromhex(band_body[4:].decode())
        self.assertEqual(len(raw), 72)
        self.assertEqual(struct.unpack_from('>BBhHH', raw), (0, 9, -35, 32, 70))
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.device_setting = Mock(return_value=169)
        ws = WSClient()
        ws.device_setting = AsyncMock(return_value=169)
        ws.send = AsyncMock()
        tcp.set_peq(intended)
        await ws.set_peq(intended)
        for tag, payload in [Frames().feed(tcp.socket.sendall.call_args.args[0])[0],
                             Frames().feed(frame(*ws.send.call_args.args))[0]]:
            self.assertEqual(tag, '0678')
            self.assertEqual(payload[:4], b'000A')
            self.assertNotEqual(payload, band_body)
            encoded = json.loads(payload[4:])
            self.assertEqual([dict(b, gain=float(b['gain']), qValue=float(b['qValue']))
                              for b in encoded], intended)

    def test_physical_local_save_retains_edited_profile_then_reset_without_device_save(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_peq_local_save.json').read_text())

        def payload(record, expected_tag):
            [(tag, body)] = Frames().feed(record['wire'].encode())
            self.assertEqual(tag, expected_tag)
            return body

        original = peq_value(payload(observed['baseline']['bands'], 'a628'))
        expected = [dict(b) for b in original]
        expected[0]['gain'] = -3.5
        self.assertEqual(peq_value(payload(observed['reselected_edit']['bands'], 'a628')), expected)
        self.assertEqual(setting_value('eq_master_db', payload(observed['master_write'], '0630')), -6.5)
        self.assertEqual(setting_value('eq_master_db', payload(observed['master_reply'], 'a629')), -6.5)
        self.assertEqual(setting_value('eq_master_db',
                                      payload(observed['reselected_edit']['master'], 'a629')), -6.5)
        raw = bytes.fromhex(payload(observed['band_write'], '0678')[4:].decode())
        self.assertEqual(struct.unpack('>BBhHHB', raw), (0, 0, -35, 32, 70, 0))
        self.assertNotIn('0626', observed['app_request_tags'])
        self.assertEqual(observed['app_request_tags'].count('0678'), 1)
        self.assertEqual(observed['app_request_tags'].count('0630'), 1)
        self.assertEqual(peq_value(payload(observed['reset']['bands'], 'a628')),
                         [dict(b, qValue=.71) for b in original])
        self.assertEqual(peq_value(payload(observed['reselected_reset']['bands'], 'a628')), original)
        self.assertEqual(setting_value('eq_master_db',
                                      payload(observed['reselected_reset']['master'], 'a629')), 0.0)
        self.assertEqual(payload(observed['reselected_reset']['selection_reply'], 'a639'), b'00A9')

    async def test_read_only_and_local_only_preferences_never_send_setters(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        for name in ('gapless', 'folder_jump', 'replay_gain', 'artist_class_type',
                     'track_display', 'list_oper_mode'):
            for value in (-1, 0, 1, 2, True, 1.0, '1', None):
                with self.assertRaises(ValueError):
                    tcp.set_device_setting(name, value)
                with self.assertRaises(ValueError):
                    await ws.set_device_setting(name, value)
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_called()

    async def test_preferences_read_common_snapshot_tcp_ws(self):
        tcp = Client.__new__(Client)
        tcp.request = Mock()
        ws = WSClient()
        ws.request = AsyncMock()
        for name, field in SETTING_FIELDS.items():
            for value in SETTINGS[name][2]:
                snapshot = {field: value if name == 'replay_gain' else bool(value)}
                tcp.request.return_value = ws.request.return_value = json.dumps(snapshot).encode()
                self.assertEqual(tcp.device_setting(name), value)
                self.assertEqual(await ws.device_setting(name), value)
                tcp.request.assert_called_with('0501')
                ws.request.assert_awaited_with('0501')

    def test_preference_snapshot_validation(self):
        for name, field in SETTING_FIELDS.items():
            for payload in (b'{}', b'[]', b'null', b'0001', b'{',
                            json.dumps({field: '1'}).encode(),
                            json.dumps({field: 1.0}).encode(),
                            json.dumps({field: None}).encode(),
                            json.dumps({field: -1}).encode(),
                            json.dumps({field: 3}).encode()):
                with self.subTest(name=name, payload=payload), self.assertRaises(ValueError):
                    setting_value(name, payload)
        with self.assertRaises(ValueError):
            setting_value('replay_gain', b'{"replayGain":true}')
        for name in ('gapless', 'folder_jump'):
            for value in (0, 1):
                self.assertEqual(setting_value(name, json.dumps({SETTING_FIELDS[name]: value}).encode()), value)

    async def test_local_only_preferences_never_send_a_getter(self):
        tcp = Client.__new__(Client)
        tcp.request = Mock()
        ws = WSClient()
        ws.request = AsyncMock()
        for name in ('artist_class_type', 'track_display', 'list_oper_mode'):
            with self.assertRaisesRegex(ValueError, 'unsupported device setting'):
                tcp.device_setting(name)
            with self.assertRaisesRegex(ValueError, 'unsupported device setting'):
                await ws.device_setting(name)
            with self.assertRaises(ValueError):
                setting_value(name, b'0000')
        tcp.request.assert_not_called()
        ws.request.assert_not_called()

    def observed_modes(self):
        return json.loads((Path(__file__).parent / 'fixtures' /
                           'fiio_control_ios_460_modes.json').read_text())

    async def test_modes_match_physical_ios_capture(self):
        observed = self.observed_modes()
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        parser = Frames()
        def normalized(wire):
            # Only the ASCII-hex header is case-insensitive; preserve payload bytes.
            return wire[:8].lower() + wire[8:]
        self.assertEqual(normalized(frame('0599', '0000').decode()),
                         normalized(observed['handshake']['request']))
        self.assertEqual(parser.feed(observed['handshake']['reply'].encode()),
                         [('a599', b'0306')])
        for transition in observed['modes']:
            with self.subTest(value=transition['value']):
                tcp.set_device_setting('work_mode', transition['value'])
                await ws.set_device_setting('work_mode', transition['value'])
                self.assertEqual(normalized(tcp.socket.sendall.call_args.args[0].decode()),
                                 normalized(transition['request']))
                self.assertEqual(normalized(frame(*ws.send.call_args.args).decode()),
                                 normalized(transition['request']))
                [(request_tag, request_payload)] = Frames().feed(transition['request'].encode())
                self.assertEqual(request_tag, '0657')
                self.assertEqual(int(request_payload, 16), transition['value'])
                [(tag, payload)] = parser.feed(transition['reply'].encode())
                self.assertEqual(tag, 'a607')
                self.assertEqual(setting_value('work_mode', payload), transition['value'])
        self.assertFalse(parser.buffer)

    def test_physical_disabled_peq_snapshot(self):
        # Stock reports ten zeroed bands while EQ is off, including zero frequency/Q.
        # Reading this state must work even though sending it as a custom EQ is invalid.
        observed = self.observed_modes()['peq']
        [(tag, payload)] = Frames().feed(observed['reply'].encode())
        self.assertEqual(tag, 'a628')
        bands = peq_value(payload)
        self.assertEqual(bands, [dict(position=i, frequency=0, gain=0.0,
                                     qValue=0.0, filterType=0) for i in range(10)])
        with self.assertRaises(ValueError):
            peq_payload(bands)

    async def test_codecs_match_physical_ios_capture(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_460_codecs.json').read_text())
        parser = Frames()
        for reading in observed['initial_reads']:
            self.assertEqual(parser.feed(reading['request'].encode()), [('06d4', b'0000')])
            [(tag, payload)] = parser.feed(reading['reply'].encode())
            self.assertEqual(tag, 'a6d4')
            self.assertEqual(setting_value('bt_source_codec', payload), 4)
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.device_setting = Mock(return_value=8)
        ws = WSClient()
        ws.send = AsyncMock()
        ws.device_setting = AsyncMock(return_value=8)
        for transition in observed['transitions']:
            with self.subTest(codec=transition['label']):
                tcp.set_device_setting('bt_source_codec', transition['value'])
                await ws.set_device_setting('bt_source_codec', transition['value'])
                expected = parser.feed(transition['request'].encode())
                self.assertEqual(Frames().feed(tcp.socket.sendall.call_args.args[0]), expected)
                self.assertEqual(Frames().feed(frame(*ws.send.call_args.args)), expected)
                [(tag, payload)] = parser.feed(transition['reply'].encode())
                self.assertEqual(tag, 'a6d4')
                self.assertEqual(setting_value('bt_source_codec', payload), transition['value'])
        self.assertFalse(parser.buffer)

    async def test_tcp_ws_setting_wire(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.device_setting = Mock(return_value=8)
        ws = WSClient()
        ws.send = AsyncMock()
        ws.device_setting = AsyncMock(return_value=8)
        for name, value, wire in (
            ('gain', 0, b'0649000C0000'), ('dre', 1, b'0812000C0001'),
            ('spdif', 0, b'0823000C0000'), ('filter', 1, b'0653000C000A'),
            ('balance', -20, b'0713000C0014'), ('balance', 0, b'0713000C0000'),
            ('balance', 20, b'0713000C0114'),
            ('eq_type', 160, b'0690000C00A0'), ('eq_master_db', -1, b'0630000CFFF6'),
            ('work_mode', 10, b'0657000C000A'), ('bt_source_codec', 4, b'06d3000C0004'),
        ):
            tcp.set_device_setting(name, value)
            await ws.set_device_setting(name, value)
            tcp.socket.sendall.assert_called_with(wire)
            self.assertEqual(frame(*ws.send.call_args.args), wire)

    async def test_codec_requires_local_mode(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.device_setting = Mock(return_value=10)
        ws = WSClient()
        ws.send = AsyncMock()
        ws.device_setting = AsyncMock(return_value=1)
        with self.assertRaises(ValueError):
            tcp.set_device_setting('bt_source_codec', 0)
        with self.assertRaises(ValueError):
            await ws.set_device_setting('bt_source_codec', 0)
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_called()

    def test_setting_decoding(self):
        self.assertEqual(setting_value('eq_master_db', b'FFF6'), -1.0)
        self.assertEqual(setting_value('filter', b'000A'), 1)
        self.assertEqual(setting_value('filter', b'0001'), 1)
        for name, value in (('filter', 9), ('gain', True), ('eq_type', 7),
                            ('eq_type', 170), ('eq_master_db', float('nan')),
                            ('eq_master_db', -.01), ('work_mode', 6),
                            ('bt_source_codec', 5), ('reset', 1)):
            with self.assertRaises(ValueError):
                setting_command(name, value)

    def test_peq_binary_schema(self):
        raw = bytes([0, 0]) + struct.pack('>hHHB', -10, 1000, 150, 0)
        self.assertEqual(peq_value(b'0000' + raw.hex().encode()),
            [dict(position=0, frequency=1000, gain=-1.0, qValue=1.5, filterType=0)])
        for payload in (b'', b'00000009', b'0000000A', b'0000xxxx', b'00000000FF'):
            with self.assertRaises(ValueError):
                peq_value(payload)

    def test_balance_range_and_direction(self):
        for value in range(-20, 21):
            tag, payload = setting_command('balance', value)
            self.assertEqual(tag, '0713')
            self.assertEqual(setting_value('balance', payload.encode()), value)
        for payload, expected in ((b'0014', -20), (b'0114', 20),
                                  (b'0001', -1), (b'0101', 1),
                                  (b'0000', 0), (b'0100', 0)):
            self.assertEqual(setting_value('balance', payload), expected)
        for value in (-21, 21, True, 1.0, '1', None):
            with self.assertRaises(ValueError):
                setting_command('balance', value)
        for payload in (b'FFFF', b'0201', b'0015', b'0115', b'000', b'00000'):
            with self.assertRaises(ValueError):
                setting_value('balance', payload)

    async def test_balance_getter_tcp_ws(self):
        tcp = Client.__new__(Client)
        tcp.request = Mock(return_value=b'0014')
        ws = WSClient()
        ws.request = AsyncMock(return_value=b'0114')
        self.assertEqual(tcp.device_setting('balance'), -20)
        self.assertEqual(await ws.device_setting('balance'), 20)
        tcp.request.assert_called_once_with('0712')
        ws.request.assert_awaited_once_with('0712')

    async def test_invalid_balance_never_sends(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        for value in (-21, 21, True, 1.0, '1', None):
            with self.assertRaises(ValueError):
                tcp.set_device_setting('balance', value)
            with self.assertRaises(ValueError):
                await ws.set_device_setting('balance', value)
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_called()

    async def test_peq_requires_complete_valid_fields_and_user_preset(self):
        band = dict(position=0, frequency=1000, gain=-1.0, qValue=1.5, filterType=0)
        expected = '0001[{"position":0,"frequency":1000,"filterType":0,"gain":"-1.0","qValue":"1.5"}]'
        self.assertEqual(peq_payload([band]), expected)
        for value in ([], [dict(position=0)], [band, band],
                      [dict(band, frequency=0)], [dict(band, qValue=float('inf'))],
                      [dict(band, filterType=1)]):
            with self.assertRaises(ValueError):
                peq_payload(value)
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.device_setting = Mock(return_value=255)
        ws = WSClient()
        ws.send = AsyncMock()
        ws.device_setting = AsyncMock(return_value=255)
        with self.assertRaises(ValueError):
            tcp.set_peq([band])
        with self.assertRaises(ValueError):
            await ws.set_peq([band])
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_called()
        tcp.device_setting.return_value = ws.device_setting.return_value = 160
        tcp.set_peq([band])
        await ws.set_peq([band])
        tcp.socket.sendall.assert_called_once_with(frame('0678', expected))
        ws.send.assert_called_once_with('0678', expected)


if __name__ == '__main__':
    unittest.main()
