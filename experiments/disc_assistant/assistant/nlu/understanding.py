"""Single-action grammar and context policy; language-dependent text lives in TOML."""
from dataclasses import asdict
import re
from pathlib import Path
import tomllib

from experiments.disc_assistant.assistant.nlu.command_catalog import digest
from experiments.disc_assistant.assistant.nlu.languages import load_languages, normalized, literal_pattern
from experiments.disc_assistant.assistant.nlu.intents import Intent, ControlIntent, LanguageIntent, language_target, music_intent
from experiments.disc_assistant.assistant.nlu.explain import template_value

DIRECTORY = Path(__file__).parents[1] / 'locales/understanding'
QUOTES = {'"': '"', '«': '»', '“': '”'}


def grammar(locale):
    load_languages((locale,))  # Validate tag and installed ordinary locale first.
    path = DIRECTORY / (locale + '.toml')
    with path.open('rb') as stream:
        value = tomllib.load(stream)
    if set(value) != {'version', 'locale', 'templates', 'language_names', 'controls', 'context'} or value['version'] != 1 or value['locale'] != locale:
        raise ValueError('invalid understanding grammar header')
    keys = {'templates': {'play', 'artist', 'track', 'language'}, 'controls': {'pause', 'resume', 'stop', 'next', 'previous'},
            'context': {'negation', 'reported', 'questions', 'nonmusic', 'connectors', 'actions', 'action_modifiers', 'empty'}}
    for section, fields in keys.items():
        if not isinstance(value[section], dict) or set(value[section]) != fields:
            raise ValueError('invalid understanding grammar sections')
    for section in ('templates', 'language_names', 'controls', 'context'):
        if not isinstance(value[section], dict) or not value[section]:
            raise ValueError('empty understanding grammar section')
        for key, phrases in value[section].items():
            if not isinstance(phrases, list) or not phrases or any(not isinstance(p, str) or not p.strip() or len(p) > 300 or any(ord(c)<32 for c in p) for p in phrases):
                raise ValueError('invalid literal grammar phrases')
            if section == 'templates':
                placeholder = '{language}' if key == 'language' else '{query}'
                if any(p.count(placeholder) != 1 or '{' in p.replace(placeholder, '') or '}' in p.replace(placeholder, '') for p in phrases):
                    raise ValueError('invalid grammar placeholder')
    return value


def phrase_matches(text, phrases, *, start=False):
    return any(re.search((r'^\s*' if start else r'(?<!\w)') + literal_pattern(p) + r'(?!\w)', text, re.IGNORECASE) for p in phrases)


def quote_mask(text):
    chars, close = list(text), None
    for i, char in enumerate(text):
        if close is not None:
            chars[i] = ' '
            if char == close:
                close = None
        elif char in QUOTES:
            chars[i], close = ' ', QUOTES[char]
    return ''.join(chars), close is not None


def single_action(text, locale, rules=None):
    """Small shared execution gate, not multi-action decomposition or planning."""
    if rules is None:
        try:
            rules = grammar(locale)
        except FileNotFoundError:
            return {'supported': True, 'reason': 'no_optional_grammar', 'grammar_sha256': None}
    context = rules['context']
    masked, unclosed = quote_mask(text)
    # A named single-action template may have a compound verb ('find and play').
    # Mask only its fixed prefix; sequencing after the captured argument remains visible.
    for templates in rules['templates'].values():
        for template in sorted(templates, key=len, reverse=True):
            placeholder = 'language' if '{language}' in template else 'query'
            match = template_value(text, [template], placeholder)
            if match:
                start = match[1]['start']
                masked = ' ' * start + masked[start:]
                break
    # Live locale dictionaries also contribute prefixes and action words. Adding
    # a synonym must not create a hole in the shared single-action gate.
    literal = load_languages((locale,))
    music = literal.prefix('commands', text.strip())
    if music and music[0] == 'play':
        start = text.rfind(music[1])
        masked = ' ' * start + masked[start:]
    actions = set(context['actions']) | {p for p, _ in literal.commands}
    modifiers = '|'.join(literal_pattern(p) for p in context['action_modifiers'])
    action = r'(?:(?:' + modifiers + r')\s+){0,2}(?:' + '|'.join(literal_pattern(p) for p in sorted(actions, key=len, reverse=True)) + r')(?!\w)'
    reason = None
    if unclosed:
        reason = 'unclosed_quoted_reference'
    elif ';' in masked and not music:
        reason = 'multiple_actions'
    elif re.search(r';\s*(?:(?:' + '|'.join(literal_pattern(p) for p in context['connectors'])
                   + r')\s+)?' + action, masked, re.IGNORECASE):
        reason = 'multiple_actions'
    else:
        for conjunction in [*context['connectors'], ',']:
            pattern = ((r'(?<!\w)' if conjunction != ',' else '') + literal_pattern(conjunction)
                       + r'\s+' + action)
            if re.search(pattern, masked, re.IGNORECASE):
                reason = 'multiple_actions'
                break
    return {'supported': reason is None, 'reason': reason, 'grammar_sha256': digest(rules)}


