"""Run the FastAPI app with SO_REUSEADDR so we can rebind to a port
that's still in the OS TCP table even when the previous uvicorn
process is gone. Use this on Windows where TCP table cleanup lags.
"""
import socket

import uvicorn

if __name__ == "__main__":
    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
    # Inject SO_REUSEADDR on the listening socket. On Windows, the
    # TCP table sometimes holds the port in TIME_WAIT/LISTEN for
    # zombie sockets that no longer correspond to a real process.
    config.load()  # ensures server is initialised

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((config.host, config.port))

    server = uvicorn.Server(config)
    server.run(sockets=[sock])
