from .records import parse_row, parse_rows_header


def load(lines):
    header = parse_rows_header(lines[0])
    return [parse_row(line, header) for line in lines[1:] if line.strip()]


def oldest(lines):
    records = load(lines)
    return max(records, key=lambda r: r["age"])["name"] if records else None
