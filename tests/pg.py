"""pgserver uses a TCP URI on Windows and a unix socket URI on Linux."""
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


def pg_uri(server) -> str:
    uri = server.get_uri()
    info = server.get_postmaster_info()
    candidate = getattr(info, "socket_path", None)
    if callable(candidate):
        candidate = candidate()
    socket_path = Path(candidate) if candidate else None
    if socket_path is None:
        socket_dir = parse_qs(urlparse(uri).query).get("host", [None])[0]
        if socket_dir:
            port = getattr(info, "port", None) or 5432
            socket_path = Path(socket_dir) / f".s.PGSQL.{port}"
    if socket_path is None:
        return uri
    return ("postgresql+pg8000://postgres@/postgres?unix_sock="
            + quote(str(socket_path), safe="/"))
