#!/usr/bin/env bash
echo "boom on first stderr line" >&2
echo "second line of stderr" >&2
exit 1
