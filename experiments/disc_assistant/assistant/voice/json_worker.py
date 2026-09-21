"""Owned, resident optional-model process; bounded messages and cancellation cleanup."""
import asyncio
import json
import os
from pathlib import Path

from experiments.disc_assistant.assistant.voice.contracts import InvalidSpeech, SpeechUnavailable

REPO = Path(__file__).resolve().parents[4]
LIMIT = 9 * 1024 * 1024


class JsonWorker:
    def __init__(self, python, module, settings, *, timeout=120):
        self.python = str(Path(python).expanduser().absolute())
        self.module, self.settings, self.timeout = module, settings, timeout
        self.process = None
        self.busy = False

    def available(self):
        return Path(self.python).is_file()

    async def read(self):
        try:
            line = await self.process.stdout.readline()
            if not line.endswith(b'\n') or len(line) > LIMIT:
                raise ValueError('bad message length')
            result = json.loads(line)
            if not isinstance(result, dict):
                raise ValueError('bad message type')
            return result
        except (ValueError, UnicodeError) as exc:
            raise InvalidSpeech('invalid speech worker response') from exc

    async def write(self, value):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() + b'\n'
        if len(data) > LIMIT:
            raise InvalidSpeech('speech worker request too large')
        self.process.stdin.write(data)
        await self.process.stdin.drain()

    async def exchange(self, request=None):
        if self.busy:
            raise SpeechUnavailable('speech worker is busy')
        self.busy = True
        try:
            async with asyncio.timeout(self.timeout):
                if self.process is None:
                    if not self.available():
                        raise SpeechUnavailable('install the optional speech environment')
                    # No runtime downloads, including optional Hugging Face models.
                    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                           'TOKENIZERS_PARALLELISM': 'false'}
                    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                        self.python, '-m', self.module, cwd=REPO, env=env,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL, limit=LIMIT))
                    try:
                        self.process = await asyncio.shield(spawn)
                    except asyncio.CancelledError:
                        self.process = await spawn
                        raise
                    await self.write(self.settings)
                    if await self.read() != {'ready': True}:
                        raise SpeechUnavailable('speech worker startup failed')
                if request is not None:
                    await self.write(request)
                    return await self.read()
        except BaseException:
            await self.aclose()
            raise
        finally:
            self.busy = False

    async def aclose(self):
        process, self.process = self.process, None
        if process is not None:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
            if process.stdin is not None:
                process.stdin.close()


def read_message(stream, limit=65536):
    line = stream.readline(limit + 1)
    if not line:
        return None
    if not line.endswith(b'\n') or len(line) > limit:
        raise ValueError('oversized worker request')
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError('invalid worker request')
    return value
