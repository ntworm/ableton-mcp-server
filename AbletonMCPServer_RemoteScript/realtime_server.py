"""A UDP channel for control moves that cannot wait for the JSONL request loop.

Live's API is only safe to touch from its own thread, so nothing here writes to
Live. Packets are validated, deduplicated and appended to a queue that the
control surface drains inside ``update_display``.

The channel is closed until something arms it. An unarmed server drops every
packet, which is what makes an open UDP port on loopback acceptable: a token has
to be handed out over the authenticated JSONL connection first, and only the
parameter references named at arming time can be moved.
"""

import json
import logging
import socket
import threading

# Live calls update_display at roughly 10 Hz. A controller sending faster than
# that would otherwise grow the queue without bound between drains, so the
# oldest moves are dropped: for a live control surface the newest value is the
# only one that matters.
MAX_QUEUED_COMMANDS = 256

_RECV_TIMEOUT_SECONDS = 0.5
_MAX_PACKET_BYTES = 512


class RealtimeUDPServer(threading.Thread):
    def __init__(self, port, callback_queue):
        super().__init__()
        # Live may tear the script down without calling disconnect. A non-daemon
        # thread would keep the process alive waiting on a socket nobody reads.
        self.daemon = True
        self.port = port
        self.callback_queue = callback_queue
        self.sock = None
        self._stop_event = threading.Event()
        self.armed_token = None
        self.armed_refs = []
        self.last_seq = -1

    def arm(self, token, refs):
        self.armed_token = token
        self.armed_refs = refs
        self.last_seq = -1

    def disarm(self):
        self.armed_token = None
        self.armed_refs = []
        self.last_seq = -1

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Reloading the Remote Script rebinds this port within seconds of
            # the previous socket closing. Without this the new instance fails
            # to bind and realtime is silently dead until Live restarts.
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("127.0.0.1", self.port))
            self.sock.settimeout(_RECV_TIMEOUT_SECONDS)
        except OSError as error:
            logging.error("Failed to bind realtime UDP server: %s", error)
            return

        try:
            while not self._stop_event.is_set():
                try:
                    data, _addr = self.sock.recvfrom(_MAX_PACKET_BYTES)
                except TimeoutError:
                    continue
                except OSError as error:
                    logging.error("Realtime receive failed: %s", error)
                    continue
                try:
                    self._handle_packet(data)
                except Exception as error:  # noqa: BLE001 - one bad packet must not kill the loop
                    logging.error("Realtime packet rejected: %s", error)
        finally:
            self.sock.close()
            self.sock = None

    def _enqueue(self, command):
        if len(self.callback_queue) >= MAX_QUEUED_COMMANDS:
            del self.callback_queue[0]
        self.callback_queue.append(command)

    def _handle_packet(self, data):
        if not self.armed_token:
            return

        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return
        if not isinstance(payload, dict):
            return

        if payload.get("token") != self.armed_token:
            return

        # UDP reorders and duplicates. A move older than the last one applied is
        # not a correction, it is a stale packet arriving late.
        seq = payload.get("seq", -1)
        if not isinstance(seq, int) or seq <= self.last_seq:
            return
        self.last_seq = seq

        op = payload.get("op")
        if op == "parameter.set":
            ref = payload.get("ref")
            if ref in self.armed_refs:
                self._enqueue(("parameter.set", ref, payload.get("value")))

        elif op == "xy.set":
            x_ref = payload.get("xRef")
            y_ref = payload.get("yRef")
            # Both or neither: half an XY move puts the pad somewhere the
            # performer never pointed at.
            if x_ref in self.armed_refs and y_ref in self.armed_refs:
                self._enqueue(("parameter.set", x_ref, payload.get("x")))
                self._enqueue(("parameter.set", y_ref, payload.get("y")))

        elif op == "emergency-stop":
            self._enqueue(("emergency-stop",))

    def stop(self, timeout=2.0):
        """Signal the loop and wait for the socket to actually close.

        Returning before the thread exits leaves the port bound, so the next
        instance cannot bind it. The loop wakes at most one receive timeout
        after the event is set.
        """

        self._stop_event.set()
        if self.is_alive():
            self.join(timeout)
