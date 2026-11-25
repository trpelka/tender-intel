"""pgserver returns different URI shapes on Windows and Linux."""
from urllib.parse import quote


def pg_uri(server) -> str:
    uri = server.get_uri()
    if "://" not in uri:
        return uri
    after = uri.split("://", 1)[1]
    authority, _, rest = after.partition("/")
    host = authority.rsplit("@", 1)[-1]
    if host.startswith("/"):
        # Some builds put the socket directory in the host component.
        socket_dir = host
    elif not host and rest:
        # Others put it at the start of the path (with or without a leading
        # slash after partition): /tmp/dir/postgres.
        socket_dir = "/" + rest.rsplit("/", 1)[0].lstrip("/")
    else:
        return uri
    return ("postgresql+pg8000://postgres@/postgres?unix_sock="
            + quote(f"{socket_dir}/.s.PGSQL.5432", safe="/"))
