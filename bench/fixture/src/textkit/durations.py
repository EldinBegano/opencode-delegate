import re

UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
PART = re.compile(r"(\d+)([wdhms])")


def parse_duration(text):
    text = text.strip().lower().replace(" ", "")
    if not text:
        raise ValueError("empty duration")
    total, pos, seen = 0, 0, set()
    for match in PART.finditer(text):
        if match.start() != pos:
            raise ValueError(f"invalid duration: {text!r}")
        unit = match.group(2)
        if unit in seen:
            raise ValueError(f"unit {unit!r} given twice")
        seen.add(unit)
        total += int(match.group(1)) * UNITS[unit]
        pos = match.end()
    if pos != len(text):
        raise ValueError(f"invalid duration: {text!r}")
    return total


def format_duration(seconds, largest=2):
    if seconds < 0:
        raise ValueError("duration must not be negative")
    if seconds == 0:
        return "0s"
    parts = []
    for unit, size in UNITS.items():
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count}{unit}")
    return " ".join(parts[:largest])


def add_durations(*texts):
    return format_duration(sum(parse_duration(text) for text in texts), largest=len(UNITS))


def split_evenly(seconds, parts):
    if parts < 1:
        raise ValueError("parts must be at least 1")
    base, extra = divmod(seconds, parts)
    return [base + 1 if i < extra else base for i in range(parts)]


def within(seconds, limit, tolerance=0):
    return seconds <= parse_duration(limit) + tolerance
