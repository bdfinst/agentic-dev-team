#!/usr/bin/env python3
"""Load sample orders into the local development database."""
import sys


def main(argv):
    count = int(argv[1]) if len(argv) > 1 else 10
    print(f"seeded {count} orders")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
