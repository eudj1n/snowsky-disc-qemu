"""Short, sequential catalog sessions, not a persistent playback event service."""
from controller.fiio_http import HTTPClient
from controller.fiio_link import Client
from research.disc_assistant.library.catalog import CatalogReader, CatalogChanged


def check_events(client, *, during_read=False):
    # a60a is a general status tag: 0010 also arrives during initialization and
    # 000D appears in playback traces. Only the verified scan values qualify.
    # No queries here: request() discards unrelated events.
    for _ in range(10000):
        try:
            tag, payload = client.event(timeout=0.01)
        except TimeoutError:
            return
        if tag not in ('a60a', 'a622'):
            continue
        if (not payload or any(byte not in b'0123456789abcdefABCDEF' for byte in payload)
                or (tag == 'a60a' and len(payload) != 4)):
            raise CatalogChanged(f'invalid {tag} status notification; snapshot retained')
        value = int(payload, 16)
        if tag == 'a622' or value == 15:
            event = 'a622/count' if tag == 'a622' else 'a60a/000F'
            raise CatalogChanged(f'observed library scan activity ({event}); sync after it finishes')
        if value == 5 and during_read:
            # A scan may have started before this connection. Finish during the
            # read invalidates it too; finish before the read permits a fresh one.
            raise CatalogChanged('library scan ended during catalog read (a60a/0005); retry sync')
    raise CatalogChanged('device event budget exhausted')


def sync(config, store):
    expected = store.head(config.device_key)['generation']
    with Client(config.host, config.tcp_port, config.timeout) as client:
        handshake = client.handshake()
        settings = client.settings()
        version = settings.get('soc_version')
        if handshake != '0306' or type(version) is not int or version != 257:
            raise ValueError('prototype catalog contract requires reviewed DISC V2.57')
        http = HTTPClient(config.host, config.http_port, config.timeout)
        reader = CatalogReader(http, page_size=config.page_size, max_tracks=config.max_tracks,
                               max_requests=config.max_requests)
        check_events(client)
        tracks = reader.read_stable()
        check_events(client, during_read=True)
    return store.publish(config.device_key, tracks, {
        'soc_version': version, 'host': config.host, 'tcp_port': config.tcp_port,
        'http_port': config.http_port, 'consistency': 'two-equal-reads-not-atomic',
        'identity': 'snapshot-only'}, expected_generation=expected)
