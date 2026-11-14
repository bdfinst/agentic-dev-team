"""Turn a post title into a URL slug."""
import re
import sys


def slugify(title):
    words = re.split(r"\s+", title.strip().lower())
    return "-".join(w for w in words if w)


def main(argv):
    if len(argv) < 2 or not argv[1].strip():
        print("error: empty title", file=sys.stderr)
        return 2
    print(slugify(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
