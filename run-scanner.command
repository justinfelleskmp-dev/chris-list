#!/bin/zsh
cd "$(dirname "$0")"
git pull --ff-only || exit 1
/opt/homebrew/bin/python3 scanner.py --publish
