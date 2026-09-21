"""Interactive command reference shared by adapters."""
HELP = '''Enter Play … / Включи …, Pause / Пауза, Resume / Продолжи, Stop / Стоп,
Next track / Следующий трек, Previous track / Предыдущий трек.
Like / Лайк, Unlike / Не нравится, What is playing? / Что играет?
Volume 40 / Громкость 40, Louder / Громче, Quieter / Тише.
Commands use one active locale; /language CODE changes input and replies.
/connect  /disconnect  /device  /status  /queue  /sync  /index
/search TEXT  /rank TEXT  /explain TEXT  /commands [rebuild|import FILE]
/language [CODE|reset]  /help  /clear  /exit
/response [mode none|errors|all|reset]  /locales
/shadow [on|off]  Compare interpretation sources; never changes execution
/debug [on|off]  Stream request traces for this console session
/transcribe FILE  /rank --audio FILE  /ask --audio FILE  (PCM WAV input)
/history [LIMIT|show ID|export PATH|prune|clear --yes]
Terminal: Up/Down history, Ctrl-R search, Tab completion, Right accepts a suggestion,
Ctrl-L clears the screen, Ctrl-C cancels input, Ctrl-D on empty input exits.
Events are read continuously. Disconnect/exit never stop music or Typesense.
One-shot device commands require /exit to release the local ownership lock.
Offline run.sh search/index/status remain available while this console is open.'''
