"""Explicit, local listing references for staff replies."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from urllib.parse import urlsplit


_CODE = re.compile(r"(?<![A-Za-z0-9_-])CL-[0-9A-F]{12}(?![A-Za-z0-9_-])", re.I)
_URL = re.compile(r'''https?://[^\s<>"']+''', re.I)
_TRAILING_URL_PUNCTUATION = ".,;:!?"


def _row(row):
    if not isinstance(row, Mapping):
        raise ValueError('Listing rows must be objects')
    values = {key: row.get(key) for key in ('id', 'url', 'title')}
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError('Listing rows require non-empty id, url and title')
    url = values['url'].strip()
    try:
        parsed = urlsplit(url)
    except ValueError:
        parsed = None
    if parsed is None or parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc or any(char.isspace() for char in url):
        raise ValueError('Listing rows require a valid HTTP(S) URL')
    return values['id'].strip(), url, values['title'].strip()


def reference(row):
    """Return the stable human-readable code for one validated listing."""
    _, url, _ = _row(row)
    digest = hashlib.sha256(url.encode()).hexdigest()[:12].upper()
    return 'CL-' + digest


def _url_from_match(match):
    value = match.group(0)
    while value and value[-1] in _TRAILING_URL_PUNCTUATION:
        value = value[:-1]
    pairs = {')': '(', ']': '[', '}': '{'}
    while value and value[-1] in pairs and value.count(value[-1]) > value.count(pairs[value[-1]]):
        value = value[:-1]
    return value


def _references(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Reply must contain exactly one listing reference')
    urls = []
    masked = list(text)
    for match in _URL.finditer(text):
        url = _url_from_match(match)
        if url:
            urls.append(url)
            for position in range(*match.span()):
                masked[position] = ' '
    codes = [value.upper() for value in _CODE.findall(''.join(masked))]
    refs = [('url', url) for url in urls] + [('code', code) for code in codes]
    if len(refs) != 1:
        raise ValueError('Reply must contain exactly one listing reference')
    return refs[0]


def _index(rows):
    try:
        rows = list(rows)
    except TypeError:
        raise ValueError('Known listing rows are required') from None
    by_code = {}
    by_url = {}
    for row in rows:
        identity = _row(row)
        code = reference(row)
        for index, key in ((by_code, code), (by_url, identity[1])):
            old = index.get(key)
            if old is not None and old[0] != identity:
                raise ValueError('Conflicting listing records share '+code)
            index.setdefault(key, (identity, row))
    return by_code, by_url


def resolve(text, rows):
    """Resolve one explicit code or exact URL against supplied listing rows."""
    kind, value = _references(text)
    by_code, by_url = _index(rows)
    match = (by_code if kind == 'code' else by_url).get(value)
    if match is None:
        raise ValueError('Unknown listing reference: '+value)
    return match[1]
