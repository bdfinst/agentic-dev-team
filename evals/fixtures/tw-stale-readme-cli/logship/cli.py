import argparse

DEFAULT_PORT = 9514


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="logship", description="Forward log files to a collector.")
    p.add_argument("paths", nargs="+", help="Log files or globs to watch")
    p.add_argument("--output", "-o", required=True, help="Collector URL, e.g. tcp://logs.example.com")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Collector port")
    p.add_argument("--quiet", "-q", action="store_true", help="Only print errors")
    p.add_argument("--batch-size", type=int, default=200, help="Lines per send")
    return p
