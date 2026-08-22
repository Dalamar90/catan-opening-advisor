"""Port valuation, KB B.5.

The golden rule of B.5 is that a port without production is a wasted square, so
the value of a port is a function of how much of its resource the *portfolio*
produces -- not of the port itself. That makes it circular at the first pick,
when the portfolio does not exist yet. We resolve the circularity explicitly:
with an unknown portfolio a port is priced as an option, worth what this vertex
alone feeds it plus a discounted slice of the upside a plausible second
settlement would add.
"""

from __future__ import annotations

from ..board import Port
from ..config import Config
from .breakdown import Breakdown


def _step_value(table: dict, pips: int) -> float:
    """Value from a {threshold: value} table, taking the highest match."""
    value = 0.0
    for threshold in sorted(int(t) for t in table):
        if pips >= threshold:
            value = float(table[threshold])
    return value


def specific_port_value(cfg: Config, pips_of_resource: int) -> float:
    return _step_value(cfg.require("ports.specific_by_pips"), pips_of_resource)


def generic_port_value(
    cfg: Config, total_pips: int | None = None, max_resource_pips: int | None = None
) -> float:
    value = float(cfg.get("ports.generic_base", 0.4))
    if total_pips is not None and total_pips >= 20:
        value += float(cfg.get("ports.generic_high_production_bonus", 1.0))
    if max_resource_pips is not None and max_resource_pips >= 8:
        value += float(cfg.get("ports.generic_surplus_bonus", 1.2))
    return value


def score_port(
    cfg: Config,
    port: Port | None,
    production: dict[str, int],
    portfolio_known: bool,
    breakdown: Breakdown,
) -> None:
    """Add the port term to `breakdown`.

    `production` is the pips per resource of whatever is known so far: the
    single vertex at the first pick, the whole pair once it exists.
    """
    if port is None:
        return

    if port.is_generic:
        total = sum(production.values())
        peak = max(production.values(), default=0)
        if portfolio_known:
            value = generic_port_value(cfg, total, peak)
            label = f"porto 3:1 con {total} pip di produzione"
        else:
            # The two bonuses are properties of the pair, unknowable right now.
            value = generic_port_value(cfg)
            label = "porto 3:1 (valore base; i bonus dipendono dalla coppia)"
        breakdown.add("port_generic", label, value, ref="B.5")
        return

    own = production.get(port.resource, 0)
    if portfolio_known:
        value = specific_port_value(cfg, own)
        label = f"{port} con {own} pip di quella risorsa"
        if value == 0:
            label = f"{port} senza produzione: casella sprecata ({own} pip)"
        breakdown.add("port_specific", label, value, ref="B.5")
        return

    discount = float(cfg.get("ports.unknown_portfolio_discount", 0.4))
    partner = int(cfg.get("ports.unknown_portfolio_partner_pips", 4))
    now = specific_port_value(cfg, own)
    upside = specific_port_value(cfg, own + partner)
    value = now + discount * (upside - now)
    label = (
        f"{port}: {now:.1f} con i {own} pip di qui, fino a {upside:.1f} se la "
        f"seconda colonia porta la risorsa (conto il {discount:.0%} dell'upside)"
    )
    breakdown.add("port_option", label, value, ref="B.5")
