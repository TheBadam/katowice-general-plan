#!/usr/bin/env bash
# Rebuild the static "Environmental impact on Katowice plan" viewer
# (same export as export_katowice.sh) and preview it locally with Python's
# simple built-in web server. Extra arguments are passed to gml_viewer.py
# (e.g. -o map.png for a preview image).
cd "$(dirname "$0")"

"$PWD/export_katowice.sh" "$@" || exit $?
echo
echo "Preview: http://127.0.0.1:8000/  (Ctrl-C to stop)"
exec python3 -m http.server -d static_site 8000
