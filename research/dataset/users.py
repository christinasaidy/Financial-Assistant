"""The synthetic users the dataset is built on: who they are, where they shop, and their receipts.

Decided by the assistant on 2026-11-08 (the user delegated these choices):
- 30 users, each made from a fixed seed, so the same number always gives the same user and receipts;
- each user's "today" falls between March 2025 and late 2027, about a month apart, so every month and weekday is
  someone's today and a named month falls in the same year for some users and the previous year for others;
- 14 months of receipts before today, about 150-250 receipts per user; food and drink sometimes come several
  to a line (up to 6), other things almost always one;
- a user has a few shops of each kind they use (2 supermarkets, 3 fast-food places, ...) and a personal set of
  items they buy there, some often, some rarely; some users have a car, a pet, a smoking habit or a baby;
- prices: one base price per user and item within the catalogue's range, times the shop's own price level, with a
  small change per purchase; USD rounded to 0.05, LBP to 5,000 (weighed lines to 1,000) at 89,500 per USD;
- about a quarter of lines have no unit price, as on receipts that do not print it; weighed food and fuel are
  stored as their weight or volume with quantity 1;
- some receipts differ from their lines (a restaurant's service charge, a supermarket discount, LBP rounding),
  and a few restaurant, cafe and taxi receipts have no lines at all;
- bills (electricity, generator, internet, phone) and subscriptions come once a month on a fixed day;
- private categories: a pet owner may have Pets, a smoker Tobacco, a subscriber Subscriptions, a beauty shopper
  Beauty. An item of a private category the user does not have takes its fallback category.

Planning (`make_user`) is separate from writing to the database (`seed_user`), so the plan can be checked and tested
without one.
"""

import random
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.application.auth.dtos import RegisterRequest
from app.application.receipts.dtos import ConfirmReceiptRequest
from app.domain.receipts.receipt import ReceiptLine

from research.dataset.catalogue import Catalogue, Item, Shop

USER_COUNT = 30
RATE = Decimal(89500)  # LBP per USD
HISTORY_DAYS = 425  # about 14 months
FIRST_TODAY = date(2025, 3, 1)
EMAIL_DOMAIN = "dataset.local"

# kind: (chance a user shops there at all, how many such shops, visits a month to all of them, lines per receipt)
KINDS: dict[str, tuple[float, tuple[int, int], tuple[float, float], tuple[int, int]]] = {
    "supermarket": (1.0, (1, 3), (2.0, 4.0), (3, 10)),
    "minimarket": (0.8, (1, 2), (1.0, 3.0), (1, 4)),
    "bakery": (0.9, (1, 2), (1.0, 3.0), (1, 3)),
    "sweets": (0.4, (1, 1), (0.2, 0.6), (1, 2)),
    "nuts": (0.4, (1, 1), (0.2, 0.6), (1, 3)),
    "butcher": (0.5, (1, 1), (0.5, 1.5), (1, 2)),
    "pharmacy": (0.9, (1, 2), (0.3, 1.0), (1, 3)),
    "fuel": (1.0, (1, 2), (1.5, 3.0), (1, 2)),  # only users with a car
    "car_wash": (0.5, (1, 1), (0.3, 1.0), (1, 1)),  # only users with a car
    "cafe": (0.8, (1, 3), (1.0, 4.0), (1, 3)),
    "fast_food": (0.9, (2, 4), (1.0, 3.0), (1, 3)),
    "restaurant": (0.7, (1, 3), (0.3, 1.2), (2, 4)),
    "delivery": (0.5, (1, 1), (0.5, 2.0), (1, 3)),
    "clothes": (0.8, (1, 3), (0.2, 0.6), (1, 3)),
    "department_store": (0.5, (1, 1), (0.1, 0.3), (1, 2)),
    "sports": (0.4, (1, 2), (0.1, 0.3), (1, 2)),
    "electronics": (0.6, (1, 2), (0.1, 0.3), (1, 2)),
    "home": (0.5, (1, 1), (0.1, 0.3), (1, 3)),
    "bookstore": (0.5, (1, 2), (0.1, 0.4), (1, 3)),
    "beauty": (0.5, (1, 2), (0.2, 0.5), (1, 2)),
    "toys": (0.3, (1, 1), (0.1, 0.3), (1, 2)),
    "pets": (1.0, (1, 1), (0.8, 1.5), (1, 3)),  # only pet owners
    "cinema": (0.5, (1, 2), (0.3, 1.0), (1, 1)),
    "taxi": (0.7, (1, 2), (1.0, 5.0), (1, 1)),  # every user without a car, more often
    "tobacco": (0.5, (1, 1), (0.3, 1.0), (1, 1)),  # only smokers
}
MONTHLY_KINDS = ("utility", "subscription", "gym")  # one receipt a month on a fixed day
VISIT_SCALE = 0.65  # brings the receipts to about 150-250 per user
# How many of one item a line holds: food and drink sometimes come in sixes, other things almost always one.
QUANTITIES = {"Groceries": ([1, 2, 3, 6], [75, 17, 5, 3]), "Dining": ([1, 2, 3], [80, 15, 5])}
OTHER_QUANTITIES = ([1, 2], [92, 8])
NO_LINES_KINDS = ("restaurant", "fast_food", "cafe", "taxi")  # some receipts show only a total
SERVICE_KINDS = ("restaurant", "cafe")


