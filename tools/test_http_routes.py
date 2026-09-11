import struct
import unittest
from inspect_http_routes import routes


class RouteTests(unittest.TestCase):
    def test_elf_segment_mapping_and_table_termination(self):
        data = bytearray(2048)
        data[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 1)
        # Deliberately unrelated to the old virtual-address-minus-0x400000 guess.
        struct.pack_into('<8I', data, 52, 1, 512, 0x6c7a50, 0, 1024, 1024, 4, 4)
        struct.pack_into('<4I', data, 512, 0x6c7a90, 0x6c7a94, 0x484abc, 0)
        data[576:586] = b'GET\0/dir/\0'
        self.assertEqual(routes(data), [dict(method='GET', path='/dir/',
                                            handler='0x00484abc', event='HTTP_MSG')])

    def test_rejects_wrong_binary(self):
        with self.assertRaises(ValueError):
            routes(b'not an ELF')
