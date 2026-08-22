"""Scores are lists of labelled contributions, never bare floats.

This is the structural bet of the project: explainability cannot be bolted on
afterwards. If a scoring function returns a float and a separate renderer
re-tells the story in words, the two drift apart the first time a weight
changes and the explanation quietly becomes fiction.

So every scoring function returns a Breakdown whose total *is* the sum of its
parts. The report is then a projection of the computation, and the tests can
assert on a single term instead of on the total.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contribution:
    key: str            # stable machine name, e.g. "expansion_near"
    label: str          # one line in Italian, shown to the user
    value: float
    ref: str = ""       # where it comes from in the knowledge base, e.g. "B.3"

    @property
    def is_note(self) -> bool:
        return self.value == 0.0

    def __str__(self) -> str:
        ref = f"  [{self.ref}]" if self.ref else ""
        amount = "      " if self.is_note else f"{self.value:+6.2f}"
        return f"{amount}  {self.label}{ref}"


@dataclass
class Breakdown:
    subject: str
    contributions: list[Contribution] = field(default_factory=list)

    def add(self, key: str, label: str, value: float, ref: str = "") -> None:
        """Zero-valued terms are dropped: a wall of '+0.00' hides the signal."""
        if abs(value) < 1e-9:
            return
        self.contributions.append(Contribution(key, label, value, ref))

    def note(self, key: str, label: str, ref: str = "") -> None:
        """A fact worth showing that carries no points."""
        self.contributions.append(Contribution(key, label, 0.0, ref))

    @property
    def total(self) -> float:
        return sum(c.value for c in self.contributions)

    def get(self, key: str) -> float:
        return sum(c.value for c in self.contributions if c.key == key)

    def has(self, key: str) -> bool:
        return any(c.key == key for c in self.contributions)

    def by_magnitude(self, n: int | None = None) -> list[Contribution]:
        ordered = sorted(self.contributions, key=lambda c: -abs(c.value))
        return ordered[:n] if n else ordered

    def positives(self) -> list[Contribution]:
        return [c for c in self.contributions if c.value > 0]

    def negatives(self) -> list[Contribution]:
        return [c for c in self.contributions if c.value < 0]

    def merge(self, other: "Breakdown", prefix: str = "") -> None:
        for c in other.contributions:
            self.contributions.append(
                Contribution(f"{prefix}{c.key}", c.label, c.value, c.ref)
            )

    def render(self, indent: str = "   ") -> str:
        lines = [f"{indent}{c}" for c in self.contributions]
        lines.append(f"{indent}{'-' * 46}")
        lines.append(f"{indent}{self.total:+6.2f}  TOTALE")
        return "\n".join(lines)
