def format_url(package):
    url = package["url"]
    for h in ["sha256", "md5"]:
        if h in package:
            url += f"#{h}={package[h]}"
    return url
