"""Bounded subprocess and model-file utilities shared by speech adapters."""
import asyncio
from functools import lru_cache
import hashlib
from experiments.disc_assistant.assistant.speech import SpeechUnavailable


async def run_process(arguments, *, timeout):
    """Bound execution and reap cancelled/timed-out children before temp cleanup."""
    try:
        process = await asyncio.create_subprocess_exec(
            *arguments, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except OSError as exc:
        raise SpeechUnavailable('speech executable could not be started; check speech configuration') from exc
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except BaseException as exc:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
        if isinstance(exc, TimeoutError):
            raise SpeechUnavailable('speech processing timed out') from exc
        raise
    if process.returncode:
        raise SpeechUnavailable('speech executable failed; check installed models, voices and configuration')


@lru_cache(maxsize=8)
def model_digest(path, size, modified_ns):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
