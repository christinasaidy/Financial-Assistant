"""Deterministic, receipt-only coverage selection for the second dataset batch.

Use ``make_batch2_plan`` once per split to coordinate global quotas. For example,
27 training users with limits of 30 give 810 specs; three validation users with
limits of 40 give 120. ``make_batch2_specs`` is a convenient *local* picker, not a
global guarantee. Always inspect the returned plan's shortfalls before generation.

The bounded greedy picker reserves template and boundary diversity, then prioritizes
rare available items (three direct specs, two semantic families, two users where
available), then period/price coverage. Limits are hard;
quotas are goals, not promises or a proof of infeasibility when unmet. Counts refer
to selected specs, not six writer versions or follow-up bases. They say nothing
about which spelling a writer will use or how many versions survive review.

SQL comes exclusively from the existing template functions/helpers. No template
globals, batch-1 seeds, receipts or catalogue entries are changed. Job IDs and DB
validation remain the caller's responsibility.
"""

import random
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from copy import copy
from dataclasses import dataclass, replace

from research.dataset import periods
from research.dataset import templates as t
from research.dataset.templates import Spec, UserData

SEED_PREFIX = "fyp-dataset/batch2"


@dataclass
class Batch2Plan:
    specs: dict[int, list[Spec]]
    # item -> (missing direct specs, missing semantic families); excludes ALL follow-ups
    item_shortfalls: dict[str, tuple[int, int]]
    feature_shortfalls: dict[str, int]
    feature_counts: dict[str, int]
    diversity_shortfalls: dict[str, int]


def _family(spec: Spec) -> str:
    name = spec.template
    if name in ("T9", "T10", "F7", "F8"):
        return "spending"
    if name in ("T11", "T11k"):
        return "latest_price"
    if name in ("T12", "T12k"):
        return "average_price"
    if name == "T13":
        return "shop_comparison"
    if name == "T14":
        return "purchase_frequency"
    if name in ("T15", "T18"):
        return "quantity"
    return name


def _features(spec: Spec) -> tuple[str, ...]:
    found = [f"template:{spec.template}"]
    if spec.kind == "sql":
        # Inherited labels are not a new mention (F6 even discards its base's
        # period). Only period-changing follow-ups add period-language coverage.
        if spec.labels.get("period") and (spec.base is None or spec.template in ("F1", "F8")):
            found.append(f"period:{spec.labels['period']}")
        if spec.template in ("T12", "T12k"):
            found.append("average")
        if spec.template == "T13":
            found.append(f"comparison:{spec.labels['compared']}")
    if spec.template == "C4":
        found.append(f"unclear:{spec.labels['period']}")
    if spec.template == "C5":
        found.append(f"missing:{spec.labels['group']}")
    return tuple(found)


def _direct_item(spec: Spec) -> str | None:
    return spec.labels.get("item") if spec.kind == "sql" and spec.base is None else None


def _periods(data: UserData) -> list[periods.Period]:
    # Every supported kind, but only one day-range per month: the full template
    # helper also contains 1,800 range variants which would swamp selection.
    return [p for p in t._all_periods(data)
            if not p.kind.startswith("range_") or p.kind.endswith("_1_5")]


def _spending(data: UserData, name: str, period: periods.Period) -> Spec:
    item = data.catalogue.item(name)
    return t._spec("T9", f"How much the user spent on {name} (no brand named), {period.description}.",
                   t.money("purchases", "line_total", t.item_is(name), period.sql), period,
                   t.item_words(item), item=name)


def _brand_follow(data: UserData, base: Spec, brand: str, period: periods.Period) -> Spec:
    name = base.labels["item"]
    target = t.money("purchases", "line_total", t.item_is(name), f"brand = {t.quoted(brand)}", period.sql)
    return t._follow("F7", base, f"The same spending question, only the brand {brand}. Keep the item and period.",
                     target, t._brand_words(data.catalogue.item(name), brand), brand=brand)


def _brand_period(data: UserData, follow: Spec, old: periods.Period, new: periods.Period) -> Spec:
    """A branded first question, then a period-only follow-up retaining its brand."""
    name, brand = follow.labels["item"], follow.labels["brand"]
    base = t._spec("T10", f"How much the user spent on {brand} {name} (the brand {brand} is named), "
                   f"{old.description}.", follow.target, old, t.item_words(data.catalogue.item(name)),
                   t._brand_words(data.catalogue.item(name), brand), item=name, brand=brand)
    target = t.money("purchases", "line_total", t.item_is(name), f"brand = {t.quoted(brand)}", new.sql)
    return t._follow("F8", base, f"The same question for another period: {new.description}. "
                     "Keep the earlier item and brand; mention only the new period.", target,
                     new.words, period=new.kind)


