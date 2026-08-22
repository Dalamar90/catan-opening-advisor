"""Loading and access for config.yaml.

The config is a plain nested dict wrapped in a thin accessor. No dataclass
mirror of every key: M6 will be adding and removing weights constantly, and a
schema that has to be edited twice per change is a schema that rots.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import constants as K

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class Config:
    def __init__(self, data: dict[str, Any], source: Path | None = None):
        self._data = data
        self.source = source

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, dotted: str, default: Any = None) -> Any:
        """Fetch a nested value: cfg.get('pair.hard_constraints.min_wheat_pips')."""
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        sentinel = object()
        value = self.get(dotted, sentinel)
        if value is sentinel:
            raise KeyError(f"chiave di configurazione mancante: {dotted}")
        return value

    # ------------------------------------------------------------------
    def resource_weights(
        self, pips_by_resource: dict[str, int] | None = None, n_players: int = 4
    ) -> dict[str, float]:
        """Base weights, corrected for how scarce each resource is on this board.

        KB B.2. Returns the final weights; call scarcity_report() if you also
        need the intermediate quotas for the explanation.
        """
        base = dict(self.require("resource_weights"))
        if n_players == 3:
            # KB C.2: the board stays open, so roads matter more.
            base[K.WOOD] += 0.1
            base[K.BRICK] += 0.1
        if not pips_by_resource:
            return base

        exponent = self.get("scarcity.exponent", 0.5)
        lo = self.get("scarcity.min_multiplier", 0.7)
        hi = self.get("scarcity.max_multiplier", 1.6)
        total = sum(pips_by_resource.values()) or K.TOTAL_PIPS

        out = {}
        for resource, weight in base.items():
            actual = pips_by_resource.get(resource, 0) / total
            expected = K.EXPECTED_QUOTA[resource]
            if actual <= 0:
                multiplier = hi
            else:
                multiplier = (expected / actual) ** exponent
            out[resource] = weight * max(lo, min(hi, multiplier))
        return out

    def scarcity_report(
        self, pips_by_resource: dict[str, int], n_players: int = 4
    ) -> dict[str, dict[str, float]]:
        total = sum(pips_by_resource.values()) or K.TOTAL_PIPS
        final = self.resource_weights(pips_by_resource, n_players)
        base = self.resource_weights(None, n_players)
        out = {}
        for resource in K.RESOURCES:
            pips = pips_by_resource.get(resource, 0)
            actual = pips / total
            expected = K.EXPECTED_QUOTA[resource]
            out[resource] = {
                "pips": pips,
                "quota": actual,
                "expected": expected,
                "deviation": actual - expected,
                "ratio": actual / expected if expected else 0.0,
                "weight_base": base[resource],
                "weight_final": final[resource],
            }
        return out


@lru_cache(maxsize=8)
def load_config(path: str | Path | None = None) -> Config:
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(resolved, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"config non valida: {resolved}")
    return Config(data, source=resolved)
