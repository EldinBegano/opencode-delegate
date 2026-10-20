import sys

from . import records


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for line in argv:
        print(records.parse_row(line))
    return 0
