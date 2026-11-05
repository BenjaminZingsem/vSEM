from dataclasses import dataclass

_MAX_INT = 9007199254740991


def _check_int(value, name):
    if type(value) is not int:
        raise ValueError(f"{name} must be an exact int")
    if value < 0 or value > _MAX_INT:
        raise ValueError(f"{name} out of range")


def _check_bytes(value, name):
    if type(value) is not bytes:
        raise ValueError(f"{name} must be exact bytes")


@dataclass(frozen=True)
class PairedCountPlane:
    pixel_count: int
    page_pixels: int
    pages: tuple

    def __init__(self, pixel_count, page_pixels, pages):
        _check_int(pixel_count, "pixel_count")
        _check_int(page_pixels, "page_pixels")
        if page_pixels <= 0:
            raise ValueError("page_pixels must be positive")

        if type(pages) is not tuple:
            raise ValueError("pages must be an exact tuple")

        expected_pages = (pixel_count + page_pixels - 1) // page_pixels if pixel_count > 0 else 0
        if len(pages) != expected_pages:
            raise ValueError("pages length mismatch")

        for i, entry in enumerate(pages):
            if entry is None:
                continue
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("populated page must be an exact 2-tuple")
            se, bse = entry
            _check_bytes(se, "se")
            _check_bytes(bse, "bse")
            if len(se) != len(bse):
                raise ValueError("paired byte lengths must be equal")
            if len(se) % 4 != 0:
                raise ValueError("byte length must be divisible by 4")
            page_pixel_count = min(page_pixels, pixel_count - i * page_pixels)
            if len(se) != 4 * page_pixel_count:
                raise ValueError("page byte length mismatch")

        object.__setattr__(self, "pixel_count", pixel_count)
        object.__setattr__(self, "page_pixels", page_pixels)
        object.__setattr__(self, "pages", pages)

    def write(self, first_pixel, se_u32le, bse_u32le):
        _check_int(first_pixel, "first_pixel")
        _check_bytes(se_u32le, "se_u32le")
        _check_bytes(bse_u32le, "bse_u32le")

        if len(se_u32le) != len(bse_u32le):
            raise ValueError("paired byte lengths must be equal")
        if len(se_u32le) % 4 != 0:
            raise ValueError("byte length must be divisible by 4")

        count_pixels = len(se_u32le) // 4
        if first_pixel + count_pixels > self.pixel_count:
            raise ValueError("write range out of bounds")

        if count_pixels == 0:
            return self

        pages_list = list(self.pages)
        first_page = first_pixel // self.page_pixels
        last_page = (first_pixel + count_pixels - 1) // self.page_pixels

        for p in range(first_page, last_page + 1):
            page_start = p * self.page_pixels
            page_end = min(page_start + self.page_pixels, self.pixel_count)
            page_pixel_count = page_end - page_start

            overlap_start = max(first_pixel, page_start)
            overlap_end = min(first_pixel + count_pixels, page_end)
            if overlap_start >= overlap_end:
                continue

            offset_in_page = overlap_start - page_start
            byte_offset = offset_in_page * 4
            byte_length = (overlap_end - overlap_start) * 4

            old_entry = pages_list[p]
            if old_entry is None:
                old_se = b"\x00" * (4 * page_pixel_count)
                old_bse = b"\x00" * (4 * page_pixel_count)
            else:
                old_se, old_bse = old_entry

            src_offset = (overlap_start - first_pixel) * 4
            new_se = old_se[:byte_offset] + se_u32le[src_offset:src_offset + byte_length] + old_se[byte_offset + byte_length:]
            new_bse = old_bse[:byte_offset] + bse_u32le[src_offset:src_offset + byte_length] + old_bse[byte_offset + byte_length:]

            if new_se == old_se and new_bse == old_bse and old_entry is not None:
                continue

            pages_list[p] = (new_se, new_bse)

        return PairedCountPlane(self.pixel_count, self.page_pixels, tuple(pages_list))

    def read(self, first_pixel, count_pixels):
        _check_int(first_pixel, "first_pixel")
        _check_int(count_pixels, "count_pixels")

        if first_pixel > self.pixel_count:
            raise ValueError("first_pixel out of bounds")
        if count_pixels > self.pixel_count - first_pixel:
            raise ValueError("count_pixels out of bounds")

        if count_pixels == 0:
            return (b"", b"")

        se_parts = []
        bse_parts = []

        first_page = first_pixel // self.page_pixels
        last_page = (first_pixel + count_pixels - 1) // self.page_pixels

        for p in range(first_page, last_page + 1):
            page_start = p * self.page_pixels
            page_end = min(page_start + self.page_pixels, self.pixel_count)

            overlap_start = max(first_pixel, page_start)
            overlap_end = min(first_pixel + count_pixels, page_end)
            if overlap_start >= overlap_end:
                continue

            offset_in_page = overlap_start - page_start
            byte_offset = offset_in_page * 4
            byte_length = (overlap_end - overlap_start) * 4

            entry = self.pages[p]
            if entry is None:
                se_parts.append(b"\x00" * byte_length)
                bse_parts.append(b"\x00" * byte_length)
            else:
                se, bse = entry
                se_parts.append(se[byte_offset:byte_offset + byte_length])
                bse_parts.append(bse[byte_offset:byte_offset + byte_length])

        return (b"".join(se_parts), b"".join(bse_parts))


def zero_plane(pixel_count, page_pixels=1024):
    _check_int(pixel_count, "pixel_count")
    _check_int(page_pixels, "page_pixels")
    if page_pixels <= 0:
        raise ValueError("page_pixels must be positive")

    if pixel_count == 0:
        pages = ()
    else:
        expected_pages = (pixel_count + page_pixels - 1) // page_pixels
        pages = tuple(None for _ in range(expected_pages))

    return PairedCountPlane(pixel_count, page_pixels, pages)
