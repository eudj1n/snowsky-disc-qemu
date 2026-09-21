"""Check local Markdown link targets without scanning ignored/private data."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
INLINE = re.compile(r'\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+"[^"]*")?\s*\)')
REFERENCE = re.compile(r'^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', re.MULTILINE)
HTML = re.compile(r'\b(?:href|src)=["\']([^"\']+)["\']')


def prose(text):
    # Examples inside fenced code blocks need not resolve as document links.
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            value = marker[1]
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            lines.append('\n')
        else:
            lines.append(line if fence is None else '\n')
    return ''.join(lines)


def main():
    paths = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT,
    ).decode().split('\0')
    errors = []
    count = 0
    for name in sorted(set(paths)):
        path = ROOT / name
        if path.suffix != '.md' or not path.is_file():
            continue
        count += 1
        text = prose(path.read_text())
        matches = [(m, m[1] or m[2]) for m in INLINE.finditer(text)]
        matches += [(m, m[1]) for pattern in (REFERENCE, HTML) for m in pattern.finditer(text)]
        for match, url in matches:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'):
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                line = text.count('\n', 0, match.start()) + 1
                errors.append(f'{name}:{line}: missing local target {url}')
    for error in errors:
        print(error)
    print(f'Checked {count} Markdown files: {len(errors)} missing local targets')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
