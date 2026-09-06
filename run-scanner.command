#!/bin/zsh
cd "$(dirname "$0")" || exit 1
git pull --ff-only || print -u2 "Code update unavailable; scanning with the installed version."
/opt/homebrew/bin/python3 scanner.py --publish
