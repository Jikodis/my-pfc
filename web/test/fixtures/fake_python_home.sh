#!/bin/sh
# Stands in for python: prints the script's name check and its arguments as JSON.
case "$1" in
  */automations/scripts/web_data.py) printf '{"date": "2025-11-01", "args": ["%s"]}\n' "$2" ;;
  *) echo "unexpected script: $1" >&2; exit 1 ;;
esac
