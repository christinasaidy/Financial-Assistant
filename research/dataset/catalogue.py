"""The catalogue the synthetic users shop from (data/catalogue.json, reviewed by the user).

Loading it also checks it, so a mistake in the file stops the build instead of producing odd receipts: every item
has a category that exists, exactly one way of being priced, and shops of its kind; no spelling belongs to two items.
"""

import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

CATALOGUE_FILE = Path(__file__).parent / "data" / "catalogue.json"


@dataclass(frozen=True)
class Size:
    amount: int
    unit: str  # g, ml or pcs
    low: Decimal  # USD price range for one unit of this size
    high: Decimal


@dataclass(frozen=True)
class Item:
    name: str
    category: str
    group: str | None
    words: tuple[str, ...]  # the user's Arabizi spellings
    suggested: tuple[str, ...]  # spellings added by the assistant, still to be checked by the user
    brands: tuple[str, ...]
    at: tuple[str, ...]  # kinds of shop that sell it
    vendors: tuple[str, ...]  # when only these shops sell it (bills, subscriptions)
    sizes: tuple[Size, ...] = ()  # packaged
    weight_g: tuple[int, int] | None = None  # weighed: grams in one line, and USD per kilo
    per_kg: tuple[Decimal, Decimal] | None = None
    litres: tuple[int, int] | None = None  # fuel: litres in one line, and USD per litre
    per_litre: tuple[Decimal, Decimal] | None = None
    price: tuple[Decimal, Decimal] | None = None  # no size

    @property
    def spellings(self) -> tuple[str, ...]:
        return self.words + self.suggested


@dataclass(frozen=True)
class Shop:
    name: str
    kind: str
    category: str
    lbp_share: float  # how often its receipts are in LBP
    nicknames: tuple[str, ...]
    suggested: tuple[str, ...]


@dataclass(frozen=True)
class Catalogue:
    items: tuple[Item, ...]
    shops: tuple[Shop, ...]
    default_categories: tuple[str, ...]
    private_categories: dict[str, str]  # private category -> the category its items take for users without it
    category_words: dict[str, tuple[str, ...]]
    group_words: dict[str, tuple[str, ...]]

    def shops_of(self, kind: str) -> tuple[Shop, ...]:
        return tuple(shop for shop in self.shops if shop.kind == kind)

    def item(self, name: str) -> Item:
        return next(item for item in self.items if item.name == name)


class CatalogueError(ValueError):
    pass


def load_catalogue(path: Path = CATALOGUE_FILE) -> Catalogue:
    data = json.loads(path.read_text(encoding="utf-8"))
    categories = data["categories"]
    catalogue = Catalogue(
        items=tuple(_item(entry) for entry in data["items"]),
        shops=tuple(_shop(entry) for entry in data["shops"]),
        default_categories=tuple(categories["default"]),
        private_categories=dict(categories["private"]),
        category_words={
            name: tuple(words) for name, words in data["category_words"].items() if isinstance(words, list)
        },
        group_words={name: tuple(words) for name, words in data["group_words"].items() if isinstance(words, list)},
    )
    _check(catalogue)
    return catalogue


def _item(entry: dict) -> Item:
    def money(pair):
        return (Decimal(str(pair[0])), Decimal(str(pair[1]))) if pair else None

    return Item(
        name=entry["name"], category=entry["category"], group=entry.get("group"),
        words=tuple(entry.get("words", ())), suggested=tuple(entry.get("suggested", ())),
        brands=tuple(entry.get("brands", ())), at=tuple(entry["at"]), vendors=tuple(entry.get("vendors", ())),
        sizes=tuple(Size(int(a), u, Decimal(str(lo)), Decimal(str(hi))) for a, u, lo, hi in entry.get("sizes", ())),
        weight_g=tuple(entry["weight_g"]) if entry.get("weight_g") else None, per_kg=money(entry.get("per_kg")),
        litres=tuple(entry["litres"]) if entry.get("litres") else None, per_litre=money(entry.get("per_litre")),
        price=money(entry.get("price")),
    )  # fmt: skip


def _shop(entry: dict) -> Shop:
    return Shop(name=entry["name"], kind=entry["kind"], category=entry["category"],
                lbp_share=float(entry["lbp_share"]), nicknames=tuple(entry.get("nicknames", ())),
                suggested=tuple(entry.get("suggested", ())))  # fmt: skip


def _check(catalogue: Catalogue) -> None:
    problems: list[str] = []
    categories = set(catalogue.default_categories) | set(catalogue.private_categories)
    shop_names = {shop.name for shop in catalogue.shops}
    kinds = {shop.kind for shop in catalogue.shops}
    for fallback in catalogue.private_categories.values():
        if fallback not in catalogue.default_categories:
            problems.append(f"private category falls back to an unknown category: {fallback}")
    for shop in catalogue.shops:
        if shop.category not in catalogue.default_categories:
            problems.append(f"{shop.name}: a shop's category must be a shared one, not {shop.category}")
        if not 0 <= shop.lbp_share <= 1:
            problems.append(f"{shop.name}: lbp_share must be between 0 and 1")
    for item in catalogue.items:
        if item.category not in categories:
            problems.append(f"{item.name}: unknown category {item.category}")
        pricing = [bool(item.sizes), item.weight_g is not None, item.litres is not None, item.price is not None]
        if sum(pricing) != 1:
            problems.append(f"{item.name}: needs exactly one of sizes, weight_g, litres or price")
        if (item.weight_g is None) != (item.per_kg is None) or (item.litres is None) != (item.per_litre is None):
            problems.append(f"{item.name}: a weight or volume needs its price per kilo or litre")
        for kind in item.at:
            if kind not in kinds:
                problems.append(f"{item.name}: no shop of kind {kind}")
        for vendor in item.vendors:
            if vendor not in shop_names:
                problems.append(f"{item.name}: unknown shop {vendor}")
        for size in item.sizes:
            if size.unit not in ("g", "ml", "pcs") or size.low > size.high:
                problems.append(f"{item.name}: bad size {size}")
    names = Counter(item.name for item in catalogue.items)
    problems += [f"item listed twice: {name}" for name, count in names.items() if count > 1]
    spellings = Counter(spelling for item in catalogue.items for spelling in set(item.spellings))
    problems += [f"spelling on two items: {s}" for s, count in spellings.items() if count > 1]
    if problems:
        raise CatalogueError("; ".join(problems))
