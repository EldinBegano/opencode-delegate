class Table:
    def __init__(self, headers):
        if not headers:
            raise ValueError("a table needs at least one column")
        if len(set(headers)) != len(headers):
            raise ValueError("column names must be unique")
        self.headers = list(headers)
        self.rows = []

    def add_row(self, *values):
        if len(values) != len(self.headers):
            raise ValueError(f"expected {len(self.headers)} values, got {len(values)}")
        self.rows.append(list(values))

    def column(self, name):
        index = self._index(name)
        return [row[index] for row in self.rows]

    def sort_by(self, name, reverse=False):
        index = self._index(name)
        self.rows.sort(key=lambda row: row[index], reverse=reverse)
        return self

    def where(self, name, predicate):
        index = self._index(name)
        result = Table(self.headers)
        result.rows = [list(row) for row in self.rows if predicate(row[index])]
        return result

    def widths(self):
        return [max([len(header)] + [len(str(row[i])) for row in self.rows]) for i, header in enumerate(self.headers)]

    def render(self):
        widths = self.widths()
        lines = [" | ".join(header.ljust(width) for header, width in zip(self.headers, widths))]
        lines.append("-+-".join("-" * width for width in widths))
        for row in self.rows:
            lines.append(" | ".join(cell(value, width) for value, width in zip(row, widths)))
        return "\n".join(lines)

    def to_markdown(self):
        lines = ["| " + " | ".join(self.headers) + " |", "|" + "|".join(" --- " for _ in self.headers) + "|"]
        for row in self.rows:
            lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
        return "\n".join(lines)

    def _index(self, name):
        try:
            return self.headers.index(name)
        except ValueError:
            raise KeyError(name) from None

    def __len__(self):
        return len(self.rows)


def cell(value, width):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value).rjust(width)
    return str(value).ljust(width)
