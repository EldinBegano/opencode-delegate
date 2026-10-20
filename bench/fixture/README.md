# textkit

Small text helpers.

```python
from textkit.records import parse_row

parse_row("ada;36;london")  # {"name": "ada", "age": 36, "city": "london"}
```

`parse_rows_header` reads the header line of an export.