def extract(text, locale):
    rules = grammar(locale)
    policy = single_action(text, locale, rules)
    base = {'status': 'rejected', 'label': 'reject', 'intent': None, 'spans': [],
            'reason': 'no_template', 'evidence': {'grammar_sha256': digest(rules), 'policy': policy}}
    if not policy['supported']:
        return {**base, 'status': 'unsupported', 'reason': policy['reason']}
    context = rules['context']
    if text.lstrip().startswith(tuple(QUOTES)):
        return {**base, 'reason': 'quoted_command'}
    controls = {normalized(p): action for action, phrases in rules['controls'].items() for p in phrases}
    if normalized(text) in controls:
        action = controls[normalized(text)]
        return {**base, 'status': 'recognized', 'label': action, 'intent': asdict(ControlIntent(action)), 'reason': 'literal_control'}
    # Context outside a captured music reference can veto a fallback from any source.
    if phrase_matches(text, context['questions'], start=True) or phrase_matches(text, context['reported'], start=True):
        return {**base, 'reason': 'non_command_context'}
    language = template_value(text, sorted(rules['templates']['language'], key=len, reverse=True), 'language')
    if language:
        value, span = language
        names = {normalized(p): code for code, phrases in rules['language_names'].items() for p in phrases}
        target = names.get(normalized(value))
        if target is None:
            try:
                target = language_target(value, load_languages((locale,)))
            except ValueError:
                return {**base, 'status': 'incomplete', 'label': 'language', 'reason': 'unknown_language', 'spans': [span]}
        from experiments.disc_assistant.assistant.responses import validate_locale
        try:
            validate_locale(target)
        except ValueError:
            return {**base, 'status': 'unsupported', 'reason': 'language_not_installed'}
        return {**base, 'status': 'recognized', 'label': 'language', 'intent': asdict(LanguageIntent(target)),
                'reason': 'language_slot', 'spans': [span]}
    for name in ('artist', 'track', 'play'):
        match = template_value(text, sorted(rules['templates'][name], key=len, reverse=True), 'query')
        if not match:
            continue
        value, span = match
        kind = name if name != 'play' else 'auto'
        if name == 'play':
            explicit = load_languages((locale,)).prefix('targets', value)
            if explicit:
                kind, value = explicit
        value = value.strip()
        quoted = len(value) > 1 and value[0] in QUOTES and value[-1] == QUOTES[value[0]]
        missing = {normalized(p) for p in context['empty']} | {p for p, _ in load_languages((locale,)).targets}
        if not value or (kind == 'auto' and not quoted and normalized(value) in missing):
            return {**base, 'status': 'incomplete', 'label': 'play', 'reason': 'missing_music_reference'}
        if kind == 'auto' and not quoted and phrase_matches(value, context['nonmusic'], start=True):
            return {**base, 'status': 'unsupported', 'reason': 'non_music_target'}
        if quoted:
            value = value[1:-1]
        if not value.strip():
            return {**base, 'status': 'incomplete', 'label': 'play', 'reason': 'missing_music_reference'}
        start = text.find(value, span['start'])
        span = {'name': 'query', 'start': start, 'end': start+len(value), 'text': value}
        intent = music_intent('"' + value + '"', kind) if quoted else music_intent(value, kind)
        return {**base, 'status': 'recognized', 'label': 'play', 'intent': asdict(intent), 'spans': [span], 'reason': 'music_slot'}
    if phrase_matches(text, context['negation']):
        return {**base, 'reason': 'negated_command'}
    if phrase_matches(text, context['reported']):
        return {**base, 'reason': 'non_command_context'}
    return base
