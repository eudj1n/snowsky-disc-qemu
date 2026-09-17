"""Guarded custom-playlist selection shared by TCP and WebSocket clients.

HTTP and Link must address the same DISC. Reads are best-effort preflight, not
an atomic revision check: serialize list edits/selection and never replay a write.
"""
import json


def playlist_command(position, index, expected_name):
    if type(position) is not int or not 0 <= position <= 0x7fffffff:
        raise ValueError('playlist position outside 0..2147483647')
    if index is not None and (type(index) is not int or not 0 <= index <= 65535):
        raise ValueError('track position outside 0..65535')
    if not isinstance(expected_name, str) or not expected_name or '\0' in expected_name:
        raise ValueError('expected playlist name is required')
    prefix = '' if index is None else f'{index:04X}'
    return ('0101' if index is None else '0100',
            prefix + '0005' + json.dumps({'id': position}, separators=(',', ':')))


def verify_playlist(http, position, index, expected_name):
    """Check current list name, nonempty track position, then name again."""
    def row(page, wanted):
        total, items = page['total'], page['items']
        if type(total) is not int or not 0 <= wanted < total or len(items) != 1:
            raise ValueError('position outside the current playlist catalog')
        item = items[0]
        if type(item.get('pos')) is not int or item['pos'] != wanted:
            raise ValueError('unexpected playlist catalog position')
        return item

    def check_name():
        item = row(http.catalog('custom', offset=position, limit=1), position)
        if item.get('name') != expected_name:
            raise ValueError('playlist changed; refresh its position and name')

    check_name()
    wanted = 0 if index is None else index
    row(http.catalog('custom/song', offset=wanted, limit=1, src_list_id=position), wanted)
    check_name()
