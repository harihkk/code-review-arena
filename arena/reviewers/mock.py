"""Deprecated alias for :mod:`arena.reviewers.controls`.

The deterministic baseline reviewers are controls (calibrated ceilings,
floors, and cheaters), not throwaway mocks. Import ControlReviewer from
arena.reviewers.controls; this shim remains for one release.
"""

from arena.reviewers.controls import ControlReviewer

MockReviewer = ControlReviewer

__all__ = ["MockReviewer"]
