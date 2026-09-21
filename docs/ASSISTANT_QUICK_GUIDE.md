# Disc Assistant command quick guide

Type or say **one command at a time**. Choose one interaction language with
`/language ru` or `/language en`; music names can use any language.
Open the browser with `./experiments/disc_assistant/run.sh web --bootstrap`.
Microphone input uses the same commands as text. Enable browser sound for replies.

| Task | Russian examples | English examples |
| --- | --- | --- |
| Play music | `Включи Numb` | `Play Numb` |
| Specify artist and track | `Включи Linkin Park — Numb` | `Play Linkin Park — Numb` |
| Play an artist | `Включи исполнителя Linkin Park` | `Play artist Linkin Park` |
| Play an album | `Включи альбом Meteora` | `Play album Meteora` |
| Pause / resume | `Пауза` / `Продолжи` | `Pause` / `Resume` |
| Stop (pause, retaining the queue) | `Стоп` | `Stop` |
| Navigate | `Следующий трек` / `Предыдущий трек` | `Next track` / `Previous track` |
| Add current track to favorites | `Лайк`, `Нравится` | `Like`, `Like this song` |
| Remove current track from favorites | `Дизлайк`, `Не нравится` | `Dislike`, `Unlike` |
| Ask about the current track | `Что играет?`, `Что сейчас играет?`, `Какой трек сейчас играет?`, `Какая песня сейчас играет?` | `What is playing?`, `What song is playing?` |
| Set volume | `Громкость 40`, `Громкость сорок` | `Volume 40`, `Volume forty` |
| Decrease volume | `Тише`, `Сделай тише` | `Quieter`, `Make it quieter` |
| Increase volume | `Громче`, `Сделай громче` | `Louder`, `Make it louder` |

Favorites apply to the current track, including while paused. Repeating a like
or removing a track that is not in favorites does nothing. Dislike does not skip,
delete or create a separate dislike list. A current-track question identifies a
paused track as paused; unavailable playback is reported explicitly.

An unqualified music request searches the active album first, then its artist,
then the whole library. An artist queue starts with artist tracks. Context must
be established from fresh queue membership; an arbitrary playlist does not become
an album just because its current track has an album tag. Weak scoped matches
fall through to wider search; an explicit artist or album keeps its requested
scope. If playback context changes during search, request a new selection.

Volume uses the player's **0–120 device units**, not percentages. Absolute values
outside that range are rejected. Relative commands stop at 0 or 120. Both steps
default to 20; configure them independently in `~/disc-assistant.toml`, then
restart the Assistant:

```toml
[volume]
up_step = 20
down_step = 20
```

Each step must be an integer from 1 to 120. Controls and current-track questions
work without the search service. Music search needs a current library index.

Use `/response mode all` for spoken confirmations, `errors` for problems and
answers to current-track questions, or `none` to disable spoken replies. Browser
sound opt-in is required in every mode. An uncertain result is never retried
automatically. See the [full command reference](ASSISTANT_COMMANDS.md) for setup,
previews, diagnostics and maintenance.
