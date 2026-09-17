"""Selected build and reviewed acceptance fixtures; no implicit version fallback."""
import os
from firmware.profile import selected_version, selected_profile, require_scenario, value, supports


def version():
    return selected_version()


def profile():
    return selected_profile()


def main_os_version():
    return profile()['main_os_version']


def capability(feature):
    return supports(profile(), feature)


def require_acceptance(scenario):
    if os.environ.get('CI_DISPOSABLE') != '1' or not os.environ.get('FW_VERSION'):
        raise RuntimeError('Requires an explicitly selected disposable firmware stack')
    try:
        require_scenario(profile(), scenario)
    except ValueError as error:
        raise RuntimeError(str(error)) from error


def diagnostic(key):
    return value(profile(), 'diagnostics.' + key)
