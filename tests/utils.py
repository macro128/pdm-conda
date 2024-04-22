REPO_BASE = "https://anaconda.org"
DEFAULT_CHANNEL = "channel"
PLATFORM = "platform"


def channel_url(channel: str) -> str:
    return f"{REPO_BASE}/{channel}"


def format_url(package):
    url = package["url"]
    for h in ["md5"]:
        if h in package:
            url += f"#{package[h]}"
    return url


def generate_package_info(
    name: str,
    version: str,
    depends: list | None = None,
    constrains: list | None = None,
    build_number: int = 0,
    timestamp: int = 0,
    channel: str = f"{DEFAULT_CHANNEL}/{PLATFORM}",
    python_only: bool = False,
) -> dict:
    channel = channel_url(channel)
    build_string = f"{name}_{build_number}"
    return {
        "name": name,
        "depends": depends or [],
        "constrains": constrains or [],
        "version": version,
        "build_number": build_number,
        "url": f"{channel}/{name}",
        "channel": channel,
        "md5": f"{name}-hash",
        "build": build_string,
        "build_string": build_string,
        "timestamp": timestamp,
        "python_only": python_only,
    }