def _candidates(data: UserData, seed: str) -> list[Spec]:
    rng = random.Random(f"{SEED_PREFIX}/{seed}/{data.user.number}")
    available_periods = _periods(data)
    rng.shuffle(available_periods)
    result = []
    for index, name in enumerate(data.items):
        focused = copy(data)
        focused.items = [name]  # template eligibility stays intact; receipts remain complete
        for offset in range(3):
            p = available_periods[(index * 3 + offset) % len(available_periods)]
            base = _spending(data, name, p)
            result.append(base)
            if offset == 0:
                brands = sorted({line.brand for _, line in data.lines if line.item == name and line.brand})
                for brand in brands:
                    follow = _brand_follow(data, base, brand, p)
                    result.append(follow)
                    new = available_periods[(index * 3 + 1) % len(available_periods)]
                    if p.sql and new.sql and p.sql != new.sql:
                        result.append(_brand_period(data, follow, p, new))
        for maker in (t.t14_times, t.t11_latest_price, t.t11k_latest_per_kilo,
                      t.t12_average_price, t.t12k_average_per_kilo, t.t15_quantity,
                      t.t18_weight, t.t13_compare_shops):
            spec = maker(focused, rng)
            if spec is not None:
                result.append(spec)
    # Explicit periods prevent the usual receipt-weighted random draw from
    # starving named months, weekdays and short rolling windows.
    for p in available_periods:
        result.append(t._spec("T1", f"How much the user spent in total, {p.description}.",
                              t.money("receipts", "total", p.sql), p))
    for _ in range(30):
        for maker in t.CLARIFY.values():
            # C2 assumes at least one catalogue shop is missing.
            if maker is t.c2_unknown_shop and len(data.shops) == len(data.catalogue.shops):
                continue
            spec = maker(data, rng)
            if spec is not None:
                result.append(spec)
        result.append(t.unsupported(data, rng))
        result.append(t.reply(data, rng))
    # Include the entire existing repertoire, not just item-oriented templates.
    for maker in (*t.SQL_TEMPLATES.values(), *t.FOLLOW_UPS.values()):
        if maker is t.f3_item and len(data.items) < 2:
            continue
        for _ in range(12):
            spec = maker(data, rng)
            if spec is not None:
                result.append(spec)
    grouped = t._group(data, rng, periods.no_period())
    if grouped is not None:
        result.append(grouped)
    # No repeats masquerading as independent coverage within a user. Descriptions
    # matter for non-SQL variants; bases distinguish different follow-up contexts.
    unique = {}
    for spec in result:
        # F6's existing helper looks up the latest purchase across all time.
        # A period-constrained base would leave an implicit period in the chat
        # that its SQL silently discards. Only retain unbounded contexts here.
        if spec.template == "F6" and (
            spec.base is None or spec.base.labels.get("period") != "none"
            or spec.labels.get("period") != "none"
        ):
            continue
        key = (spec.template, spec.target, spec.description, spec.base.target if spec.base else None)
        unique.setdefault(key, replace(spec, labels={**spec.labels, "batch2_family": _family(spec)}))
    result = list(unique.values())
    rng.shuffle(result)
    return result


def _goals() -> dict[str, int]:
    goals = {f"period:{prefix}{month}": 2
             for prefix in ("month_", "since_month_") for month in range(1, 13)}
    for kind in ("this_month", "last_month", "this_week", "last_week", "today", "yesterday",
                 "this_year", "since_start_of_year", "weekend", "summer", "none",
                 "last_3_days", "last_7_days", "last_10_days", "last_14_days", "last_30_days",
                 "last_2_weeks", "last_3_weeks", "last_2_months", "last_3_months", "last_6_months"):
        goals[f"period:{kind}"] = 2
    goals.update({f"period:weekday_{day}": 2 for day in range(7)})
    goals.update({f"template:C{i}": 3 for i in range(1, 7)})
    goals.update({f"template:U{i}": 3 for i in range(1, 6)})
    goals.update({f"unclear:{kind}": 2 for kind in ("kanoun", "semester", "awal el sene")})
    goals.update({f"missing:{kind}": 2 for kind in ("gifts", "repairs")})
    goals.update({f"comparison:{unit}": 4 for unit in ("per 100 g or ml", "per piece", "per unit")})
    for name in (*t.SQL_TEMPLATES, *t.FOLLOW_UPS, "T3g", "R1", "R2", "R3", "R4"):
        goals[f"template:{name}"] = 1
    goals.update({"template:F7": 12, "template:F8": 6, "average": 30, "template:T17": 3,
                  "template:T19": 3, "template:T20": 3})
    return goals


def make_batch2_specs(data: UserData, count: int, seed: str) -> list[Spec]:
    """Pick locally; use make_batch2_plan for global quotas and deficit reporting."""
    return make_batch2_plan([data], {data.user.number: count}, seed).specs[data.user.number]


