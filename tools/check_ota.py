#!/usr/bin/env python3
"""Read the stock OTA catalog; print only validated version numbers, never URLs."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from fetch_firmware import HTTPSRedirect, https_url
from firmware_profile import DEFAULT_VERSION, load_profile

CATALOG = 'https://discpick.fiio.net/ota_patch_user.json'
MAX_CATALOG = 128 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


def parse_catalog(data):
    # Accept precisely the vendor's trailing ARRAY comma, without rewriting URL
    # strings or accepting malformed/skipped records. Object JSON remains strict.
    if len(data) > MAX_CATALOG:
        raise ValueError('Catalog too large')
    text = data.decode('utf-8-sig').strip()
    if not text.startswith('['):
        raise ValueError('Expected array')
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    rows, sources, pos = [], set(), 1
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == ']':
            if text[pos + 1:].strip() or not rows:
                raise ValueError('Empty array or trailing data')
            return rows
        row, pos = decoder.raw_decode(text, pos)
        if not isinstance(row, dict) or set(row) != {
                'last_version', 'new_version', 'recovery', 'patch_url'}:
            raise ValueError('Unexpected record fields')
        for key in ('last_version', 'new_version', 'recovery'):
            if type(row[key]) is not int or not 1 <= row[key] <= 999999:
                raise ValueError('Invalid version')
        if row['last_version'] in sources or row['new_version'] < row['last_version']:
            raise ValueError('Duplicate source or downgrade')
        if not isinstance(row['patch_url'], str):
            raise ValueError('Invalid package URL')
        url = row['patch_url']
        if any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ValueError('Invalid package URL')
        https_url(url)
        sources.add(row['last_version'])
        # Discard the URL immediately; all later output is safe metadata.
        rows.append({key: row[key] for key in ('last_version', 'new_version', 'recovery')})
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == ',':
            pos += 1
        elif pos >= len(text) or text[pos] != ']':
            raise ValueError('Missing array separator')


def fetch_catalog():
    opener = urllib.request.build_opener(HTTPSRedirect())
    request = urllib.request.Request(CATALOG, headers={'User-Agent': 'snowsky-disc-ota-check'})
    for attempt in range(3):
        try:
            with opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise ValueError('Unexpected HTTP status')
                return parse_catalog(response.read(MAX_CATALOG + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def evaluate(rows, profile):
    current = profile['main_os_version']
    recovery = profile['recovery_os_version']
    selected = next((row for row in rows if row['last_version'] == current), None)
    if selected is None:
        raise ValueError('No route for reviewed version')
    latest = max((row['new_version'], row['recovery']) for row in rows)
    return {
        'current_version': current,
        'current_recovery': recovery,
        'target_version': selected['new_version'],
        'target_recovery': selected['recovery'],
        'latest_version': latest[0],
        'latest_recovery': latest[1],
        'update_available': (selected['new_version'], selected['recovery']) > (current, recovery),
        'newer_release_available': latest > (current, recovery),
    }


def report(result):
    print(json.dumps(result, sort_keys=True))
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with Path(output).open('a') as file:
            for key, value in result.items():
                file.write(f'{key}={str(value).lower()}\n')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        status = 'New firmware advertised' if result['newer_release_available'] else 'No newer firmware advertised'
        with Path(summary).open('a') as file:
            file.write(f'## OTA check: {status}\n\n'
                       '| Version | Main OS | Recovery |\n| --- | --- | --- |\n'
                       f'| Reviewed profile | {result["current_version"]} | {result["current_recovery"]} |\n'
                       f'| Offered to this profile | {result["target_version"]} | {result["target_recovery"]} |\n'
                       f'| Highest advertised pair | {result["latest_version"]} | {result["latest_recovery"]} |\n\n'
                       'Metadata check only. New firmware requires review before integration.\n')
    if result['newer_release_available'] and os.environ.get('GITHUB_ACTIONS') == 'true':
        print('::warning title=New SNOWSKY DISC firmware::'
              f'Main OS {result["latest_version"]}, recovery {result["latest_recovery"]}; review the OTA check summary.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=DEFAULT_VERSION)
    args = parser.parse_args()
    try:
        result = evaluate(fetch_catalog(), load_profile(args.version))
        report(result)
    except Exception:
        # urllib/JSON errors may contain the response or a package URL.
        parser.exit(1, 'OTA check failed: network, catalog, profile, or output error (details suppressed).\n')


if __name__ == '__main__':
    main()
