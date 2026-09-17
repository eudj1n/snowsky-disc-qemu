"""Conservative stock DISC lock-screen requests; see docs/REMOTE_MODES_THEMES.md."""
from pathlib import Path
import re
import struct
from urllib.parse import quote


ROUTE = '/image/lock_screen/'
CUSTOM_STYLES = ('default/0', 'default/1', 'default/2', 'clock/0')
FIELDS = ('alias', 'x-fields-to-update', 'back-groud', 'lock-screen', 'msg-style',
          'front-color', 'flag-in-use', 'file-source', 'subclass', 'content-type')


def read_lock_screen(http, slot=0, *, system=False, preview=False):
    if type(system) is not bool or type(preview) is not bool:
        raise ValueError('system and preview must be booleans')
    # Current DISC profiles advertise one custom and five system slots.
    if type(slot) is not int or not 0 <= slot < (5 if system else 1):
        raise ValueError('unsupported DISC lock-screen slot')
    return http.request('GET', ROUTE, headers={
        'x-fields-to-update': str(slot),
        'file-source': 'lock_screen/system' if system else 'lock_screen/custom',
        'preview-flag': str(int(preview)),
    })


def upload_lock_screen(http, source, *, alias='', alpha=100,
                       show_time=True, show_date=True, show_battery=True,
                       show_id3=False, color=(255, 255, 255), style='default/0'):
    """Replace AND activate custom slot 0. Always send the complete PNG and metadata.

    Stock empty-body custom updates clear the image path. Even flag-in-use=0
    clears another active theme, so this helper intentionally activates its upload.
    A 200 response is not success: read the original back with preview=False.
    V2.57 custom styles are allowlisted; style never implicitly changes flags.
    """
    if not isinstance(style, str) or style not in CUSTOM_STYLES:
        raise ValueError('unsupported DISC custom lock-screen style')
    # Stock copies at most 63 header bytes, then percent-decodes; exceeding
    # this can persist truncated/invalid UTF-8 even though HTTP returns 200.
    if (not isinstance(alias, str) or any(ord(c) < 32 for c in alias)
            or len(quote(alias, safe='')) > 63):
        raise ValueError('alias must fit the 63-byte percent-encoded stock header')
    if type(alpha) is not int or not 0 <= alpha <= 100:
        raise ValueError('alpha must be an integer in 0..100')
    flags = (show_time, show_date, show_battery, show_id3)
    if any(type(flag) is not bool for flag in flags):
        raise ValueError('overlay flags must be booleans')
    if not isinstance(color, (tuple, list)) or len(color) != 3 or any(
            type(c) is not int or not 0 <= c <= 255 for c in color):
        raise ValueError('color must contain three integer bytes')
    data = Path(source).read_bytes()
    if (len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n'
            or data[12:16] != b'IHDR' or struct.unpack('>II', data[16:24]) != (360, 360)):
        raise ValueError('only 360x360 PNG lock-screen uploads are validated')
    return http.request('POST', ROUTE, body=data, headers={
        'content-type': 'image/png', 'x-fields-to-update': '0',
        'alias': quote(alias, safe=''), 'back-groud': f'alpha={alpha}',
        'lock-screen': ';'.join(f'{name}={int(value)}' for name, value in
                               zip(('time', 'date', 'battery', 'id3'), flags)),
        'front-color': 'r=%d;g=%d;b=%d' % tuple(color),
        'msg-style': style, 'flag-in-use': '1',
        'file-source': 'lock_screen/custom', 'subclass': 'lock_screen/custom/default',
    })


def _system_snapshot(http, slot):
    reply = read_lock_screen(http, slot, system=True)
    if (reply.status != 200 or not reply.body or any(key not in reply.headers for key in FIELDS)
            or reply.headers['file-source'] != 'lock_screen/system'
            or reply.headers['x-fields-to-update'] != str(slot)
            or any(not isinstance(reply.headers[k], str) or
                   any(ord(c) < 32 for c in reply.headers[k]) for k in FIELDS)):
        raise ValueError('incomplete or mismatched stock theme response')
    return reply


def select_system_lock_screen(http, slot=0):
    """Select a stock image, preserving the metadata returned for that slot."""
    reply = _system_snapshot(http, slot)
    headers = {key: reply.headers[key] for key in FIELDS}
    # Response aliases may be raw ASCII or percent-encoded. Preserve wire spelling.
    headers['flag-in-use'] = '1'
    return http.request('POST', ROUTE, body=b'', headers=headers)


def update_system_lock_screen(http, slot=0, *, alpha=None, color=None, style=None,
                              show_time=None, show_date=None, show_battery=None,
                              show_id3=None):
    """Edit AND activate a system slot; None leaves that field unchanged.

    Read fresh metadata/original bytes, send an empty-body system POST, then
    verify all metadata and original bytes. Return the verified GET reply.
    Serialize with other writers: stock has no compare-and-swap. Never retry a
    failed/uncertain write automatically. A verification error may follow an
    applied update; reread state before deciding what to do. A locked physical
    screen may need unlock/relock to repaint. Custom uploads use a separate API.
    """
    flags = (show_time, show_date, show_battery, show_id3)
    if alpha is not None and (type(alpha) is not int or not 0 <= alpha <= 100):
        raise ValueError('alpha must be an integer in 0..100')
    if color is not None and (not isinstance(color, (tuple, list)) or len(color) != 3 or
                             any(type(c) is not int or not 0 <= c <= 255 for c in color)):
        raise ValueError('color must contain three integer bytes')
    if style is not None and (not isinstance(style, str) or style not in CUSTOM_STYLES):
        raise ValueError('unsupported DISC system lock-screen style')
    if any(flag is not None and type(flag) is not bool for flag in flags):
        raise ValueError('overlay flags must be booleans')
    if all(value is None for value in (alpha, color, style, *flags)):
        raise ValueError('at least one theme edit is required')
    before = _system_snapshot(http, slot)
    headers = {key: before.headers[key] for key in FIELDS}
    if alpha is not None:
        headers['back-groud'] = f'alpha={alpha}'
    if color is not None:
        headers['front-color'] = 'r=%d;g=%d;b=%d' % tuple(color)
    if style is not None:
        headers['msg-style'] = style
    if any(flag is not None for flag in flags):
        match = re.fullmatch(r'time=([01]);date=([01]);battery=([01]);id3=([01])',
                             headers['lock-screen'])
        if match is None:
            raise ValueError('unrecognized stock overlay flags')
        headers['lock-screen'] = ';'.join(
            f'{name}={old if value is None else int(value)}'
            for name, old, value in zip(('time', 'date', 'battery', 'id3'),
                                        match.groups(), flags))
    headers['flag-in-use'] = '1'
    posted = http.request('POST', ROUTE, body=b'', headers=headers)
    if posted.status != 200:
        raise OSError('system theme update failed; state may have changed')
    after = _system_snapshot(http, slot)
    if after.body != before.body or any(after.headers[k] != v for k, v in headers.items()):
        raise OSError('system theme readback differs; state may have changed')
    return after
