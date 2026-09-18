"""Assistant configuration/ownership adapter for the shared Controller session."""
from controller.models import DeviceConfig
from controller.session import DiscSession, LiveClient, LiveSocket
from research.disc_assistant.assistant.device import device_lock


class DeviceSession(DiscSession):
    def __init__(self, config, **kwargs):
        endpoint = DeviceConfig(config.host, config.tcp_port, config.http_port, config.timeout,
                                config.page_size, config.max_tracks, config.max_requests)
        super().__init__(endpoint, ownership=device_lock(config.data_dir), **kwargs)
