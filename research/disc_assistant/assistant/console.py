"""Foreground application: persistent DISC session and interactive text input."""
import asyncio
from dataclasses import replace
import json
import os
import shlex
import sys
from uuid import uuid4

from research.disc_assistant.assistant.config import Config
from research.disc_assistant.assistant.controls import execute as control
from research.disc_assistant.assistant.intents import ControlIntent, LanguageIntent
from research.disc_assistant.assistant.languages import load_languages
from research.disc_assistant.assistant.interpreter import InterpretationContext, interpret_request
from research.disc_assistant.assistant.live import DeviceSession
from research.disc_assistant.assistant.preferences import effective_config, language_command, response_command
from research.disc_assistant.assistant.journal import Trace, history_command, debug_line, debug_stderr
from research.disc_assistant.assistant.responses import Responses, exception_result, validate_locales
from research.disc_assistant.assistant.playback import execute as play
from research.disc_assistant.assistant.queue import observe as queue
from research.disc_assistant.assistant.ranking import rank
from research.disc_assistant.assistant.session import sync
from research.disc_assistant.library.search.typesense import Search, create_client, signature
from research.disc_assistant.library.store import Store

HELP = '''Enter Play … / Включи …, Pause / Пауза, Resume / Продолжи, Stop / Стоп,
Next track / Следующий трек, Previous track / Предыдущий трек.
Commands use one active locale; /language CODE changes input and replies.
/connect  /disconnect  /device  /status  /queue  /sync  /index
/search TEXT  /rank TEXT  /language [CODE|reset]  /help  /clear  /exit
/response [mode none|errors|all|reset]  /locales
/debug [on|off]  Stream request traces for this console session
/history [LIMIT|show ID|export PATH|prune|clear --yes]
Terminal: Up/Down history, Ctrl-R search, Tab completion, Right accepts a suggestion,
Ctrl-L clears the screen, Ctrl-C cancels input, Ctrl-D on empty input exits.
Events are read continuously. Disconnect/exit never stop music or Typesense.
One-shot device commands require /exit to release the local ownership lock.
Offline run.sh search/index/status remain available while this console is open.'''


