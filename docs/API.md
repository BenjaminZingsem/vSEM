# Instrument API for a separate AI operator

The foreground launcher binds the GUI to 127.0.0.1:8122 and instrument API to
127.0.0.1:8123 by default. `--ui-port` and `--api-port` are administrator settings;
zero selects unused ephemeral ports. No endpoint changes the bind address.

The administrator reads the run's private `connection.json` and passes only
`api_origin` and `api_token` to a trusted operator. The human invitation uses a
different principal. API requests must send `Authorization: Bearer TOKEN` and
must not carry a browser Cookie or Origin header. GUI POST requests require their
own session, exact Origin and CSRF token. There is no truth/evaluator/admin route.

## Lifecycle

1. `POST /lease` with `{}` acquires control, or renews your existing control.
   Renew every 5 seconds; authority expires after 30 seconds. Competing GUI/API
   control requests can be refused. Do not assume an HTTP 202 means completion.
   To switch from the GUI to an API client, stop exposure, close the GUI tab and
   let its authority expire before acquiring API control.
2. `GET /state` obtains observable readbacks, current/applied/requested settings,
   physical scan progress, delivery age, stop generation and available images.
3. `POST /command` submits exactly the object shown below. It returns an
   `operation_id`; use `GET /operation/ID` to observe its disposition.
4. Image metadata is `GET /image/ID`; raw SE data is `GET /image/ID/SE`.
   The count plane is row-major, little-endian uint32, four bytes per pixel.
   Columns increase toward positive specimen X; rows increase toward negative Y.
5. Send Stop before ending a client session. Closing an HTTP connection alone
   does not stop the physical instrument. The service continues while you think.

```json
{
  "action": "scan_single",
  "parameters": {
    "width_px": 1024,
    "height_px": 1024,
    "field_width_m": 0.000002,
    "offset_x_m": 0.0,
    "offset_y_m": 0.0,
    "dwell_ns": 20000
  },
  "expected_stop_generation": 0
}
```

Always use the observed `stop_generation`, not a hardcoded zero. A timeout means
the outcome is unknown; inspect state/operation before retrying. Do not replay a
possibly admitted action blindly. Rejected or cancelled operations are not success.

## Commands

| Action | Exact parameter keys | Supported values |
|---|---|---|
| `scan_single`, `scan_live`, `configure_live` | `width_px`, `height_px`, `field_width_m`, `offset_x_m`, `offset_y_m`, `dwell_ns` | Square 64/128/256/512/1024; HFW 0.1–5000 µm; dwell 20000/100000/1000000 ns |
| `optics` | `current_pA`, `focus_offset_m`, `stigmator_x`, `stigmator_y` | Integer current 1–1000 pA; focus ±25 µm; stigmators ±1 |
| `stage_move` | `x_m`, `y_m`, `z_m` | X/Y ±25 mm; Z ±20 µm; combined focus+Z must remain within ±25 µm |
| `freeze` | `source_id` | An observed current live source identifier |
| `stop` | none (`{}`) | Requires owned control; changes stop generation |

An ROI uses a smaller field width and explicit scan offsets. The GUI separately
retains its survey viewport underneath that acquired ROI; viewport composition
does not alter the instrument image or coordinates. `configure_live` changes a
live raster; a pixel-grid change interrupts/restarts it with partial-frame history.

`latest_image` may still describe an earlier delivered cut while physical progress
has advanced. Match source/image identifiers and inspect `outcome`, completed
pixels, acquisition times, parameter segments and blank holds. Single-frame
terminal images are listed in `recorded_images`; live scans reuse their source.
Raw counts and metadata can be stored directly, as the example client does.

### Live command completion

`configure_live` admission records a request, not an applied raster. Its operation
completes when a verified raster uses the requested pixel grid, field, offsets and
dwell. If that configuration is already active, completion can follow admission
without a new sweep. Stage pose is controlled separately. A later admitted
configuration supersedes a still-unapplied one (`CANCELLED`, `SUPERSEDED`). Stop,
authority loss or a terminal fault cancels requests that have not applied. Ending
a session before application is not successful configuration.

`freeze` has its own receipt, separate from the original `scan_live` operation.
It completes when the corresponding live session finishes normally; interruption
reports cancellation. Freeze does not advance Stop generation. Confirm a separate
Stop when required. A late admission event never downgrades an already terminal
receipt. Physical completion can precede numerical image delivery: still match
the live source, frame outcome and acquisition times when retrieving the image.

Requests refused because an ingress queue is full return `ingress_capacity`
without an admitted operation receipt. They retain no operation record. The
separate reserved Stop queue is unchanged; this is not a general history-retention
policy or a hostile-client confinement guarantee.

### Terminal preparation faults

`BANK_FAILED` is fail-closed: the episode interlocks, ends active acquisition,
retires pending work and removes control authority. Subsequent episode ticks do
not expose more specimen. Blank state does not establish a newly successful Stop,
settled optics or complete numerical publication. An old Stop generation cannot
confirm a later Stop after the fault. Preserve acquired images, partial metadata
and the known observable charge interval; do not invent missing finalized dose.

The administrator must preserve the private run records, close the owned instance
and investigate before starting a new episode. There is no operator reset or
interlock-clearing endpoint. Bounded private preparation categories can help the
administrator correlate the failure, but are never returned through state, image
or operation endpoints. See [deployment diagnostics](DEPLOYMENT.md).

The current protocol is `vsem.core-human.v3` with captured-image v2 projections;
older helper schemas in the code are not this API's contract. The authoritative
admission/projection code is `runtime/hierarchical_public_protocol.py`,
`runtime/interactive_public_protocol.py` and `runtime/core_public_protocol.py`.
The example client imports none of the private engine implementation.

This development transport is loopback HTTP. For adversarial evaluations, first
build and audit OS/network/filesystem separation: the operator must not read the
server code's hidden data, specimen coefficients, run records or credentials.
Remote access/TLS and multi-user deployment are not provided by this release.
