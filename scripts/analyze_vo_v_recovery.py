#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtests.vo_v_recovery import build_vo_v_recovery_weights
from scripts import analyze_vo_consecutive as analysis


if __name__ == "__main__":
    analysis.BUILDER = build_vo_v_recovery_weights
    analysis.DESCRIPTION = "Analyze preregistered VO V-recovery controls"
    analysis.PREREGISTRATION = "docs/research/preregistrations/batch-15-vo-v-recovery-controls.yaml"
    analysis.PREREGISTERED_COMMIT = "3edd163"
    raise SystemExit(analysis.main())
