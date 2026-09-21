import struct
import unittest
from research.diagnostics.inspect_http_routes import parse_routes, routes


class RouteTests(unittest.TestCase):
    def fixture(self, table):
        data = bytearray(2048)
        data[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 2)
        # Neither segment follows a virtual-address-minus-0x400000 assumption.
        struct.pack_into('<8I', data, 52, 1, 512, table, 0, 1024, 1024, 4, 4)
        struct.pack_into('<8I', data, 84, 1, 1536, 0x484abc, 0, 512, 512, 5, 4)
        struct.pack_into('<4I', data, 512, table + 64, table + 68, 0x484abc, 0)
        data[576:586] = b'GET\0/dir/\0'
        return data, dict(table=hex(table), count=1)

    def test_segment_mapping_for_both_tables(self):
        for table in (0x6c7a50, 0x6d2580):
            data, layout = self.fixture(table)
            self.assertEqual(parse_routes(data, layout), [dict(method='GET', path='/dir/',
                                             handler='0x00484abc', event='HTTP_MSG')])

    def test_rejects_wrong_binary_even_with_plausible_table(self):
        for data in (b'not an ELF', self.fixture(0x6c7a50)[0]):
            with self.assertRaises(ValueError):
                routes(data)

    def test_rejects_wrong_count_handler_event_and_string_range(self):
        for field, value in ((8, 0x6c7a50), (12, 2), (4, 0x12345678)):
            data, layout = self.fixture(0x6c7a50)
            struct.pack_into('<I', data, 512 + field, value)
            with self.assertRaises(ValueError):
                parse_routes(data, layout)
        data, layout = self.fixture(0x6c7a50)
        layout['count'] = 2
        with self.assertRaises(ValueError):
            parse_routes(data, layout)

    def test_rejects_truncated_elf(self):
        data, layout = self.fixture(0x6c7a50)
        for end in (10, 80, 1600):
            with self.assertRaises(ValueError):
                parse_routes(data[:end], layout)
