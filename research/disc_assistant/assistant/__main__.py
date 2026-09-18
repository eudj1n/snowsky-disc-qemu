"""Desktop prototype: catalog search, ranked text requests and verified playback."""
import argparse
from dataclasses import replace
import asyncio
import json
import os
import sys

from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.session import sync
from research.disc_assistant.assistant.ranking import rank
from research.disc_assistant.assistant.playback import execute, device_lock
from research.disc_assistant.assistant.intents import ControlIntent, LanguageIntent
from research.disc_assistant.assistant.interpreter import InterpretationContext, interpret_request
from research.disc_assistant.assistant.preferences import effective_config, language_command, response_command
from research.disc_assistant.assistant.journal import Trace, history_command, outcome, debug_stderr
from research.disc_assistant.assistant.responses import Responses, exception_result, validate_locales
from research.disc_assistant.assistant.controls import execute as control
from research.disc_assistant.assistant.queue import observe as observe_queue
from research.disc_assistant.library.store import Store
from research.disc_assistant.library.search.typesense import Search, create_client, signature


def server_identity(config):
    return [config.search_protocol, config.search_host, config.search_port]


def status(config, store):
    head = store.head(config.device_key)
    head['database'] = str(store.path)
    head['index_current'] = bool(head['generation'] and head['generation'] == head['index_generation']
        and head['index_signature'] == signature(config.aliases, server_identity(config)))
    return head


async def search_command(config, store, args, trace, intent=None):
    trace.catalog(store)
    trace.event('search', {'command': args.command, 'query': getattr(args, 'text', getattr(args, 'query', ''))})
    key = os.environ.get(config.api_key_env, '')
    if not key.strip():
        raise ValueError(f'set {config.api_key_env} in the process environment (Compose .env is not auto-loaded)')
    client = create_client(config, key)
    try:
        search = Search(client, config.aliases, server_identity(config))
        if args.command == 'index':
            return await search.build(store, config.device_key)
        if args.command in ('ask', 'rank'):
            ranking = await rank(config, store, search, intent, trace=trace)
            trace.search(ranking)
            if args.command == 'rank' or not ranking['candidates']:
                return ranking
            trace.select(ranking)
            trace.event('execution_started', {'action': 'play'})
            result = execute(config, store, ranking)
            trace.event('execution_result', outcome(result))
            return result
        result = await search.search(store, config.device_key, args.query, limit=args.limit)
        trace.search(result, phase='retrieval')
        return result
    finally:
        await client.api_call.aclose()


