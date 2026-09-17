"""Read-only desktop prototype: sync, status, index and search."""
import argparse
import asyncio
import json
import os
import sys

from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.session import sync
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


async def search_command(config, store, args):
    key = os.environ.get(config.api_key_env, '')
    if not key.strip():
        raise ValueError(f'set {config.api_key_env} in the process environment (Compose .env is not auto-loaded)')
    client = create_client(config, key)
    try:
        search = Search(client, config.aliases, server_identity(config))
        if args.command == 'index':
            return await search.build(store, config.device_key)
        return await search.search(store, config.device_key, args.query, limit=args.limit)
    finally:
        await client.api_call.aclose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='path to a TOML configuration')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('sync', help='read the device catalog twice and publish a SQLite snapshot')
    sub.add_parser('status', help='show locally recorded snapshot/index status; no network calls')
    sub.add_parser('index', help='rebuild Typesense from SQLite; no device connection')
    search = sub.add_parser('search', help='show candidates only; never starts playback')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=10)
    args = parser.parse_args(argv)
    try:
        config = load(args.config)
        with Store(config.data_dir) as store:
            if args.command == 'sync':
                result = sync(config, store)
            elif args.command == 'status':
                result = status(config, store)
            else:
                result = asyncio.run(search_command(config, store, args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'Assistant: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        # SDK errors can contain server response bodies. Keep personal data and
        # credentials out of accidental terminal logs.
        print(f'Assistant: {type(exc).__name__}; check the configured service and credentials', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
