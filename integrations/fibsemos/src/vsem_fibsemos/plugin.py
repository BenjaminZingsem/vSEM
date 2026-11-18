"""Lazy registry descriptor. Importing this module needs no external package.

Actual descriptor loading and bindings execution require M05B qualification.
No environment switch, version-string check or mock proves that qualification.
"""

UPSTREAM_COMMIT = '27e72f6cc8f9c014562859450ad9260411acaa12'
QUALIFICATION = 'M05A_source_only'


def driver_entry():
    from fibsem.drivers.registry import DriverEntry, DeviceBuilder
    return DriverEntry(
        manufacturer='vSEM', port=None,
        microscope_class='vsem_fibsemos.bindings:VsemMicroscope',
        devices={'beam': DeviceBuilder(build='vsem_fibsemos.bindings:build_electron'),
                 'stage': DeviceBuilder(build='vsem_fibsemos.bindings:build_stage')})