class Application:
    def __init__(self, config: Config, *, session_factory=DeviceSession, source='interactive', interpreter=None, language=None,
                 debug=False, debug_output=debug_stderr):
        self.base_config, self.session_factory = config, session_factory
        self.config = effective_config(config, language=language)
        self.interpreter = interpreter
        self.debug, self.debug_output = debug, debug_output
        self.rules = load_languages((self.config.locale,))
        self.session_id, self.source = uuid4().hex, source

    def __enter__(self):
        self.session = self.session_factory(self.config)
        self.session.__enter__()
        try:
            self.store = Store(self.config.data_dir)
        except BaseException:
            self.session.__exit__(*sys.exc_info())
            raise
        self.session.connect()
        return self

    def __exit__(self, *args):
        self.session.__exit__(*args)
        self.store.close()

    def device_call(self, callback):
        client = None
        operation_id = uuid4().hex
        try:
            with self.session.operation() as client:
                result = callback(client)
                result.setdefault('operation_id', operation_id)
                if client.closed.is_set() and result.get('mutation_attempted'):
                    result.update(status='uncertain', reason='connection lost during operation; no replay')
                return result
        except (OSError, ValueError, RuntimeError) as exc:
            attempted = bool(client and client.mutation_attempted)
            return {'operation_id': operation_id, 'status': 'uncertain' if attempted else 'not_sent',
                    'mutation_attempted': attempted, 'reason': str(exc), 'error_type': type(exc).__name__}

    async def search(self, command, text='', *, intent=None, reuse=False, trace=None):
        if trace:
            trace.catalog(self.store)
            trace.event('search', {'command': command, 'query': text})
        key = os.environ.get(self.config.api_key_env, '')
        if not key.strip():
            raise ValueError(f'search is unavailable: set {self.config.api_key_env}; controls remain available')
        client = create_client(self.config, key)
        server = [self.config.search_protocol, self.config.search_host, self.config.search_port]
        search = Search(client, self.config.aliases, server)
        try:
            if command == 'index':
                head = self.store.head(self.config.device_key)
                if (reuse and head['collection'] and head['generation'] == head['index_generation']
                        and head['index_signature'] == search.signature):
                    from typesense.exceptions import ObjectNotFound
                    try:
                        info = await client.collections[head['collection']].retrieve()
                        if info.get('num_documents') == head['track_count']:
                            return dict(head, reused=True)
                    except ObjectNotFound:
                        pass
                return await search.build(self.store, self.config.device_key)
            if command == 'rank':
                result = await rank(self.config, self.store, search, intent, trace=trace)
            else:
                result = await search.search(self.store, self.config.device_key, text)
            if trace:
                trace.search(result, phase='ranking' if command == 'rank' else 'retrieval')
            return result
        finally:
            await client.api_call.aclose()

    def status(self):
        head = self.store.head(self.config.device_key)
        server = [self.config.search_protocol, self.config.search_host, self.config.search_port]
        head['index_current'] = bool(head['generation'] and head['generation'] == head['index_generation']
                                    and head['index_signature'] == signature(self.config.aliases, server))
        return {'session': self.session.status(), 'library': head,
                'language': {'locale': self.config.locale},
                'response_preferences': {'mode': self.config.response_mode},
                'dialogue': {'enabled': False}}

    def device(self):
        state = self.session.status()
        return {'device': {'key': self.config.device_key, 'host': self.config.host,
                           'tcp_port': self.config.tcp_port, 'http_port': self.config.http_port},
                'session': {key: state[key] for key in ('connection', 'enabled', 'generation', 'last_error')}}

    def request(self, line, *, source=None, reuse_index=False):
        if not line.strip():
            return None
        command = line.strip().split(maxsplit=1)[0][1:] if line.strip().startswith('/') else 'ask'
        # History still gets timing, but never persists inspection/export/clear.
        with Trace(self.config, command, line, source=source or self.source, session_id=self.session_id,
                   event_sink=self.trace_event, persist=command != 'history') as trace:
            if command == 'history':
                return trace.finish(history_command(self.config, shlex.split(line.strip())[1:]))
            if hasattr(self, 'session'):
                state = self.session.status()
                trace.event('connection', {k: state[k] for k in ('generation', 'connection')})
            trace.event('parse', {})
            return trace.finish(self._request(line, trace, reuse_index=reuse_index))

    def trace_event(self, event):
        if self.debug:
            self.debug_output(event)

    def interpret(self, text, trace):
        playback = 'unknown'
        if hasattr(self, 'session'):
            observed = self.session.status().get('observation', {}).get('playback')
            if observed in ('playing', 'paused', 'stopped'):
                playback = observed
        return asyncio.run(interpret_request(text, InterpretationContext(self.config.locale, playback),
                                            interpreter=self.interpreter, trace=trace))

    def language(self, arguments, trace):
        trace.event('preference', {'name': 'language.locale'})
        result = language_command(self.base_config, arguments)
        self.config = replace(self.config, locale=result['locale'])
        self.rules = load_languages((self.config.locale,))
        trace.responses = Responses(self.config.locale, self.config.response_mode)
        trace.event('locale_changed', trace.responses.context())
        return result

    def _request(self, line, trace, *, reuse_index=False):
        line = line.strip()
        if not line:
            return None
        if line.startswith('/'):
            command, _, text = line[1:].partition(' ')
            text = text.strip()
            if command == 'debug':
                if text not in ('', 'on', 'off'):
                    raise ValueError('/debug accepts on or off')
                if text:
                    self.debug = text == 'on'
                return {'debug': {'enabled': self.debug, 'scope': 'session'}}
            if command == 'language':
                return self.language(text.split(), trace)
            if command == 'response':
                trace.event('preference', {'name': 'response.mode'})
                result = response_command(self.base_config, text.split())
                self.config = replace(self.config, locale=result['locale'], response_mode=result['mode'])
                self.rules = load_languages((self.config.locale,))
                trace.responses = Responses(self.config.locale, self.config.response_mode)
                trace.event('response_preferences', trace.responses.context())
                return result
            if command in ('search', 'rank'):
                if not text:
                    raise ValueError(f'/{command} needs text')
                if command == 'rank':
                    intent = self.interpret(text, trace)
                    if isinstance(intent, (ControlIntent, LanguageIntent)):
                        return {'status': 'planned', 'action': intent.action if isinstance(intent, ControlIntent) else 'set_language',
                                'requires_search': False}
                    return asyncio.run(self.search(command, text, intent=intent, trace=trace))
                return asyncio.run(self.search(command, text, trace=trace))
            if text:
                raise ValueError(f'/{command} takes no arguments')
            if command == 'locales':
                return validate_locales()
            if command == 'help':
                return {'help': HELP}
            if command == 'exit':
                return {'status': 'exit'}
            if command == 'clear':
                return {'status': 'clear_screen'}
            if command == 'status':
                return self.status()
            if command == 'device':
                return self.device()
            if command == 'disconnect':
                self.session.disconnect()
                return self.session.status()
            if command == 'connect':
                self.session.connect()
                return self.session.status()
            if command == 'queue':
                trace.event('execution_started', {'action': 'queue', 'read_only': True})
                return self.device_call(lambda client: queue(self.config, shared=client))
            if command == 'sync':
                trace.event('execution_started', {'action': 'sync', 'read_only': True})
                return self.device_call(lambda client: sync(self.config, self.store, shared=client, reuse_unchanged=True))
            if command == 'index':
                trace.event('index', {})
                return asyncio.run(self.search('index', reuse=reuse_index, trace=trace))
            raise ValueError('unknown console command; use /help')
        # An online interpreter may take time: pin before interpretation, not after it.
        generation = self.session.status()['generation'] if hasattr(self, 'session') else None
        intent = self.interpret(line, trace)
        if isinstance(intent, LanguageIntent):
            return self.language([intent.locale], trace)
        if generation is not None and generation != self.session.status()['generation']:
            return {'status': 'not_sent', 'mutation_attempted': False, 'reason': 'session changed during interpretation'}
        if isinstance(intent, ControlIntent):
            trace.event('execution_started', {'action': intent.action})
            return self.device_call(lambda client: control(self.config, intent, shared=client))
        # Pin the request to the current connection BEFORE potentially slow search.
        ranking = asyncio.run(self.search('rank', line, intent=intent, trace=trace))
        if not ranking['candidates']:
            return ranking
        trace.select(ranking)
        def execute(client):
            if generation != self.session.status()['generation']:
                raise ConnectionError('session changed during search; request a new selection')
            return play(self.config, self.store, ranking, shared=client)
        trace.event('execution_started', {'action': 'play'})
        return self.device_call(execute)


