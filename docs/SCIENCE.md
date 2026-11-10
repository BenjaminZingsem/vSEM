# Scientific scope and limits

The public runtime selects the finite stored, ideal grounded reference model.
It integrates probe response over the specimen and tracks causal raster exposure,
incident charge, finite-sample absorption and count generation. It does not paint
blur, charge or damage decorations onto a previously completed scan.

Focus and stage Z change effective probe geometry; stigmator axes change its
covariance. Stage X/Y and scan offsets select physical coordinates. HFW determines
pixel pitch; reported magnification uses an explicit 0.1 m reference display width.
The same acquired raw counts remain unchanged by display-window adjustments.

Controls apply when the physical engine admits them. Requested and applied
settings can differ while a response is prepared. Blank/settle holds are recorded;
changes affect later exposure, never pixels already acquired. Numerical delivery
may lag physical exposure. Slower accuracy-driven rendering is allowed and the
observations include delivery age. Stop and physical evolution do not depend on
an operator polling the API.

The model is **generic and uncalibrated**. It has one public SE detector, a
low-relief specimen envelope and bounded controls. It does not claim electron
transport Monte Carlo accuracy, arbitrary materials, calibrated beam profiles,
full SEM column/vacuum controls or matching a particular commercial instrument.
Unsupported controls are absent rather than simulated by cosmetic switches.

The finite world stores multiscale features and private spatial material codes.
All 27 code combinations occur in the default 16-region-per-side catalogue.
**Sensitivity/conductivity codes are expansion metadata in this release:**
charging and beam-damage feedback are not active. Exterior vacuum produces zero
sample counts/dose; incident beam/time accounting remains causal.

An experimental successor with causal material response and resident GPU state
is preserved separately from this release. Its integration requires independent
physics, timing, performance and human review. It must not be mistaken for a
qualified public capability merely because supporting types exist in this tree.

Acquired records are buffered development artifacts. Crash-durable replay,
adversarial evaluated-agent confinement and long-duration retention policy are
future gates, not release claims. This project has no real-instrument route.

A finite response preparation failure latches a terminal `BANK_FAILED` interlock.
The scalar owner ends active exposure/motion and removes authority; later ticks
return without new exposure. This is a terminal fault, not an acknowledged Stop
or evidence that pending optics settled. Acquired/partial publication and charge
already observed remain evidence; missing finalized numerical accounting remains
unknown. Private bounded failure categories aid diagnosis without changing the
physical failure path or exposing hidden specimen state. They do not establish
the cause of any previously observed numerical failure.
