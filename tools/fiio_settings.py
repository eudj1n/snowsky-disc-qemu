"""Validated DISC setting/PEQ encodings shared by TCP and WS clients."""
import json
import math
import struct


# Verified V2.57 stock UI labels, keyed by helper/SQLite value, not menu position.
# FiiO Control's expanded filter names still need a paired label/wire capture.
GAIN_LABELS = {0: 'Low', 1: 'High'}
FILTER_LABELS = {0: 'FAST_LL', 1: 'SLOW_LL', 2: 'SLOW_PC',
                 3: 'FAST_PC', 4: 'NON_OS', 5: 'Wideband_FF'}


SETTINGS = {
    'gain': ('064a', '0649', (0, 1)),
    'dre': ('0813', '0812', (0, 1)),
    'spdif': ('0824', '0823', (0, 1)),
    'balance': ('0712', '0713', tuple(range(-20, 21))),
    'filter': ('0603', '0653', tuple(range(6))),
    'eq_type': ('0639', '0690', (255, 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, *range(160, 170))),
    'eq_master_db': ('0629', '0630', None),
    # Only modes present in DISC's FiiO Control UI are exposed.
    'work_mode': ('0607', '0657', (1, 8, 10)),
    'bt_source_codec': ('06d4', '06d3', tuple(range(5))),
    # These three are fields of the common a501 JSON, not individual replies.
    # The local UI setters are NOT admitted by the stock TCP allowlist.
    'gapless': ('0501', None, (0, 1)),
    'folder_jump': ('0501', None, (0, 1)),
    'replay_gain': ('0501', None, (0, 1, 2)),  # off / album / track
}

SETTING_FIELDS = {'gapless': 'gaplessPlay', 'folder_jump': 'folderJump',
                  'replay_gain': 'replayGain'}


def spec(name):
    if name not in SETTINGS:
        raise ValueError('unsupported device setting')
    return SETTINGS[name]


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'expected finite number in {low}..{high}')
    return value


def setting_query(name):
    tag = spec(name)[0]
    if tag is None:
        raise ValueError(f'{name} has no validated remote getter')
    return tag


def setting_command(name, value):
    _, tag, values = spec(name)
    if tag is None:
        raise ValueError('setting is read-only in this client')
    if name == 'eq_master_db':
        number(value, -24, 12)
        scaled = round(value * 10)
        if not math.isclose(value * 10, scaled, abs_tol=1e-6):
            raise ValueError('master gain requires 0.1 dB steps')
        value = scaled & 0xffff
    else:
        if type(value) is not int or value not in values:
            raise ValueError('unsupported setting value')
        if name == 'filter':
            value += 9  # Link enum 9..14; device/UI enum 0..5.
        elif name == 'balance':
            # Stock UI: L20..0..R20. High byte 1 = right, 0 = left;
            # low byte is attenuation steps, NOT a signed 16-bit number.
            value = 0x100 + value if value > 0 else -value
    return tag, f'{value:04X}'


def setting_value(name, payload):
    setting_query(name)
    if name in SETTING_FIELDS:
        snapshot = json.loads(payload)
        field = SETTING_FIELDS[name]
        if not isinstance(snapshot, dict) or field not in snapshot:
            raise ValueError(f'missing setting field {field}')
        value = snapshot[field]
        # Stock cJSON uses booleans for switches and a number for ReplayGain.
        if name != 'replay_gain' and type(value) is bool:
            value = int(value)
        if type(value) is not int or value not in spec(name)[2]:
            raise ValueError(f'unknown {field} value')
        return value
    if len(payload) != 4:
        raise ValueError('expected four hexadecimal setting digits')
    value = int(payload, 16)
    if name == 'balance':
        direction, steps = value >> 8, value & 0xff
        if direction not in (0, 1) or steps > 20:
            raise ValueError('unknown balance encoding')
        return steps if direction else -steps
    if name == 'eq_master_db':
        return (value if value < 32768 else value - 65536) / 10
    if name == 'filter':
        # A query can send both device enum and Link enum notifications.
        if 9 <= value <= 14:
            value -= 9
        if not 0 <= value <= 5:
            raise ValueError('unknown filter enum')
    return value


def peq_payload(bands):
    if not isinstance(bands, list) or not 1 <= len(bands) <= 10:
        raise ValueError('expected 1..10 PEQ bands')
    positions = set()
    result = []
    for band in bands:
        if not isinstance(band, dict) or set(band) != {'position', 'frequency', 'gain', 'qValue', 'filterType'}:
            raise ValueError('PEQ requires position, frequency, gain, qValue and filterType')
        position, frequency = band['position'], band['frequency']
        if type(position) is not int or not 0 <= position <= 9 or position in positions:
            raise ValueError('PEQ positions must be unique integers in 0..9')
        positions.add(position)
        if type(frequency) is not int or not 20 <= frequency <= 20000:
            raise ValueError('frequency must be integer Hz in 20..20000')
        if type(band['filterType']) is not int or band['filterType'] != 0:
            raise ValueError('only stock peaking filter type 0 is validated')
        gain = number(band['gain'], -24, 12)
        quality = number(band['qValue'], .1, 20)
        # Stock JSON parser requires STRINGS for gain and qValue.
        result.append(dict(position=position, frequency=frequency, filterType=0,
                           gain=str(float(gain)), qValue=str(float(quality))))
    return f'{len(result):04X}' + json.dumps(result, separators=(',', ':'))


def peq_value(payload):
    # a628: four-digit extension, then hex bytes [first,last, 7 bytes/band].
    if len(payload) < 8 or payload[:4] != b'0000':
        raise ValueError('unsupported PEQ envelope')
    raw = bytes.fromhex(payload[4:].decode('ascii'))
    first, last = raw[:2]
    if not 0 <= first <= last <= 9 or len(raw) != 2 + (last - first + 1) * 7:
        raise ValueError('invalid PEQ range or record size')
    bands = []
    for index in range(last - first + 1):
        gain, frequency, quality, kind = struct.unpack_from('>hHHB', raw, 2 + 7 * index)
        bands.append(dict(position=first + index, frequency=frequency, gain=gain / 10,
                          qValue=quality / 100, filterType=kind))
    return bands
