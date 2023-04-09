REPO_BASE = "https://anaconda.org"


def format_url(package):
    url = package["url"]
    for h in ["sha256", "md5"]:
        if h in package:
            url += f"#{h}={package[h]}"
    return url


def generate_package_info(
    name: str,
    version: str,
    depends: list | None = None,
    build_number: int = 0,
    timestamp: int = 0,
) -> dict:
    channel = f"{REPO_BASE}/channel"
    build_string = f"{name}_{build_number}"
    return {
        "name": name,
        "depends": depends or [],
        "version": version,
        "build_number": build_number,
        "url": f"{channel}/{name}",
        "channel": channel,
        "sha256": f"{name}-hash",
        "build": build_string,
        "build_string": build_string,
        "timestamp": timestamp,
    }
