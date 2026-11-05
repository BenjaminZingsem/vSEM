"""Independent paired raw storage oracle; no engine, exposure or clock inputs."""
from dataclasses import FrozenInstanceError
import random
import struct
import unittest

from packages.acquisition.paged_counts import PairedCountPlane, zero_plane


def packed(values):
    return b''.join(struct.pack('<I', v) for v in values)


class CountPagesAcceptance(unittest.TestCase):
    def test_empty_and_zero_planes(self):
        empty = zero_plane(0, 4)
        self.assertIs(type(empty), PairedCountPlane)
        self.assertEqual((empty.pixel_count, empty.page_pixels, empty.pages), (0, 4, ()))
        self.assertEqual(empty.read(0, 0), (b'', b''))
        self.assertIs(empty.write(0, b'', b''), empty)
        plane = zero_plane(9, 4)
        self.assertEqual(plane.pages, (None, None, None))
        self.assertEqual(plane.read(0, 9), (bytes(36), bytes(36)))

    def test_zero_initialization_uses_pages_not_pixel_bytes(self):
        plane = zero_plane(2048*2048)
        self.assertEqual(plane.page_pixels, 1024)
        self.assertEqual(len(plane.pages), 4096)
        self.assertTrue(all(page is None for page in plane.pages))
        self.assertEqual(plane.read(2048*2048-2, 2), (bytes(8), bytes(8)))

    def test_cross_page_pair_preserves_exact_bit_patterns(self):
        old = zero_plane(9, 4)
        new = old.write(3, packed([0, 1, 2**32-1]), packed([2**32-1, 3, 0]))
        self.assertEqual(new.read(2, 5),
            (packed([0, 0, 1, 2**32-1, 0]), packed([0, 2**32-1, 3, 0, 0])))
        self.assertEqual(old.read(0, 9), (bytes(36), bytes(36)))

    def test_last_short_page_and_last_pixel(self):
        plane = zero_plane(10, 4).write(9, packed([123]), packed([2**32-1]))
        self.assertEqual(tuple(len(v) for v in plane.pages[2]), (8, 8))
        self.assertEqual(plane.read(8, 2), (packed([0, 123]), packed([0, 2**32-1])))
        self.assertEqual(plane.read(10, 0), (b'', b''))

    def test_unaffected_populated_pages_share_exact_identity(self):
        before = zero_plane(13, 4).write(0, packed(range(13)), packed(range(13, 26)))
        after = before.write(5, packed([999]), packed([555]))
        for index in (0, 2, 3):
            self.assertIs(after.pages[index], before.pages[index])
        self.assertEqual(before.read(5, 1), (packed([5]), packed([18])))
        self.assertEqual(after.read(5, 1), (packed([999]), packed([555])))

    def test_replacing_with_zeros_and_empty_writes(self):
        plane = zero_plane(6, 2).write(0, packed([1]*6), packed([2]*6))
        zeroed = plane.write(1, bytes(16), bytes(16))
        self.assertEqual(zeroed.read(0, 6), (packed([1, 0, 0, 0, 0, 1]), packed([2, 0, 0, 0, 0, 2])))
        for position in (0, 3, 6):
            self.assertIs(plane.write(position, b'', b''), plane)

    def test_snapshot_is_frozen_and_has_only_immutable_pages(self):
        plane = zero_plane(5, 2).write(0, packed(range(5)), packed(range(5)))
        for name, value in (('pixel_count', 1), ('page_pixels', 1), ('pages', ())):
            with self.subTest(name=name), self.assertRaises((FrozenInstanceError, AttributeError)):
                setattr(plane, name, value)
        self.assertIs(type(plane.pages), tuple)
        for page in plane.pages:
            self.assertIs(type(page), tuple)
            self.assertTrue(all(type(value) is bytes for value in page))

    def test_constructor_exact_shapes_and_short_page_lengths(self):
        good = PairedCountPlane(3, 2, ((bytes(8), bytes(8)), (bytes(4), bytes(4))))
        self.assertEqual(good.read(0, 3), (bytes(12), bytes(12)))
        bad = [(), (None,), (None, None, None), [None, None],
               ((bytes(8),), None), ((bytes(4), bytes(8)), None),
               (None, (bytes(8), bytes(8))), ([bytes(8), bytes(8)], None),
               ((bytearray(8), bytes(8)), None), (None, False)]
        for pages in bad:
            with self.subTest(pages=repr(pages)), self.assertRaises(ValueError):
                PairedCountPlane(3, 2, pages)

    def test_exact_integer_envelope(self):
        class IntChild(int):
            pass
        for value in (True, False, 1.0, '1', None, IntChild(1), -1, 2**53):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                zero_plane(value, 2)
            with self.subTest(page=repr(value)), self.assertRaises(ValueError):
                zero_plane(2, value)
        with self.assertRaises(ValueError):
            zero_plane(2, 0)
        self.assertEqual(zero_plane(1, 2**53-1).pages, (None,))

    def test_range_and_alignment_rejection_leave_original_pair_unchanged(self):
        plane = zero_plane(7, 3).write(0, packed(range(7)), packed(range(7, 14)))
        before = plane.read(0, 7)
        bad = [(-1, b'', b''), (8, b'', b''), (7, bytes(4), bytes(4)),
               (0, bytes(3), bytes(3)), (0, bytes(4), bytes(8)), (6, bytes(8), bytes(8))]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                plane.write(*args)
            self.assertEqual(plane.read(0, 7), before)
        for args in ((-1, 0), (0, -1), (8, 0), (7, 1), (6, 2)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                plane.read(*args)

    def test_method_exact_types_no_subclass_or_mutable_bytes(self):
        class IntChild(int):
            pass
        class BytesChild(bytes):
            pass
        plane = zero_plane(4, 2)
        for value in (True, 1.0, IntChild(1), None, '1', 2**53):
            with self.subTest(start=repr(value)), self.assertRaises(ValueError):
                plane.write(value, bytes(4), bytes(4))
            with self.subTest(read=repr(value)), self.assertRaises(ValueError):
                plane.read(value, 0)
            with self.subTest(count=repr(value)), self.assertRaises(ValueError):
                plane.read(0, value)
        for data in (BytesChild(bytes(4)), bytearray(4), memoryview(bytes(4)), None, []):
            with self.subTest(se=type(data)), self.assertRaises(ValueError):
                plane.write(0, data, bytes(4))
            with self.subTest(bse=type(data)), self.assertRaises(ValueError):
                plane.write(0, bytes(4), data)

    def test_constructor_rejects_tuple_and_bytes_subclasses(self):
        class TupleChild(tuple):
            pass
        class BytesChild(bytes):
            pass
        for pages in (TupleChild((None,)), (TupleChild((bytes(8), bytes(8))),),
                      ((BytesChild(bytes(8)), bytes(8)),)):
            with self.subTest(pages=type(pages)), self.assertRaises(ValueError):
                PairedCountPlane(2, 2, pages)

    def test_independent_random_bytearray_oracle_and_persistent_snapshots(self):
        rng = random.Random(20261014)
        count = 1031
        plane = zero_plane(count, 37)
        se, bse = bytearray(4*count), bytearray(4*count)
        saved = []
        for iteration in range(400):
            first = rng.randrange(count+1)
            length = rng.randrange(min(173, count-first)+1)
            a, b = packed(rng.getrandbits(32) for _ in range(length)), packed(rng.getrandbits(32) for _ in range(length))
            old = plane
            plane = plane.write(first, a, b)
            se[4*first:4*(first+length)], bse[4*first:4*(first+length)] = a, b
            self.assertEqual(plane.read(0, count), (bytes(se), bytes(bse)))
            touched = set(range(first//37, (first+length-1)//37+1)) if length else set()
            for page in range(len(plane.pages)):
                if page not in touched:
                    self.assertIs(plane.pages[page], old.pages[page])
            start = rng.randrange(count+1)
            span = rng.randrange(count-start+1)
            self.assertEqual(plane.read(start, span), (bytes(se[4*start:4*(start+span)]), bytes(bse[4*start:4*(start+span)])))
            if iteration % 79 == 0:
                saved.append((plane, bytes(se), bytes(bse)))
        for snapshot, a, b in saved:
            self.assertEqual(snapshot.read(0, count), (a, b))


if __name__ == '__main__':
    unittest.main()
