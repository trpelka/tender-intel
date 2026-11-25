"""pgserver uses a TCP URI on Windows and a unix socket URI on Linux."""
from urllib.parse import quote


def pg_uri(server) -> str:
    uri = server.get_uri()
    info = server.get_postmaster_info()
    getter = getattr(info, "socket_path", None)
    socket_path = getter() if callable(getter) else None
    if socket_path:
        return ("postgresql+pg8000://postgres@/postgres?unix_sock="
                + quote(str(socket_path), safe="/"))
    return uri
