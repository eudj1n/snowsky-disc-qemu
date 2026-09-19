"""Disposable native Docker checks; no player, personal catalog or persistent volume."""
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request


def check(image, *, missing):
    name = 'disc-io-check-' + secrets.token_hex(6)
    key = secrets.token_hex(16)
    arguments = ['docker', 'run', '-d', '--name', name, '--cap-drop=ALL',
                 '--security-opt=no-new-privileges:true', '--tmpfs', '/data',
                 '-p', '127.0.0.1::8108', '-e', 'TYPESENSE_DATA_DIR=/data',
                 '-e', f'TYPESENSE_API_KEY={key}']
    if missing:
        arguments += ['-e', 'TEST_PROC_IO=missing', '-e',
                      'LD_PRELOAD=/opt/disc/proc-io-compat.so:/opt/disc/fixture.so']
    try:
        subprocess.run([*arguments, image], check=True, capture_output=True)
        endpoint = subprocess.check_output(['docker', 'port', name, '8108/tcp'], text=True).strip()

        def request(path, payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            query = urllib.request.Request('http://' + endpoint + path, data=data,
                                           headers={'X-TYPESENSE-API-KEY': key, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(query, timeout=2) as response:
                return json.load(response)

        deadline = time.monotonic() + 45
        while True:
            try:
                if request('/health').get('ok') is True:
                    break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('disposable Typesense did not become healthy')
            time.sleep(.25)
        request('/collections', {'name': 'fixture', 'fields': [{'name': 'title', 'type': 'string'}]})
        request('/collections/fixture/documents', {'id': '1', 'title': 'Synthetic Song'})
        result = request('/collections/fixture/documents/search?q=Synthetic&query_by=title')
        assert result['found'] == 1 and result['hits'][0]['document']['id'] == '1', result
        print(f'{image}: health, index and search passed (missing proc I/O: {missing})')
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    check('disc-assistant-typesense:30.2-io-v1', missing=False)
    check('disc-assistant-typesense:io-verification', missing=True)
