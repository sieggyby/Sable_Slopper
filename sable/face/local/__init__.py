"""Operator-laptop-only face-swap pipeline.

Wraps the FaceFusion local CLI for swapping and provides a four-stage reference
extraction pipeline (sample → identity-filter → closed-mouth → curated faceset).

This module is laptop-only — it shells out to FaceFusion (Apple Silicon / CoreML)
and is too slow + memory-hungry to run on the Sable VPS. Use `sable face swap`
(Replicate-backed) for hosted swaps.

See docs/FACE_LOCAL_SETUP.md for install + walkthrough.
See FACE_SWAP_LESSONS.md for known failure modes and tuning recipes.
"""