@dataclass(frozen=True)
class PlannedLine:
    item: str
    brand: str | None
    size_amount: Decimal | None
    size_unit: str | None
    quantity: Decimal
    unit_price: Decimal | None
    line_total: Decimal
    category: str | None  # only when it differs from the receipt's category


@dataclass(frozen=True)
class PlannedReceipt:
    day: date
    shop: str
    currency: str
    total: Decimal
    category: str
    lines: tuple[PlannedLine, ...]


@dataclass(frozen=True)
class SyntheticUser:
    number: int
    today: date
    private_categories: tuple[str, ...]
    shops: tuple[str, ...]
    items: tuple[str, ...]
    receipts: tuple[PlannedReceipt, ...]


def make_users(catalogue: Catalogue, count: int = USER_COUNT) -> list[SyntheticUser]:
    return [make_user(catalogue, number) for number in range(1, count + 1)]


def make_user(catalogue: Catalogue, number: int) -> SyntheticUser:
    return _Planner(catalogue, number).user()


class _Planner:
    def __init__(self, catalogue: Catalogue, number: int) -> None:
        self.catalogue = catalogue
        self.number = number
        self.rng = random.Random(f"fyp-dataset/user/{number}")
        rng = self.rng
        self.today = FIRST_TODAY + timedelta(days=round((number - 1) * 1000 / (USER_COUNT - 1)) + rng.randint(0, 25))
        self.has_car = rng.random() < 0.7
        self.has_pet = rng.random() < 0.3
        self.smokes = rng.random() < 0.3
        self.has_baby = rng.random() < 0.25

        self.shops: dict[str, list[Shop]] = {}
        for kind, (chance, (fewest, most), _, _) in KINDS.items():
            if kind == "taxi" and not self.has_car:
                chance = 1.0
            if not self._wants(kind) or rng.random() >= chance:
                continue
            choices = list(catalogue.shops_of(kind))
            self.shops[kind] = rng.sample(choices, min(len(choices), rng.randint(fewest, most)))
        self.monthly: list[Shop] = [shop for shop, chance in self._monthly_shops() if rng.random() < chance]

        self.items: dict[str, float] = {}  # the user's items and how often each is picked
        self.base_price: dict[str, float] = {}  # per item, a point within its price range
        self.brand: dict[str, str] = {}
        self.size: dict[str, int] = {}
        kinds = set(self.shops) | {shop.kind for shop in self.monthly}
        for item in catalogue.items:
            if not set(item.at) & kinds or not self._may_buy(item):
                continue
            if item.vendors and not any(shop.name in item.vendors for shop in self._all_shops()):
                continue
            if rng.random() < (0.55 if item.category == "Groceries" else 0.45) or item.vendors:
                self._add_item(item)
        for kind in sorted(kinds):  # every shop the user goes to sells them at least one thing (fuel, a taxi ride, ...)
            if not any(kind in self.catalogue.item(name).at for name in self.items):
                candidates = [item for item in catalogue.items if kind in item.at and self._may_buy(item)
                              and not item.vendors]  # fmt: skip
                if candidates:
                    self._add_item(rng.choice(candidates))
        if self.has_car and "fuel" in kinds:
            self._add_item(catalogue.item("fuel"))

        self.private = self._private_categories()

    def _add_item(self, item: Item) -> None:
        if item.name in self.items:
            return
        self.items[item.name] = self.rng.uniform(0.3, 1.0)
        self.base_price[item.name] = self.rng.random()
        if item.brands:
            self.brand[item.name] = self.rng.choice(item.brands)
        if item.sizes:
            self.size[item.name] = self.rng.randrange(len(item.sizes))

    # --- who the user is ---

    def _wants(self, kind: str) -> bool:
        if kind in ("fuel", "car_wash"):
            return self.has_car
        if kind == "pets":
            return self.has_pet
        if kind == "tobacco":
            return self.smokes
        return True

    def _may_buy(self, item: Item) -> bool:
        if item.category == "Pets":
            return self.has_pet
        if item.category == "Tobacco":
            return self.smokes
        if item.name in ("fuel", "car wash", "parking"):
            return self.has_car
        if item.name == "diapers":
            return self.has_baby
        return True

    def _monthly_shops(self) -> Iterator[tuple[Shop, float]]:
        named = {shop.name: shop for shop in self.catalogue.shops}
        yield named["EDL"], 0.95
        yield named["Ishtirak el Hay"], 0.85
        yield named["Ogero"], 0.7
        yield named[self.rng.choice(["Touch", "Alfa"])], 0.9
        for shop in self.catalogue.shops_of("subscription"):
            yield shop, 0.3
        for shop in self.catalogue.shops_of("gym"):
            yield shop, 0.3

    def _all_shops(self) -> list[Shop]:
        return [shop for shops in self.shops.values() for shop in shops] + self.monthly

    def _private_categories(self) -> tuple[str, ...]:
        chosen = []
        if self.has_pet and self.rng.random() < 0.6:
            chosen.append("Pets")
        if self.smokes and self.rng.random() < 0.5:
            chosen.append("Tobacco")
        if any(shop.kind == "subscription" for shop in self.monthly) and self.rng.random() < 0.4:
            chosen.append("Subscriptions")
        if "beauty" in self.shops and self.rng.random() < 0.4:
            chosen.append("Beauty")
        return tuple(chosen)

    # --- the receipts ---

    def user(self) -> SyntheticUser:
        first = self.today - timedelta(days=HISTORY_DAYS)
        receipts: list[PlannedReceipt] = []
        for kind, shops in self.shops.items():
            low, high = KINDS[kind][2]
            if kind == "taxi" and not self.has_car:
                low, high = 3.0, 8.0
            per_day = self.rng.uniform(low, high) * VISIT_SCALE / 30 / len(shops)
            for shop in shops:
                for offset in range(HISTORY_DAYS + 1):
                    if self.rng.random() < per_day:
                        receipt = self._receipt(shop, first + timedelta(days=offset))
                        if receipt is not None:
                            receipts.append(receipt)
        for shop in self.monthly:
            day_of_month = self.rng.randint(1, 28)
            day = date(first.year, first.month, day_of_month)
            while day <= self.today:
                if day >= first:
                    receipt = self._receipt(shop, day)
                    if receipt is not None:
                        receipts.append(receipt)
                day = date(day.year + day.month // 12, day.month % 12 + 1, day_of_month)
        receipts.sort(key=lambda r: (r.day, r.shop))
        return SyntheticUser(
            number=self.number, today=self.today, private_categories=self.private,
            shops=tuple(sorted(shop.name for shop in self._all_shops())), items=tuple(sorted(self.items)),
            receipts=tuple(receipts),
        )  # fmt: skip

    def _receipt(self, shop: Shop, day: date) -> PlannedReceipt | None:
        rng = self.rng
        currency = "LBP" if rng.random() < shop.lbp_share else "USD"
        sold = [self.catalogue.item(name) for name in self.items
                if shop.kind in self.catalogue.item(name).at and self._sold_by(name, shop)]  # fmt: skip
        if not sold:
            return None
        if shop.kind in NO_LINES_KINDS and rng.random() < 0.05:
            low, high = sold[0].price or (Decimal(5), Decimal(20))
            return PlannedReceipt(day, shop.name, currency, self._money(rng.uniform(float(low), float(high)) * 2,
                                                                        currency), shop.category, ())  # fmt: skip
        if shop.kind == "fuel":
            picked = [self.catalogue.item("fuel")] if "fuel" in self.items else []
            extras = [item for item in sold if item.name != "fuel"]
            if extras and rng.random() < 0.3:
                picked.append(rng.choice(extras))
        elif shop.kind == "delivery":
            food = [item for item in sold if item.name != "delivery fee"]
            picked = rng.sample(food, min(len(food), rng.randint(1, 2)))
            if "delivery fee" in self.items:
                picked.append(self.catalogue.item("delivery fee"))
        elif shop.kind in MONTHLY_KINDS:
            picked = [rng.choice(sold)]
        else:
            fewest, most = KINDS[shop.kind][3]
            weights = [self.items[item.name] for item in sold]
            picked = []
            for _ in range(min(len(sold), rng.randint(fewest, most))):
                choice = rng.choices(sold, weights)[0]
                if choice not in picked:
                    picked.append(choice)
        if not picked:
            return None

        lines = [self._line(item, shop, day, currency) for item in picked]
        category = self._receipt_category(shop, lines)
        lines = [line if line.category != category else _without_category(line) for line in lines]
        total = sum((line.line_total for line in lines), Decimal(0))
        total = self._adjusted(total, shop, currency)
        return PlannedReceipt(day, shop.name, currency, total, category, tuple(lines))

    def _sold_by(self, item_name: str, shop: Shop) -> bool:
        vendors = self.catalogue.item(item_name).vendors
        return not vendors or shop.name in vendors

    def _line(self, item: Item, shop: Shop, day: date, currency: str) -> PlannedLine:
        rng = self.rng
        level = _price_level(shop.name) * rng.uniform(0.95, 1.05)
        brand = None
        if item.brands:
            roll = rng.random()
            brand = self.brand[item.name] if roll < 0.7 else rng.choice(item.brands) if roll < 0.85 else None
        category = self._category(item.category)

        if item.weight_g or item.litres:  # weighed, or fuel: the weight or volume, quantity 1
            if item.weight_g:
                amount, unit, (low, high) = rng.randint(*item.weight_g) // 5 * 5, "g", item.per_kg
            else:
                amount, unit, (low, high) = rng.randint(*item.litres) * 1000, "ml", item.per_litre
            per_1000 = float(low) + (float(high) - float(low)) * self.base_price[item.name]
            line_total = self._money(per_1000 * amount / 1000 * level, currency, weighed=True)
            unit_price = line_total if rng.random() < 0.5 else None
            return PlannedLine(item.name, brand, Decimal(amount), unit, Decimal(1), unit_price, line_total, category)

        if item.sizes:
            size = item.sizes[self.size[item.name]] if rng.random() < 0.8 else rng.choice(item.sizes)
            low, high, size_amount, size_unit = size.low, size.high, Decimal(size.amount), size.unit
        else:
            (low, high), size_amount, size_unit = item.price, None, None
        unit = self._money((float(low) + (float(high) - float(low)) * self.base_price[item.name]) * level, currency)
        counts, weights = QUANTITIES.get(item.category, OTHER_QUANTITIES)
        quantity = rng.choices(counts, weights)[0] if shop.kind not in MONTHLY_KINDS else 1
        unit_price = unit if rng.random() >= 0.25 else None
        return PlannedLine(item.name, brand, size_amount, size_unit, Decimal(quantity), unit_price, unit * quantity,
                           category)  # fmt: skip

    def _category(self, category: str) -> str:
        fallback = self.catalogue.private_categories.get(category)
        if fallback is None or category in self.private:
            return category
        return fallback

    def _receipt_category(self, shop: Shop, lines: list[PlannedLine]) -> str:
        """The shop's category, unless every line belongs to one of the user's private categories (a pet shop's
        receipt is Pets for a user who has Pets)."""
        categories = {line.category for line in lines}
        if len(categories) == 1 and next(iter(categories)) in self.private:
            return next(iter(categories))
        return shop.category

    def _adjusted(self, total: Decimal, shop: Shop, currency: str) -> Decimal:
        """Most receipts add up to their lines; some add a service charge, a discount or LBP rounding."""
        roll = self.rng.random()
        if shop.kind in SERVICE_KINDS and roll < 0.25:
            return _rounded(total * Decimal("1.10"), currency)
        if shop.kind == "supermarket" and roll < 0.08:
            return _rounded(total * Decimal("0.95"), currency)
        if currency == "LBP" and roll > 0.7:
            return (total / 10000).quantize(Decimal(1), rounding="ROUND_CEILING") * 10000
        return total

    @staticmethod
    def _money(usd: float, currency: str, weighed: bool = False) -> Decimal:
        if currency == "LBP":
            step = Decimal(1000) if weighed else Decimal(5000)
            amount = (Decimal(str(usd)) * RATE / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
            return max(amount, step)
        amount = (Decimal(str(usd)) * 20).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 20
        return max(amount, Decimal("0.05")).quantize(Decimal("0.01"))


def _rounded(amount: Decimal, currency: str) -> Decimal:
    """An amount already in its own currency, rounded as receipts write it (to 1,000 LBP or 0.05 USD)."""
    if currency == "LBP":
        return (amount / 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP) * 1000
    return ((amount * 20).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 20).quantize(Decimal("0.01"))


def _price_level(shop_name: str) -> float:
    """Each shop is a little cheaper or dearer than others, the same for every user."""
    return random.Random(f"fyp-dataset/shop/{shop_name}").uniform(0.92, 1.12)


def _without_category(line: PlannedLine) -> PlannedLine:
    return PlannedLine(line.item, line.brand, line.size_amount, line.size_unit, line.quantity, line.unit_price,
                       line.line_total, None)  # fmt: skip


# --- writing a user to the database, through the app's own services ---


class Services(Protocol):
    """The app services seeding needs (the evaluation's wiring provides them)."""

    auth: object
    categories: object
    receipts: object


def seed_user(services: Services, user: SyntheticUser) -> int:
    """Create the user, their private categories and their receipts; returns the new user's id. Remove the user
    with `remove_user` afterwards."""
    email = f"dataset-{user.number:02d}-{uuid.uuid4()}@{EMAIL_DOMAIN}"
    user_id = services.auth.register(RegisterRequest(email, f"{uuid.uuid4()}{uuid.uuid4()}")).id
    for name in user.private_categories:
        services.categories.create(user_id, name)
    ids = {category.name: category.id for category in services.categories.list_all(user_id)}
    for receipt in user.receipts:
        services.receipts.create_manual(user_id, ConfirmReceiptRequest(
            vendor_name=receipt.shop, receipt_date=receipt.day, currency=receipt.currency, total=receipt.total,
            primary_category_id=ids[receipt.category], lbp_per_usd=RATE,
            lines=[ReceiptLine(
                description=_printed(line), line_total=line.line_total, quantity=line.quantity,
                unit_price=line.unit_price, normalized_name=line.item, size_amount=line.size_amount,
                size_unit=line.size_unit, brand=line.brand,
                category_id=ids[line.category] if line.category else None,
            ) for line in receipt.lines],
        ))  # fmt: skip
    return user_id


def remove_user(services: Services, user_id: int) -> None:
    """Delete the user with everything they own, through the app."""
    services.auth.delete_account(user_id)


def _printed(line: PlannedLine) -> str:
    """The line as a receipt would print it, e.g. 'RIM WATER 1500ML'."""
    size = f" {line.size_amount.normalize():f}{line.size_unit.upper()}" if line.size_amount is not None else ""
    return f"{line.brand.upper() + ' ' if line.brand else ''}{line.item.upper()}{size}"
