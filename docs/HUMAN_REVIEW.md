# Current human review instructions

Start with the [illustrated GUI walkthrough](GUI_WALKTHROUGH.md) for screenshots,
exact control locations and step-by-step examples, then use this review checklist.

Version: initial public research release. Launch manually using the README.
No review server is started automatically. The terminal prints a one-use browser
invitation; use that URL, not a bare unauthenticated page. Keep the terminal open.
Ctrl+C stops the server and closes its owned processes. Use a new run directory
for each launch. Do not send run credentials or invitation URLs in issue reports.

For automation, the configure/freeze completion rules and terminal-fault limits
are documented in [the API guide](API.md). A completed physical operation can
precede image delivery; compare applied readbacks and acquisition timestamps. If
the episode interlocks, preserve evidence and close the instance. Blanking after
a terminal fault is not a new Stop acknowledgement or permission to resume.

Acquire GUI control, then test:

1. Start a 64-pixel live scan around HFW 2 µm. Adjust focus through both sides of
   the sharp setting; features should visibly soften and recover. Change X/Y
   stigmation and correct it. Settings may wait for response preparation; compare
   requested/applied readbacks and image delivery age.
2. Move stage X and Y by small fractions of the field; the same features move.
   Change Z and compensate with focus. Confirm actual stage readbacks settle.
3. Zoom from a detailed 1–2 µm field out to the 5000 µm maximum HFW. The 1.28 mm
   sample should occupy part of the survey; exterior vacuum is black with zero
   raw counts. Returning to a sampled area must not generate new terrain.
4. Acquire 1024 × 1024 at 20 µs dwell. During **physical acquiring**, change focus
   substantially. Later rows should reflect the admitted change; earlier rows
   must retain their original exposure. Inspect recorded parameter segments.
   The nominal exposure is about 21 seconds plus scan overhead/blank holds;
   slower numerical delivery is allowed.
5. After that acquisition, draw a small central ROI and use a 64-pixel live scan.
   Its updates should overlay the retained 1024 survey. Distinguish setting the
   alignment ROI from changing the full viewport/zoom. A new sweep must overwrite
   progressively rather than blanking the previous sweep.
6. Change current, use the histogram auto-window and adjust count range/gamma.
   Display changes must not alter saved raw counts. Acquire, save and reopen an
   image using the console's acquired-file controls.
7. Press Stop during exposure. Verify beam blanking and cessation of exposure.
   Stop again and close the terminal with Ctrl+C when finished.

Damage and charging are inactive in this ideal-grounded build. Do not judge their
absence as an unexpected runtime regression; they are explicit roadmap work.
Report commit/version, GPU/software versions, actions, field/resolution/dwell,
observable timing and expected/actual results. Attach acquired data only after
checking that it contains no private connection or run-control credentials.
