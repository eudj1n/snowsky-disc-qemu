"""Explicit loopback endpoints for optional local inference services."""
from urllib.parse import urlsplit


def endpoint(value, path):
    if not isinstance(value, str):
        raise ValueError('local service endpoint must be a URL')
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1')
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path != path or parsed.port is None):
        raise ValueError('use an explicit HTTP loopback endpoint with a port and the documented path')
    return value


async def bounded_body(response, limit):
    chunks, size = [], 0
    async for chunk in response.content.iter_chunked(16384):
        size += len(chunk)
        if size > limit:
            raise ValueError('local service response exceeds its size limit')
        chunks.append(chunk)
    return b''.join(chunks)
