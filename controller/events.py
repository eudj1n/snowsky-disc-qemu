"""Reviewed DISC scan guards and partial playback-state reduction."""
from controller.catalog import CatalogChanged


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


def validate_scan_events(events):
    pending = iter(events)
    class Pending:
        def event(self, timeout):
            try:
                return next(pending)
            except StopIteration as exc:
                raise TimeoutError from exc
    check_events(Pending(), during_read=True)


def merge_snapshot(state, update):
    if not update:
        return state
    if isinstance(update.get('song'), dict) and update['song']:
        if update['song'] != state.get('song'):
            state = {}
    elif update.get('state') == 2:
        # Loading/EOF state cannot retain a previous song as current evidence.
        state = {}
    return {**state, **update}

