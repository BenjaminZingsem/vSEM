"""Independent malformed-asset cases for the narrow publication PNG allowance."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from scripts.audit_publication import screenshot_manifest, validate_screenshot


def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)


def png(extra=b'', raster=b'\x00\x12\x34\x56'):
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+
        extra+chunk(b'IDAT',zlib.compress(raster))+chunk(b'IEND',b''))


def entry(raw):
    return {'file':'example.png','sha256':hashlib.sha256(raw).hexdigest(),'width':1,'height':1}


class ScreenshotPublicationTests(unittest.TestCase):
    def test_minimal_rgb_png_is_accepted(self):
        raw=png();validate_screenshot(raw,entry(raw))

    def test_embedded_text_is_rejected_even_with_matching_hash(self):
        raw=png(chunk(b'tEXt',b'Comment\x00not publishable'))
        with self.assertRaisesRegex(ValueError,'metadata'):validate_screenshot(raw,entry(raw))

    def test_trailing_bytes_and_crc_corruption_are_rejected(self):
        for raw in (png()+b'extra',png()[:-1]+b'X'):
            with self.subTest(raw=raw[-6:]),self.assertRaises(ValueError):
                validate_screenshot(raw,entry(raw))

    def test_hash_and_dimensions_must_match_review_record(self):
        raw=png()
        for changed in ({'sha256':'0'*64},{'width':2}):
            item=entry(raw);item.update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                validate_screenshot(raw,item)

    def test_truncated_and_excess_raster_are_rejected(self):
        for raster in (b'\x00',b'\x00'+b'x'*1000):
            raw=png(raster=raster)
            with self.subTest(length=len(raster)),self.assertRaisesRegex(ValueError,'raster length'):
                validate_screenshot(raw,entry(raw))

    def test_manifest_cannot_escape_asset_directory_or_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'docs/screenshots';directory.mkdir(parents=True)
            item=entry(png())
            for items in ([{**item,'file':'../escape.png'}],[item,item], [{**item,'width':True}]):
                (directory/'captures.json').write_text(json.dumps({'captures':items}))
                with self.subTest(items=items),self.assertRaises(ValueError):screenshot_manifest(root)


if __name__=='__main__':unittest.main()
