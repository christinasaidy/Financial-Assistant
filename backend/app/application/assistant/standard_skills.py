"""The Standard assistant's skills: versioned instruction modules owned by the app (2026-11-23).

A skill is text added to the model's fixed instructions for one kind of task. It is not a tool: it runs nothing and
reads nothing; tools do that. Every skill is loaded once per process, always in the same order, and always sent (the
owner's decision of 2026-11-23: the instructions are cached by the provider, so sending every skill costs little,
while choosing skills per message could miss an Arabizi or mixed message). Each skill's version is saved with every
Standard answer, so an answer can be traced to the instructions it was written under.

The Lebanese Arabizi skill is built only from the generated pack (see app/infrastructure/skills/arabizi_pack.py);
the others are written here. Change a skill's version whenever its text changes.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.assistant.arabizi import ArabiziWords


@dataclass(frozen=True)
class Skill:
    name: str
    version: str
    text: str


@dataclass(frozen=True)
class ArabiziPack:
    """The owner's Arabizi rulings as the app uses them: the skill text for the model and the words its answers are
    checked against."""

    skill: Skill
    words: ArabiziWords


PRICE_COMPARISONS = Skill(
    "price_comparisons",
    "price-comparisons-2026-11-23.1",
    """Comparing prices of an item between shops or over time:
- Compare like with like. Items have a size per unit (size_amount, size_unit in g, ml or pcs) when the receipt
  printed one. Compare per 100 g or ml (line_total / quantity / size_amount * 100 with size_unit IN ('g', 'ml')),
  per piece (size_unit = 'pcs'), or per unit only between lines without a size (size_amount IS NULL).
- If the shops have no size kind in common, say the prices cannot be compared fairly and show what each shop has.
- A comparison between currencies uses the USD values (line_total_usd), and says so.
- Name the cheaper shop first, and give the prices from the result; never work out a difference yourself.""",
)

BUDGETS = Skill(
    "budgets",
    "budgets-2026-11-23.1",
    """Explaining budgets (get_budgets):
- A budget is a monthly limit for one category, in one currency; it repeats every month until the user changes it.
- spent counts that category's items only (tax, discounts and rounding are not counted); remaining is negative once
  the limit is passed; state is ok, near or limit_reached.
- pace is only for the current month: projected is where spending ends up at this rate. In the first 7 days
  (low_confidence) say it is an early estimate.
- You can read budgets but not change them: to set or change one, the user uses the Budgets screen.""",
)

SKILL_ORDER = ("price_comparisons", "budgets", "lebanese_arabizi")


def instructions(base: str, skills: Sequence[Skill]) -> str:
    """The fixed instructions: the base prompt and every skill, in SKILL_ORDER (the same bytes on every request)."""
    ordered = sorted(skills, key=lambda skill: SKILL_ORDER.index(skill.name))
    parts = [base.rstrip(), "# Skills"]
    parts += [f"## Skill: {skill.name} ({skill.version})\n{skill.text.strip()}" for skill in ordered]
    return "\n\n".join(parts) + "\n"