def main(argv=None, *, interpreter=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='path to a TOML configuration')
    parser.add_argument('--language', help='select and persist one interaction locale at startup')
    parser.add_argument('--debug', action='store_true', help='stream bounded request traces to stderr')
    parser.add_argument('--source', choices=('cli', 'scheduled'), help='request origin; scheduled is explicit for cron')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('listen', help='persistent interactive console; existing catalog/index')
    sub.add_parser('start', help='connect, sync, index and enter the persistent console')
    language = sub.add_parser('language', help='show/set the saved interaction locale, or reset to TOML defaults')
    language.add_argument('languages', nargs='*')
    response = sub.add_parser('response', help='show/set saved speech policy')
    response.add_argument('arguments', nargs='*')
    sub.add_parser('locales', help='validate installed command and response locales')
    history = sub.add_parser('history', help='inspect/export/prune/clear the local request journal')
    history.add_argument('arguments', nargs=argparse.REMAINDER)
    sub.add_parser('sync', help='read the device catalog twice and publish a SQLite snapshot')
    sub.add_parser('status', help='show locally recorded snapshot/index status; no network calls')
    sub.add_parser('queue', help='read the actual device queue and play mode; no search/index required')
    sub.add_parser('index', help='rebuild Typesense from SQLite; no device connection')
    search = sub.add_parser('search', help='show candidates only; never starts playback')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=10)
    for name, help_text in [('rank', 'explain ranked candidates without playback'),
                            ('ask', 'play the best match or control current playback')]:
        command = sub.add_parser(name, help=help_text)
        command.add_argument('text')
    args = parser.parse_args(argv)
    config = None
    try:
        config = load(args.config)
        base_config = config
        if args.command == 'history':
            config = effective_config(config, language=args.language)
            with Trace(config, 'history', 'history', source=args.source or 'cli', persist=False,
                       event_sink=debug_stderr if args.debug else None) as trace:
                result = trace.finish(history_command(config, args.arguments))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command in ('listen', 'start'):
            from research.disc_assistant.assistant.console import run
            return run(config, bootstrap=args.command == 'start', source=args.source or 'interactive',
                       interpreter=interpreter, language=args.language, debug=args.debug)
        try:
            config = effective_config(config, language=args.language)
        except ValueError:
            recovery = ((args.command == 'language' and args.languages == ['reset']) or
                        (args.command == 'response' and args.arguments == ['reset']))
            if not recovery:
                raise
        text = getattr(args, 'text', getattr(args, 'query', args.command))
        if args.command == 'language':
            text = 'language ' + ' '.join(args.languages)
        if args.command == 'response':
            text = 'response ' + ' '.join(args.arguments)
        with Trace(config, args.command, text, source=args.source or 'cli',
                   event_sink=debug_stderr if args.debug else None) as trace:
            trace.event('parse', {})
            intent = (asyncio.run(interpret_request(args.text, InterpretationContext(config.locale),
                        interpreter=interpreter, trace=trace)) if args.command in ('ask', 'rank') else None)
            if args.command == 'language' or (isinstance(intent, LanguageIntent) and args.command == 'ask'):
                trace.event('preference', {'name': 'language.locale'})
                result = language_command(base_config, [intent.locale] if isinstance(intent, LanguageIntent) else args.languages)
                config = replace(config, locale=result['locale'])
                trace.responses = Responses(config.locale, config.response_mode)
                trace.event('locale_changed', trace.responses.context())
            elif args.command == 'response':
                trace.event('preference', {'name': 'response.mode'})
                result = response_command(base_config, args.arguments)
                config = replace(config, locale=result['locale'], response_mode=result['mode'])
                trace.responses = Responses(config.locale, config.response_mode)
                trace.event('response_preferences', trace.responses.context())
            elif args.command == 'locales':
                result = validate_locales()
            elif args.command == 'queue':
                trace.event('execution_started', {'action': 'queue', 'read_only': True})
                result = observe_queue(config)
            elif isinstance(intent, (ControlIntent, LanguageIntent)):
                if args.command == 'rank':
                    result = {'status': 'planned', 'action': intent.action if isinstance(intent, ControlIntent) else 'set_language', 'requires_search': False}
                else:
                    trace.event('execution_started', {'action': intent.action})
                    result = control(config, intent)
            else:
                result = run_catalog_command(config, args, trace, intent)
            trace.finish(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('status') in ('not_sent', 'uncertain') else 0
    except (ValueError, OSError, RuntimeError) as exc:
        if config is not None:
            print(json.dumps(exception_result(config, exc, source=args.source or 'cli'), ensure_ascii=False, indent=2))
        suffix = f' (request {exc.request_id})' if hasattr(exc, 'request_id') else ''
        print(f'Assistant: {exc}{suffix}', file=sys.stderr)
        return 1
    except Exception as exc:
        if config is not None:
            print(json.dumps(exception_result(config, exc, source=args.source or 'cli'), ensure_ascii=False, indent=2))
        # SDK errors can contain server response bodies. Keep personal data and
        # credentials out of accidental terminal logs.
        suffix = f' (request {exc.request_id})' if hasattr(exc, 'request_id') else ''
        print(f'Assistant: {type(exc).__name__}; check the configured service and credentials{suffix}', file=sys.stderr)
        return 1


def run_catalog_command(config, args, trace, intent=None):
    with Store(config.data_dir) as store:
        if args.command == 'sync':
            trace.event('execution_started', {'action': 'sync', 'read_only': True})
            with device_lock(config.data_dir):
                result = sync(config, store)
        elif args.command == 'status':
            result = status(config, store)
        else:
            result = asyncio.run(search_command(config, store, args, trace, intent))
    return result


if __name__ == '__main__':
    sys.exit(main())
