"""Text/context -> validated intentions. Providers cannot access the Controller."""
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from research.disc_assistant.assistant.intents import Intent, ControlIntent, LanguageIntent, parse
from research.disc_assistant.assistant.languages import load_languages
from research.disc_assistant.assistant.providers import ProviderInfo, ProviderUnavailable, InvalidProviderResult


@dataclass(frozen=True)
class InterpretationContext:
    locale: str
    playback: Literal['playing', 'paused', 'stopped', 'unknown'] = 'unknown'
    catalog_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class Interpretation:
    status: Literal['recognized', 'unrecognized', 'unsupported']
    intent: Intent | ControlIntent | LanguageIntent | None = None


class Interpreter(Protocol):
    info: ProviderInfo

    async def interpret(self, text: str, context: InterpretationContext) -> Interpretation: ...


class UnsupportedCommand(ValueError):
    pass


class RuleInterpreter:
    info = ProviderInfo('rules', 'literal-v3', 'local')

    async def interpret(self, text, context):
        rules = load_languages((context.locale,))
        try:
            return Interpretation('recognized', parse(text, rules))
        except ValueError:
            return Interpretation('unrecognized')


def validate_intent(intent):
    def text(value):
        return isinstance(value, str) and 1 <= len(value) <= 1000 and bool(value.strip()) and not any(ord(c) < 32 for c in value)
    if type(intent) is ControlIntent:
        valid = intent.action in ('pause', 'resume', 'stop', 'next', 'previous')
    elif type(intent) is LanguageIntent:
        from research.disc_assistant.assistant.responses import validate_locale
        try:
            validate_locale(intent.locale)
            valid = True
        except ValueError:
            valid = False
    elif type(intent) is Intent:
        valid = (text(intent.query) and intent.kind in ('auto', 'artist', 'track')
                 and all(value is None or text(value) for value in (intent.artist, intent.title))
                 and ((intent.artist is None and intent.title is None)
                      or (intent.kind == 'track' and intent.artist is not None and intent.title is not None)))
    else:
        valid = False
    if not valid:
        raise InvalidProviderResult('invalid interpreter intent')
    return intent


async def _interpret_request(text, context, *, interpreter=None, trace=None):
    if (not isinstance(text, str) or not 1 <= len(text) <= 1000
            or any(ord(c) < 32 for c in text)):
        raise ValueError('command must contain 1..1000 characters without control characters')
    provider = interpreter if interpreter is not None else RuleInterpreter()
    if trace:
        trace.event('interpretation_started', {'provider': asdict(provider.info), 'locale': context.locale})
    try:
        from research.disc_assistant.assistant.understanding import single_action
        policy = single_action(text, context.locale)
        if trace:
            trace.event('single_action_policy', policy)
        if trace:
            trace.stage = 'interpretation_started'
        result = await provider.interpret(text, context) if policy['supported'] else Interpretation('unsupported')
    except InvalidProviderResult as exc:
        raise InvalidProviderResult('invalid interpreter result') from exc
    except Exception as exc:
        # SDK exceptions may contain request bodies or credentials. Keep a stable,
        # safe error at the application boundary. Cancellation is a BaseException.
        raise ProviderUnavailable('interpreter unavailable') from exc
    if type(result) is not Interpretation or result.status not in ('recognized', 'unrecognized', 'unsupported'):
        raise InvalidProviderResult('invalid interpretation result')
    if result.status != 'recognized':
        if result.intent is not None:
            raise InvalidProviderResult('unsuccessful interpretation must not contain an intent')
        if trace:
            trace.event('interpretation', {'status': result.status})
        if result.status == 'unsupported':
            raise UnsupportedCommand('unsupported command')
        raise ValueError('command not recognized')
    intent = validate_intent(result.intent)
    if trace:
        trace.event('interpretation', {'status': result.status})
        trace.intent(intent)
    return intent


async def interpret_request(text, context, *, interpreter=None, trace=None, shadow=None, shadow_timeout_ms=100):
    """Primary owns execution; independent shadow evidence is never substituted."""
    import asyncio
    if not isinstance(text, str) or not 1 <= len(text) <= 1000 or any(ord(c) < 32 for c in text):
        raise ValueError('command must contain 1..1000 characters without control characters')
    from research.disc_assistant.assistant.interpretation_sources import collect, comparison
    task = asyncio.create_task(collect(text, context, shadow, timeout_ms=shadow_timeout_ms)) if shadow else None
    primary = {'status': 'unavailable', 'intent': None}
    cancelled = False
    try:
        intent = await _interpret_request(text, context, interpreter=interpreter, trace=trace)
        primary = {'status': 'recognized', 'intent': asdict(intent)}
        return intent
    except asyncio.CancelledError:
        cancelled = True
        raise
    except UnsupportedCommand:
        primary['status'] = 'unsupported'
        raise
    except ValueError as exc:
        primary['status'] = 'unavailable' if isinstance(exc, InvalidProviderResult) else 'unrecognized'
        raise
    finally:
        if task is not None:
            if cancelled:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                try:
                    results = await task
                    record = {'primary': primary, 'context': asdict(context), 'sources': results,
                              'comparison': comparison(primary, results), 'execution_source': 'primary_only'}
                except Exception as exc:
                    record = {'status': 'unavailable', 'error_type': type(exc).__name__}
                if trace:
                    previous_stage = trace.stage
                    try:
                        trace.event('interpretation_shadow', record)
                    finally:
                        trace.stage = previous_stage
