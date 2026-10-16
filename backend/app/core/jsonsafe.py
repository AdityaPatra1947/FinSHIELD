"""JSON responses that can never contain NaN/Infinity (invalid JSON): they become null, numpy scalars become Python numbers."""
from __future__ import annotations

import json
import math

import numpy as np
from fastapi.responses import JSONResponse


def clean(x):
    if isinstance(x, float):
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, np.floating):
        return clean(float(x))
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    try:  # pandas NA / NaT and similar missing markers
        import pandas as pd

        if x is pd.NA or x is pd.NaT:
            return None
    except Exception:  # noqa: BLE001
        pass
    return x


class SafeJSON(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(clean(content), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
