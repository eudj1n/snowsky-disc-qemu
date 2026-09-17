"""Plan same-size synthetic title edits in a disposable approved SACD copy.

No audio is generated or redistributed. Only the first title in the first text
table of each stereo TOC is changed; no original source should call this helper.
Layout reference: SACD Ripper scarletbook.h / scarletbook_read.c.
"""
import struct


def title_edits(source):
    """Return (new ASCII title, [(offset, before, after)]) without writing."""
    source.seek(510 * 2048)
    master = source.read(2048)
    if len(master) != 2048 or master[:10] != b'SACDMTOC\x01\x14':
        raise ValueError('requires SACD 1.20')
    edits = []
    for lsn in dict.fromkeys(struct.unpack_from('>II', master, 64)):
        if not lsn:
            continue
        source.seek(lsn * 2048)
        header = source.read(2048)
        if len(header) != 2048 or header[:10] != b'TWOCHTOC\x01\x14':
            raise ValueError('requires stereo TOC')
        sectors = struct.unpack_from('>H', header, 10)[0]
        if not 2 <= sectors <= 96 or header[32] != 2 or header[69] < 2:
            raise ValueError('requires multi-track stereo area')
        remainder = source.read((sectors - 1) * 2048)
        if len(remainder) != (sectors - 1) * 2048:
            raise ValueError('truncated stereo TOC')
        for sector in range(1, sectors):
            # Text offsets are relative to SACDTTxt and can reach later sectors
            # of the area (the approved image uses an offset of 4096).
            data = remainder[(sector - 1) * 2048:]
            if data[:8] != b'SACDTTxt':
                continue
            pos = struct.unpack_from('>H', data, 8)[0]
            if not 8 + 2 * header[69] <= pos < len(data) - 6 or not data[pos] or data[pos + 4] != 1:
                raise ValueError('requires title as first text record')
            start = pos + 6
            end = data.find(b'\0', start)
            if not start + 5 <= end <= start + 255:
                raise ValueError('unsupported first title length')
            before = data[start:end]
            after = b'CI-' + b'X' * (len(before) - 3)
            if before == after or (edits and edits[0][2] != after):
                raise ValueError('title already replaced or inconsistent backups')
            edits.append(((lsn + sector) * 2048 + start, before, after))
            break
        else:
            raise ValueError('missing track text')
    if not edits:
        raise ValueError('missing stereo area')
    return edits[0][2].decode('ascii'), edits
