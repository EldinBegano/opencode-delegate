FIELDS = ("name", "age", "city")


def parse_rows_header(line):
    return [field.strip().lower() for field in line.split(";")]


def parse_row(line, fields=FIELDS):
    values = [value.strip() for value in line.split(";")]
    if len(values) != len(fields):
        raise ValueError(f"expected {len(fields)} fields, got {len(values)}")
    record = dict(zip(fields, values))
    if "age" in record:
        record["age"] = int(record["age"])
    return record


def format_row(record, fields=FIELDS):
    return ";".join(str(record[field]) for field in fields)
