"""The periods a question can name, written exactly as the prompt teaches (approved by the user on 2026-11-07, worked
examples with today 2027-02-10).

Rolling periods use CURRENT_DATE, which the app fills in; named ones (a month, a weekday, the weekend, summer, a range)
are written out as dates, the most recent one up to today. Each period also carries:
- `start` and `end` (end excluded), so tests and the generator know which days it covers;
- a plain description for the question writer (Qwen), never the SQL;
- `words`: what a question must contain to name it (in English or Arabizi), for the checks.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")  # fmt: skip
# Levantine month names (the user's spellings from the seeds where there are some).
ARABIZI_MONTHS = (
    ("kanoun el tene", "kanoun el tani"), ("shbat", "chbat"), ("adar",), ("nisan", "nisen"), ("ayyar",),
    ("7zayran", "hzairan", "7ziran"), ("tammouz", "tamouz", "tamsmouz"), ("ab",), ("ayloul",),
    ("teshreen el awal",), ("teshreen el tene", "teshreen el tani"), ("kanoun el awal",),
)  # fmt: skip
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ARABIZI_WEEKDAYS = (
    ("tanayn", "tanain", "tnen", "tnein", "etnen"), ("taleta", "tleeta", "tleta"),
    ("erb3a", "orb3a", "erbaa", "arbi3a"), ("khamis", "5amis", "khamees"), ("nhar el jem3a", "yom el jem3a", "jom3a"),
    ("sabet", "sebet", "sabt"), ("a7ad", "ahad"),
)  # fmt: skip

THIS_MONTH = ("receipt_date >= date_trunc('month', CURRENT_DATE) "
              "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'")  # fmt: skip
LAST_MONTH = ("receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
              "AND receipt_date < date_trunc('month', CURRENT_DATE)")  # fmt: skip
THIS_WEEK = ("receipt_date >= date_trunc('week', CURRENT_DATE) "
             "AND receipt_date < date_trunc('week', CURRENT_DATE) + INTERVAL '1 week'")  # fmt: skip
LAST_WEEK = ("receipt_date >= date_trunc('week', CURRENT_DATE) - INTERVAL '1 week' "
             "AND receipt_date < date_trunc('week', CURRENT_DATE)")  # fmt: skip
THIS_YEAR = ("receipt_date >= date_trunc('year', CURRENT_DATE) "
             "AND receipt_date < date_trunc('year', CURRENT_DATE) + INTERVAL '1 year'")  # fmt: skip

NUMBER_WORDS = {2: ("2", "two", "tnen", "tneen"), 3: ("3", "three", "tlete", "tleteh"), 6: ("6", "six", "sette"),
                7: ("7", "seven", "sab3a", "sab3"), 10: ("10", "ten", "3ashra"),
                14: ("14", "fourteen", "2 weeks", "two weeks", "jem3ten"), 30: ("30", "thirty", "tleten")}  # fmt: skip


@dataclass(frozen=True)
class Period:
    kind: str
    sql: str  # a condition on receipt_date, or "" for no period
    start: date | None  # first day covered
    end: date | None  # first day after
    description: str
    words: tuple[str, ...]  # a question naming this period contains one of these


def no_period() -> Period:
    return Period("none", "", None, None, "no period (all their receipts)", ())


def this_month(today: date) -> Period:
    start = today.replace(day=1)
    return Period("this_month", THIS_MONTH, start, _next_month(start), "this month",
                  ("this month", "hal shaher", "hal chaher", "hal shahr", "ha shaher"))  # fmt: skip


def last_month(today: date) -> Period:
    end = today.replace(day=1)
    return Period("last_month", LAST_MONTH, _previous_month(end), end, "last month (the previous calendar month)",
                  ("last month", "previous month", "li mara2", "li mar2", "el ablo", "li ablo", "el madi", "li ata3",
                   "ekher shaher"))  # fmt: skip


def this_week(today: date) -> Period:
    start = today - timedelta(days=today.weekday())
    return Period("this_week", THIS_WEEK, start, start + timedelta(days=7), "this week (Monday to Sunday)",
                  ("this week", "hal jem3a", "hal jemaa", "hal osbou3", "hal esbou3", "hal jom3a"))  # fmt: skip


def last_week(today: date) -> Period:
    end = today - timedelta(days=today.weekday())
    return Period("last_week", LAST_WEEK, end - timedelta(days=7), end, "last week (the previous Monday to Sunday)",
                  ("last week", "previous week", "jem3a li mar2it", "jemaa li mar2it", "jem3a li fetit",
                   "osbou3 li mara2", "osbou3 el madi", "jem3a el madye"))  # fmt: skip


def today_period(today: date) -> Period:
    return Period("today", "receipt_date = CURRENT_DATE", today, today + timedelta(days=1), "today",
                  ("today", "lyom", "lyoum", "el yom", "el yawm"))  # fmt: skip


def yesterday(today: date) -> Period:
    day = today - timedelta(days=1)
    return Period("yesterday", "receipt_date = CURRENT_DATE - 1", day, today, "yesterday",
                  ("yesterday", "mbere7", "mberi7", "mbereh", "embere7"))  # fmt: skip


def last_days(today: date, days: int) -> Period:
    return Period(f"last_{days}_days", f"receipt_date > CURRENT_DATE - {days} AND receipt_date <= CURRENT_DATE",
                  today - timedelta(days=days - 1), today + timedelta(days=1),
                  f"the last {days} days (today and the {days - 1} days before)", NUMBER_WORDS[days])  # fmt: skip


def last_weeks(today: date, weeks: int) -> Period:
    days = weeks * 7
    words = ("jem3ten", "2 weeks", "two weeks", "2 jem3a", "osbou3en") if weeks == 2 else NUMBER_WORDS[weeks]
    return Period(f"last_{weeks}_weeks", f"receipt_date > CURRENT_DATE - {days} AND receipt_date <= CURRENT_DATE",
                  today - timedelta(days=days - 1), today + timedelta(days=1),
                  f"the last {weeks} weeks (the last {days} days)", words)  # fmt: skip


def last_months(today: date, months: int) -> Period:
    start = _months_before(today, months) + timedelta(days=1)
    return Period(f"last_{months}_months",
                  f"receipt_date > CURRENT_DATE - INTERVAL '{months} months' AND receipt_date <= CURRENT_DATE",
                  start, today + timedelta(days=1), f"the last {months} months (up to today)",
                  NUMBER_WORDS[months])  # fmt: skip


def this_year(today: date) -> Period:
    start = date(today.year, 1, 1)
    return Period("this_year", THIS_YEAR, start, date(today.year + 1, 1, 1), "this year",
                  ("this year", "hal sene", "hal seneh", "hal sana"))  # fmt: skip


def since_start_of_year(today: date) -> Period:
    return Period("since_start_of_year", "receipt_date >= date_trunc('year', CURRENT_DATE)", date(today.year, 1, 1),
                  today + timedelta(days=1), "since the start of the year (this year so far)",
                  ("men awal el sene", "mn awal el sene", "since the start of the year", "since january",
                   "since the beginning of the year", "this year so far"))  # fmt: skip


def named_month(today: date, month: int) -> Period:
    """A month named without a year: the most recent one up to today."""
    year = today.year if month <= today.month else today.year - 1
    start = date(year, month, 1)
    end = _next_month(start)
    return Period(f"month_{month}", f"receipt_date >= '{start}' AND receipt_date < '{end}'", start, end,
                  f"in {MONTHS[month - 1]} (say the month only, without a year)",
                  (MONTHS[month - 1].lower(),) + ARABIZI_MONTHS[month - 1])  # fmt: skip


def since_month(today: date, month: int) -> Period:
    named = named_month(today, month)
    return Period(f"since_month_{month}", f"receipt_date >= '{named.start}'", named.start, today + timedelta(days=1),
                  f"since {MONTHS[month - 1]} (from the start of that month until today, no year)", named.words)


def weekday(today: date, day: int) -> Period:
    """A weekday (0 = Monday): the most recent one up to today, today included."""
    when = today - timedelta(days=(today.weekday() - day) % 7)
    return Period(f"weekday_{day}", f"receipt_date = '{when}'", when, when + timedelta(days=1),
                  f"on {WEEKDAYS[day]} (the most recent {WEEKDAYS[day]})",
                  (WEEKDAYS[day].lower(),) + ARABIZI_WEEKDAYS[day])  # fmt: skip


def weekend(today: date) -> Period:
    """Saturday and Sunday: this one if today is Saturday or Sunday, otherwise the last one."""
    saturday = today - timedelta(days=(today.weekday() - 5) % 7)
    end = saturday + timedelta(days=2)
    return Period("weekend", f"receipt_date >= '{saturday}' AND receipt_date < '{end}'", saturday, end,
                  "the weekend (Saturday and Sunday)", ("weekend", "wikend", "week-end", "sabet w a7ad"))  # fmt: skip


def summer(today: date) -> Period:
    year = today.year if today >= date(today.year, 6, 1) else today.year - 1
    start, end = date(year, 6, 1), date(year, 9, 1)
    return Period("summer", f"receipt_date >= '{start}' AND receipt_date < '{end}'", start, end,
                  "the summer (June to August, the most recent one)",
                  ("summer", "sayf", "sayfiye", "el sayf", "seyfiye"))  # fmt: skip


def day_range(today: date, month: int, first: int, last: int) -> Period:
    """From one day to another of a named month, both included."""
    start = named_month(today, month).start.replace(day=first)
    end = start.replace(day=last) + timedelta(days=1)
    return Period(f"range_{month}_{first}_{last}", f"receipt_date >= '{start}' AND receipt_date < '{end}'", start,
                  end, f"from the {first} to the {last} of {MONTHS[month - 1]} (both days included, no year)",
                  named_month(today, month).words)  # fmt: skip


def choose(rng: random.Random, today: date, first_day: date) -> Period:
    """A period for a question, from the approved list: this month and last month twice as likely as the others.
    Named periods are picked only where the user has receipts (from `first_day`)."""
    makers = [
        lambda: this_month(today), lambda: this_month(today), lambda: last_month(today), lambda: last_month(today),
        lambda: this_week(today), lambda: last_week(today), lambda: today_period(today), lambda: yesterday(today),
        lambda: last_days(today, rng.choice([3, 7, 10, 14, 30])), lambda: last_weeks(today, rng.choice([2, 3])),
        lambda: last_months(today, rng.choice([2, 3, 6])), lambda: this_year(today),
        lambda: since_start_of_year(today), lambda: _a_named_month(rng, today),
        lambda: since_month(today, _a_past_month(rng, today)), lambda: weekday(today, rng.randrange(7)),
        lambda: weekend(today), lambda: summer(today), lambda: _a_range(rng, today), no_period,
    ]  # fmt: skip
    while True:
        period = rng.choice(makers)()
        if period.start is None or period.start >= first_day:
            return period


def _a_named_month(rng: random.Random, today: date) -> Period:
    return named_month(today, _a_past_month(rng, today))


def _a_past_month(rng: random.Random, today: date) -> int:
    """A month other than the current one (asking for this month by name would be "this month")."""
    return rng.choice([m for m in range(1, 13) if m != today.month])


def _a_range(rng: random.Random, today: date) -> Period:
    first = rng.randint(1, 15)
    return day_range(today, _a_past_month(rng, today), first, first + rng.randint(4, 13))


def _next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


def _previous_month(first_day: date) -> date:
    return date(first_day.year - (first_day.month == 1), (first_day.month - 2) % 12 + 1, 1)


def _months_before(day: date, months: int) -> date:
    """The same date `months` months earlier, moved to the month's last day when needed (as PostgreSQL does)."""
    month_index = day.year * 12 + day.month - 1 - months
    year, month = divmod(month_index, 12)
    last_day = (_next_month(date(year, month + 1, 1)) - timedelta(days=1)).day
    return date(year, month + 1, min(day.day, last_day))
