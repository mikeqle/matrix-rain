"""IPC via Unix datagram socket for receiving messages from external processes."""

import os
import socket
import stat


def default_socket_path() -> str:
    """Return the default socket path: /tmp/matrix-rain-{uid}.sock"""
    return f"/tmp/matrix-rain-{os.getuid()}.sock"


class MessageListener:
    """Non-blocking Unix datagram socket listener for incoming text messages."""

    def __init__(self, socket_path: str | None = None):
        self.socket_path = socket_path or default_socket_path()
        self._sock: socket.socket | None = None
        self._bind()

    def _bind(self):
        # Clean up stale socket from a previous crash
        if os.path.exists(self.socket_path):
            mode = os.stat(self.socket_path).st_mode
            if not stat.S_ISSOCK(mode):
                raise OSError(
                    f"Path exists and is not a socket: {self.socket_path}"
                )
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                probe.sendto(b"", self.socket_path)
            except (ConnectionRefusedError, OSError):
                # Can't connect — socket is stale, safe to replace
                try:
                    os.unlink(self.socket_path)
                except FileNotFoundError:
                    pass
            else:
                # sendto succeeded — another instance is actively listening
                probe.close()
                raise OSError(
                    f"Another matrix-rain instance is listening at {self.socket_path}"
                )
            finally:
                probe.close()

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._sock.bind(self.socket_path)

    def poll(self) -> str | None:
        """Non-blocking check for an incoming message. Returns the message
        string or None if nothing is waiting."""
        if self._sock is None:
            return None
        try:
            data, _ = self._sock.recvfrom(4096)
            text = data.decode("utf-8", errors="replace").strip()
            return text if text else None
        except BlockingIOError:
            return None

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def send_message(message: str, socket_path: str | None = None) -> None:
    """Send a single message to a running matrix-rain instance."""
    path = socket_path or default_socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(message.encode("utf-8"), path)
    finally:
        sock.close()
