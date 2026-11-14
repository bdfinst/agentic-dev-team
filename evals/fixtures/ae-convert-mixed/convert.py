"""Temperature conversion CLI: python3 convert.py --to f|c <value>."""
import sys


def c_to_f(c):
    return c * 9 / 5 + 32


def f_to_c(f):
    return f - 32 * 5 / 9


def main(argv):
    if len(argv) != 4 or argv[1] != "--to" or argv[2] not in ("f", "c"):
        print("usage: convert.py --to f|c <value>", file=sys.stderr)
        return 64
    value = float(argv[3])
    result = c_to_f(value) if argv[2] == "f" else f_to_c(value)
    print(round(result, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
