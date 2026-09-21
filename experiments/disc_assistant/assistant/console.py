"""Interactive terminal adapter for the shared Assistant application."""
import json
import os
import sys

from experiments.disc_assistant.assistant.application import Application
from experiments.disc_assistant.assistant.console_help import HELP
from experiments.disc_assistant.assistant.journal import debug_line, debug_stderr
from experiments.disc_assistant.assistant.responses import exception_result


def run(config, *, bootstrap=False, input_fn=None, output=print, source='interactive', interpreter=None, language=None,
        debug=False, transcriber=None):
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
                     debug=debug, debug_output=emit_debug, transcriber=transcriber) as app:
        if input_fn is None and interactive_output and os.environ.get('TERM') != 'dumb':
            from experiments.disc_assistant.assistant.terminal import Terminal
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
