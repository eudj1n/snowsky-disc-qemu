#!/usr/bin/env python3
"""Create one tracking issue per advertised OTA main-OS/recovery pair."""
import json
import os
import re
import subprocess
import sys


def api(arguments, payload=None):
    result = subprocess.run(
        ['gh', 'api', '--hostname', 'github.com', *arguments],
        input=json.dumps(payload) if payload is not None else None,
        text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def ensure_issue(repo, current, latest):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid repository')
    for number in (*current, *latest):
        if type(number) is not int or not 1 <= number <= 999999:
            raise ValueError('Invalid version')
    if latest <= current:
        return None, False
    main, recovery = latest
    version = f'{main // 100}.{main % 100:02d}'
    marker = f'<!-- snowsky-disc-ota:{main}:{recovery} -->'
    # List all states directly: search indexing can lag after issue creation.
    # Closed issues also count, so a handled/declined release stays handled.
    pages = api([f'repos/{repo}/issues?state=all&per_page=100', '--paginate', '--slurp'])
    for page in pages:
        for issue in page:
            if 'pull_request' not in issue and marker in (issue.get('body') or ''):
                return issue['number'], False
    body = (
        f'{marker}\n'
        f'The stock OTA catalog advertises **V{version}** '
        f'(main OS **{main}**, recovery **{recovery}**).\n\n'
        f'The reviewed emulator profile at detection was main OS **{current[0]}**, '
        f'recovery **{current[1]}**. This is a vendor release signal; emulator '
        'support has not yet been established.\n\n'
        '## Manual release process\n\n'
        '- [ ] Obtain the package and record verified inventory following `docs/PORTING.md`.\n'
        '- [ ] Prepare a PR for the firmware profile and any required emulator changes; '
        'reference this issue with `Refs #<issue>` so merging does not close it early.\n'
        '- [ ] Complete the required CI and firmware integration checks.\n'
        '- [ ] Prepare the release and document verified behavior and limitations.\n'
        '- [ ] Close this issue manually once release preparation is complete.\n\n'
        'The daily monitor does not download firmware, change runtime profiles, '
        'merge PRs, prepare releases, or close/reopen issues. One issue is created '
        'per advertised main-OS/recovery pair, including recovery-only updates.\n')
    issue = api([f'repos/{repo}/issues', '--method', 'POST', '--input', '-'],
                {'title': f'Firmware V{version} / recovery {recovery}: prepare release', 'body': body})
    return issue['number'], True


def main():
    try:
        repo = os.environ['GH_REPO']
        current = (int(os.environ['OTA_CURRENT_VERSION']), int(os.environ['OTA_CURRENT_RECOVERY']))
        latest = (int(os.environ['OTA_LATEST_VERSION']), int(os.environ['OTA_LATEST_RECOVERY']))
        number, created = ensure_issue(repo, current, latest)
        if number is not None:
            message = f'OTA tracking issue {"created" if created else "already exists"}: #{number}'
            print(message)
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as file:
                    file.write(f'\n{message}: https://github.com/{repo}/issues/{number}\n')
    except Exception:
        # Do not render gh stderr, environment values, or API response bodies.
        print('OTA issue notification failed (details suppressed).', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
