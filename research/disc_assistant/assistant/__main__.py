"""Desktop prototype: catalog search, ranked text requests and verified playback."""
import argparse
import asyncio
import json
import os
import sys

from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.session import sync
from research.disc_assistant.assistant.ranking import rank
from research.disc_assistant.assistant.playback import execute, device_lock
from research.disc_assistant.assistant.intents import parse, ControlIntent
from research.disc_assistant.assistant.languages import load_languages
from research.disc_assistant.assistant.preferences import effective_config, language_command
from research.disc_assistant.assistant.journal import Trace, history_command, outcome
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


async def search_command(config, store, args, trace):
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
            ranking = await rank(config, store, search, args.text, trace=trace)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='path to a TOML configuration')
    parser.add_argument('--source', choices=('cli', 'scheduled'), help='request origin; scheduled is explicit for cron')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('listen', help='persistent interactive console; existing catalog/index')
    sub.add_parser('start', help='connect, sync, index and enter the persistent console')
    language = sub.add_parser('language', help='show/set saved command languages, or reset to TOML defaults')
    language.add_argument('languages', nargs='*')
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
    try:
        config = load(args.config)
        if args.command == 'history':
            print(json.dumps(history_command(config, args.arguments), ensure_ascii=False, indent=2))
            return 0
        if args.command in ('listen', 'start'):
            from research.disc_assistant.assistant.console import run
            return run(config, bootstrap=args.command == 'start', source=args.source or 'interactive')
        if args.command in ('ask', 'rank'):
            config = effective_config(config)
        text = getattr(args, 'text', getattr(args, 'query', args.command))
        if args.command == 'language':
            text = 'language ' + ' '.join(args.languages)
        with Trace(config, args.command, text, source=args.source or 'cli') as trace:
            trace.event('parse', {})
            intent = parse(args.text, load_languages(config.languages)) if args.command in ('ask', 'rank') else None
            if intent:
                trace.intent(intent)
            if args.command == 'language':
                trace.event('preference', {'name': 'language.enabled'})
                result = language_command(config, args.languages)
            elif args.command == 'queue':
                trace.event('execution_started', {'action': 'queue', 'read_only': True})
                result = observe_queue(config)
            elif isinstance(intent, ControlIntent):
                if args.command == 'rank':
                    result = {'status': 'planned', 'action': intent.action, 'requires_search': False}
                else:
                    trace.event('execution_started', {'action': intent.action})
                    result = control(config, intent)
            else:
                result = run_catalog_command(config, args, trace)
            trace.finish(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('status') in ('not_sent', 'uncertain') else 0
    except (ValueError, OSError, RuntimeError) as exc:
        suffix = f' (request {exc.request_id})' if hasattr(exc, 'request_id') else ''
        print(f'Assistant: {exc}{suffix}', file=sys.stderr)
        return 1
    except Exception as exc:
        # SDK errors can contain server response bodies. Keep personal data and
        # credentials out of accidental terminal logs.
        suffix = f' (request {exc.request_id})' if hasattr(exc, 'request_id') else ''
        print(f'Assistant: {type(exc).__name__}; check the configured service and credentials{suffix}', file=sys.stderr)
        return 1


def run_catalog_command(config, args, trace):
    with Store(config.data_dir) as store:
        if args.command == 'sync':
            trace.event('execution_started', {'action': 'sync', 'read_only': True})
            with device_lock(config.data_dir):
                result = sync(config, store)
        elif args.command == 'status':
            result = status(config, store)
        else:
            result = asyncio.run(search_command(config, store, args, trace))
    return result


if __name__ == '__main__':
    sys.exit(main())
