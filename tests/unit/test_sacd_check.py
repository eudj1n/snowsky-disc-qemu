import unittest
import io
import struct
from unittest.mock import AsyncMock

from tests.integration.sacd_check import queue_page
from tests.fixtures.sacd_replacement import title_edits


class SacdQueuePaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_thirteen_tracks_keep_positions_across_page_boundary(self):
        # A shared path/ID must not collapse distinct logical rows.
        rows = [dict(itemName=f'Original track {i}', songId=7) for i in range(13)]
        client = AsyncMock()
        client.library.side_effect = [dict(total=13, items=rows[:10]),
                                      dict(total=13, items=rows[10:])]
        self.assertEqual(await queue_page(client), dict(total=13, items=rows))
        self.assertEqual(client.library.call_args_list[1].args, ('queue', 10))

    async def test_changed_or_stalled_page_fails_without_restarting(self):
        for second in (dict(total=12, items=[{}]), dict(total=13, items=[])):
            client = AsyncMock()
            client.library.side_effect = [dict(total=13, items=[{}] * 10), second]
            with self.subTest(second=second), self.assertRaises(AssertionError):
                await queue_page(client)
            self.assertEqual(client.library.await_count, 2)


class SacdReplacementTests(unittest.TestCase):
    def sample(self):
        data = bytearray(550 * 2048)
        data[510 * 2048:510 * 2048 + 10] = b'SACDMTOC\x01\x14'
        struct.pack_into('>II', data, 510 * 2048 + 64, 544, 548)
        for lsn in (544, 548):
            at = lsn * 2048
            data[at:at + 10] = b'TWOCHTOC\x01\x14'
            struct.pack_into('>H', data, at + 10, 2)
            data[at + 32], data[at + 69] = 2, 2
            text = at + 2048
            data[text:text + 8] = b'SACDTTxt'
            struct.pack_into('>H', data, text + 8, 32)
            data[text + 32] = 1
            data[text + 36:text + 47] = b'\x01 Original\0'
        return bytes(data)

    def test_plan_changes_only_equal_length_titles_in_both_tocs(self):
        original = self.sample()
        handle = io.BytesIO(original)
        title, edits = title_edits(handle)
        self.assertEqual(title, 'CI-XXXXX')
        self.assertEqual(len(edits), 2)
        self.assertEqual(handle.getvalue(), original)
        for offset, before, after in edits:
            self.assertEqual(before, b'Original')
            self.assertEqual(len(before), len(after))
            self.assertEqual(original[offset:offset + 8], before)

    def test_rejects_invalid_or_truncated_title_before_any_write(self):
        for position in (2040, 0):
            data = bytearray(self.sample())
            struct.pack_into('>H', data, 545 * 2048 + 8, position)
            with self.assertRaises(ValueError):
                title_edits(io.BytesIO(data))

    def test_text_record_can_live_two_sectors_after_its_table(self):
        data = bytearray(self.sample())
        data.extend(bytes(2 * 2048))
        for lsn in (544, 548):
            struct.pack_into('>H', data, lsn * 2048 + 10, 4)
            text = (lsn + 1) * 2048
            struct.pack_into('>H', data, text + 8, 4096)
            data[text + 4096] = 1
            data[text + 4100:text + 4111] = b'\x01 Original\0'
        title, edits = title_edits(io.BytesIO(data))
        self.assertEqual(title, 'CI-XXXXX')
        self.assertEqual([e[0] for e in edits], [547 * 2048 + 6, 551 * 2048 + 6])