def run(config, *, bootstrap=False, input_fn=None, output=print, source='interactive', interpreter=None, language=None,
        debug=False):
    interactive_output = sys.stdin.isatty() and sys.stdout.isatty()
    terminal = None
    def write(text, role='result'):
        if terminal is not None and output is print:
            terminal.write(text, role)
        else:
            output(text)

    def emit(result):
        if result is not None:
            role = ('error' if result.get('status') in ('error', 'not_sent', 'not_found')
                    else 'warning' if result.get('status') == 'uncertain' else 'result')
            if interactive_output and isinstance(result.get('help'), str):
                write(result['help'], role)
            else:
                write(json.dumps(result, ensure_ascii=False, indent=2), role)

    def emit_debug(event):
        if interactive_output:
            write(debug_line(event), 'debug')
        else:
            debug_stderr(event)

    with Application(config, source=source, interpreter=interpreter, language=language,
                     debug=debug, debug_output=emit_debug) as app:
        if input_fn is None and interactive_output and os.environ.get('TERM') != 'dumb':
            from research.disc_assistant.assistant.terminal import Terminal
            terminal = Terminal(app.config, lambda: app.rules)
        read_input = input_fn or input
        try:
            app.session.wait_ready(config.timeout * 4 + 1)
            write('Persistent DISC console. /help lists commands; /exit releases the connection.')
            emit(app.status())
            if bootstrap:
                try:
                    imported = app.request('/sync', source='startup')
                    emit(imported)
                    if imported.get('status') not in ('not_sent', 'uncertain'):
                        emit(app.request('/index', source='startup', reuse_index=True))
                except Exception as exc:
                    write(f'Startup search preparation unavailable ({type(exc).__name__}); controls remain available.', 'warning')
            while True:
                try:
                    try:
                        line = terminal.read() if terminal else read_input(
                            f'{app.config.device_key}> ' if interactive_output else '')
                    except KeyboardInterrupt:
                        if terminal:
                            continue  # Cancel input only; no request or mutation has begun.
                        raise
                    result = app.request(line)
                    if result and result.get('status') == 'exit':
                        break
                    if not terminal or not terminal.after_command(line, result):
                        emit(result)
                except (EOFError, KeyboardInterrupt):
                    raise
                except (ValueError, OSError, RuntimeError) as exc:
                    emit(dict(exception_result(app.config, exc, source=source), reason=str(exc)))
                except Exception as exc:
                    # SDK errors can include server bodies. Never print secrets.
                    emit(exception_result(app.config, exc, source=source))
        except (EOFError, KeyboardInterrupt):
            write('Console closed. In-flight writes are not replayed; inspect player state if interrupted.')
    return 0
