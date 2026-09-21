"""TTS-only pronunciation preparation; never modify commands or catalog metadata.

Identity is intentional until locale pronunciation rules have listening evidence.
A future locale dictionary belongs here, with a new revision included in cache and
journal provenance. Do not transliterate entire responses indiscriminately.
"""
REVISION = 'identity-v1'


def prepare(text: str, locale: str) -> str:
    return text