def make_batch2_plan(data: Sequence[UserData], limits: Mapping[int, int], seed: str) -> Batch2Plan:
    """Plan one split under hard per-user limits, reporting every unmet goal.

    Available means present on at least one supplied user's actual planned receipt,
    not just listed in the catalogue. Users 1-27 and 28-30 must be planned separately.
    Exact requested counts are returned or ValueError is raised if the bounded,
    deduplicated candidate pool cannot fill a limit. A shortfall does not establish
    that no better allocation exists; the selector is greedy, not an optimizer.
    """
    users = sorted(data, key=lambda d: d.user.number)
    numbers = [d.user.number for d in users]
    if any(not 1 <= n <= 30 for n in numbers):
        raise ValueError("Batch 2 only permits synthetic users 1 through 30")
    if len(set(numbers)) != len(numbers) or set(numbers) != set(limits):
        raise ValueError("Supply distinct users and exactly one limit for each")
    if any(type(n) is not int or n < 0 for n in limits.values()):
        raise ValueError("Limits must be nonnegative integers")
    if any(n <= 27 for n in numbers) and any(n >= 28 for n in numbers):
        raise ValueError("Plan training and validation separately")
    selected = {n: [] for n in numbers}
    pools = {d.user.number: _candidates(d, seed) if limits[d.user.number] else [] for d in users}
    if any(len(pools[n]) < limits[n] for n in numbers):
        raise ValueError("Requested count exceeds the distinct candidate pool")
    goals, features = _goals(), Counter()
    counts, families, item_users = Counter(), defaultdict(set), defaultdict(set)
    local_templates = defaultdict(Counter)
    owners = defaultdict(list)
    for d in users:
        for name in d.items:
            owners[name].append(d.user.number)

    def score(number, spec):
        gain = sum(features[f] < goals.get(f, 0) for f in _features(spec))
        # Feature gain first, then spread load so one user's rare items do not
        # consume every slot before other items can be placed.
        return (gain, -local_templates[number][spec.template],
                (limits[number] - len(selected[number])) / max(1, limits[number]))

    def take(number, spec):
        pools[number].remove(spec)
        selected[number].append(spec)
        features.update(_features(spec))
        local_templates[number][spec.template] += 1
        name = _direct_item(spec)
        if name:
            counts[name] += 1
            families[name].add(spec.labels["batch2_family"])
            item_users[name].add(number)

    # Protect at least one of every available template even in validation, where
    # the item universe alone is larger than the budget. Never exceed a limit.
    template_names = sorted({s.template for rows in pools.values() for s in rows})
    for template in template_names:
        choices = [(n, s) for n in numbers if len(selected[n]) < limits[n]
                   for s in pools[n] if s.template == template]
        if choices:
            take(*max(choices, key=lambda pair: score(*pair)))

    # Validation cannot meet the item quotas. Reserve one instance of each
    # period, comparison regime and boundary variant before filling rare items,
    # so a small split still exercises the breadth of the task. Missing or
    # unaffordable features remain visible in feature_shortfalls.
    for feature in goals:
        if features[feature] or feature.startswith("template:"):
            continue
        choices = [(n, s) for n in numbers if len(selected[n]) < limits[n]
                   for s in pools[n] if feature in _features(s)]
        if choices:
            take(*max(choices, key=lambda pair: score(*pair)))

    # Up to one fifth of the total budget is protected for clarify/unsupported.
    # Stop sooner when their goals are satisfied; already selected ones count.
    boundary_count = sum(s.kind in ("clarify", "unsupported") for rows in selected.values() for s in rows)
    while boundary_count < sum(limits.values()) // 5:
        choices = [(n, s) for n in numbers if len(selected[n]) < limits[n] for s in pools[n]
                   if s.kind in ("clarify", "unsupported") and score(n, s)[0] > 0]
        if not choices:
            break
        take(*max(choices, key=lambda pair: score(*pair)))
        boundary_count += 1

    # Rarest items first, including zero-budget owners in the universe but not in
    # the rarity estimate. Three rounds favor breadth when a budget is too small.
    ordered = sorted(owners, key=lambda name: (sum(limits[n] > 0 for n in owners[name]), name))
    for round_number in range(3):
        for name in ordered:
            if counts[name] > round_number:
                continue
            choices = [(n, s) for n in owners[name] if len(selected[n]) < limits[n]
                       for s in pools[n] if _direct_item(s) == name]
            if len(families[name]) < 2 and families[name]:
                diverse = [(n, s) for n, s in choices if s.labels["batch2_family"] not in families[name]]
                choices = diverse or choices
            if choices:
                take(*max(choices, key=lambda pair: (
                    len(item_users[name]) < 2 and pair[0] not in item_users[name], score(*pair))))
    while any(len(selected[n]) < limits[n] for n in numbers):
        choices = ((n, s) for n in numbers if len(selected[n]) < limits[n] for s in pools[n])
        take(*max(choices, key=lambda pair: score(*pair)))
    missing_items = {name: (max(0, 3 - counts[name]), max(0, 2 - len(families[name])))
                     for name in sorted(owners) if counts[name] < 3 or len(families[name]) < 2}
    missing_features = {f: goal - features[f] for f, goal in goals.items() if features[f] < goal}
    missing_diversity = {name: min(2, len(owners[name])) - len(item_users[name]) for name in sorted(owners)
                         if len(item_users[name]) < min(2, len(owners[name]))}
    return Batch2Plan(selected, missing_items, missing_features, dict(features), missing_diversity)
