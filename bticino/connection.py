"""
Async TCP connection for BTicino XOpen v3 protocol.

Maintains a persistent connection with:
- Continuous reader loop that dispatches EVT (push) and RSP (response) messages
- Keep-alive task every 10 seconds (2 failures = disconnect)
- Automatic reconnection with exponential backoff
- Future-based send_command() for request/response pairing
"""
import asyncio
import logging
import re
import uuid
from typing import Callable, Optional

from . import crypto
from . import protocol
from .models import ParsedMessage

logger = logging.getLogger(__name__)

# Regex to extract complete XML messages from the buffer
_MSG_V3_PATTERN = re.compile(r'(<OWNMsg[^>]*>.*?</OWNMsg>)', re.DOTALL)
_MSG_V1_PATTERN = re.compile(
    r'(<\?xml[^?]*\?>\s*)?(<OWNxml[^>]*>.*?</OWNxml>)', re.DOTALL)

# OpenWebNet text ACK
OWN_ACK = "*#*1##"

DEFAULT_PORT = 40000
CONNECT_TIMEOUT = 6.0
AUTH_TIMEOUT = 10.0
RECV_BUFFER = 10000
KEEPALIVE_INTERVAL = 10.0
KEEPALIVE_MAX_FAILURES = 2
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0
COMMAND_TIMEOUT = 10.0


class ConnectionError(Exception):
    pass


class AuthenticationError(ConnectionError):
    pass


class XOpenConnection:
    """Async TCP connection to a BTicino thermostat using XOpen v3 protocol."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, password: str = ""):
        self.host = host
        self.port = port
        self.password = password

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._buffer = ""
        self._authenticated = False

        # Internal tasks
        self._reader_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None

        # Pending command futures: seq_id -> Future[ParsedMessage]
        self._pending: dict[str, asyncio.Future] = {}

        # Callbacks
        self._event_callbacks: list[Callable[[ParsedMessage], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        self._connect_callbacks: list[Callable[[], None]] = []

        # Auth state
        self._ra_decimal = ""
        self._rb_decimal = ""

        # Reconnection
        self._auto_reconnect = True
        self._reconnecting = False
        self._closing = False

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def on_event(self, callback: Callable[[ParsedMessage], None]) -> None:
        """Register callback for EVT (push) messages from the thermostat."""
        self._event_callbacks.append(callback)

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register callback for disconnection events."""
        self._disconnect_callbacks.append(callback)

    def on_connect(self, callback: Callable[[], None]) -> None:
        """Register callback for successful connection events."""
        self._connect_callbacks.append(callback)

    async def connect(self) -> None:
        """Open TCP connection, authenticate, and start background tasks."""
        self._closing = False
        await self._do_connect()
        # Start background tasks
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        for cb in self._connect_callbacks:
            try:
                cb()
            except Exception:
                logger.exception("Error in connect callback")

    async def _do_connect(self) -> None:
        """TCP connect + authenticate (no background tasks)."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=CONNECT_TIMEOUT,
            )
            logger.info("Connected to %s:%d", self.host, self.port)
        except (OSError, asyncio.TimeoutError) as e:
            raise ConnectionError(
                f"Failed to connect to {self.host}:{self.port}: {e}")

        self._buffer = ""
        self._authenticated = False
        await self._authenticate()

    async def disconnect(self) -> None:
        """Close connection and stop background tasks."""
        self._closing = True
        self._auto_reconnect = False
        await self._close()

    async def _close(self) -> None:
        """Close the TCP connection and cancel tasks."""
        # Cancel tasks
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Close socket
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._writer = None
            self._reader = None

        # Fail all pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Connection closed"))
        self._pending.clear()

        self._authenticated = False
        self._buffer = ""
        logger.info("Connection closed")

    async def send_command(self, xml: str,
                           timeout: float = COMMAND_TIMEOUT) -> ParsedMessage:
        """Send an XML command and wait for the matching response.

        Creates a Future keyed by a unique SeqID. The reader loop
        completes the Future when a RSP with the same SeqID arrives.
        """
        if not self.connected or not self._authenticated:
            raise ConnectionError("Not connected/authenticated")

        # Generate a unique seq_id and inject it into the XML
        seq_id = str(uuid.uuid4())
        xml = _inject_seq_id(xml, seq_id)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ParsedMessage] = loop.create_future()
        self._pending[seq_id] = future

        try:
            await self._write(xml)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionError(f"Command timeout ({timeout}s)")
        finally:
            self._pending.pop(seq_id, None)

    async def _write(self, data: str) -> None:
        """Send a string over the TCP connection."""
        if not self._writer or self._writer.is_closing():
            raise ConnectionError("Not connected")
        raw = data.encode('utf-8')
        self._writer.write(raw)
        await self._writer.drain()
        logger.debug("TX: %s", data[:500])

    # --- Authentication ---

    async def _read_until(self, marker: str, timeout: float) -> str:
        """Read from socket until marker is found in buffer."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            if marker in self._buffer:
                idx = self._buffer.index(marker) + len(marker)
                result = self._buffer[:idx]
                self._buffer = self._buffer[idx:]
                return result
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise ConnectionError(
                    f"Timeout waiting for {marker!r} "
                    f"(buffer: {self._buffer[:200]!r})")
            try:
                data = await asyncio.wait_for(
                    self._reader.read(RECV_BUFFER),
                    timeout=min(remaining, 2.0),
                )
            except asyncio.TimeoutError:
                continue
            if not data:
                raise ConnectionError("Connection closed by remote")
            self._buffer += data.decode('utf-8', errors='replace')

    async def _read_message(self, timeout: float = AUTH_TIMEOUT) -> Optional[ParsedMessage]:
        """Read a single XML message from the buffer/socket (used during auth)."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            xml_str = self._extract_message()
            if xml_str:
                logger.debug("RX MSG: %s", xml_str[:500])
                return protocol.parse_message(xml_str)
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return None
            try:
                data = await asyncio.wait_for(
                    self._reader.read(RECV_BUFFER),
                    timeout=min(remaining, 2.0),
                )
            except asyncio.TimeoutError:
                continue
            if not data:
                raise ConnectionError("Connection closed by remote")
            self._buffer += data.decode('utf-8', errors='replace')

    def _extract_message(self) -> Optional[str]:
        """Try to extract a complete XML message from the buffer."""
        match = _MSG_V3_PATTERN.search(self._buffer)
        if match:
            xml_str = match.group(1)
            self._buffer = self._buffer[match.end():]
            return xml_str
        match = _MSG_V1_PATTERN.search(self._buffer)
        if match:
            xml_str = match.group(0)
            self._buffer = self._buffer[match.end():]
            return xml_str
        return None

    async def _authenticate(self) -> None:
        """Perform the full HMAC handshake."""
        logger.info("Starting authentication...")

        # Step 1: Wait for *#*1## OWN ACK
        await self._read_until(OWN_ACK, timeout=AUTH_TIMEOUT)
        logger.info("Received OWN ACK")

        # Step 2: Send OWNSetProtocol V3 negotiate
        negotiate = protocol.build_negotiate_v3()
        await self._write(negotiate)
        logger.info("Sent OWNSetProtocol V3 negotiate")

        # Step 3: Read RandomStringHMAC
        msg = await self._read_message(timeout=AUTH_TIMEOUT)
        if msg is None:
            raise AuthenticationError("No response after OWNSetProtocol")

        if msg.action_id != "RandomStringHMAC":
            raise AuthenticationError(
                f"Expected RandomStringHMAC, got: {msg.action_id}")

        # Step 4: Extract server's Ra
        ra_decimal = msg.params.get("Random", "")
        if not ra_decimal:
            raise AuthenticationError("RandomStringHMAC missing Random param")
        self._ra_decimal = ra_decimal
        sid = msg.seq_id
        pid = int(msg.progress) if msg.progress else 0
        logger.info("Received Ra challenge (%d chars)", len(ra_decimal))

        # Step 5: Compute client HMAC response
        rb_decimal, digest = crypto.make_hmac(self.password, ra_decimal)
        self._rb_decimal = rb_decimal

        # Step 6: Send ClientHandshakeHMAC (PID incremented)
        client_msg = protocol.build_client_handshake(
            sid, pid + 1, rb_decimal, digest)
        await self._write(client_msg)
        logger.info("Sent ClientHandshakeHMAC")

        # Step 7: Receive ServerHandshakeHMAC
        server_msg = await self._read_message(timeout=AUTH_TIMEOUT)
        if server_msg is None:
            raise AuthenticationError("No ServerHandshakeHMAC received")

        if server_msg.action_id == "NackMsg":
            raise AuthenticationError(
                "Authentication rejected (NackMsg) - wrong password?")

        if server_msg.action_id != "ServerHandshakeHMAC":
            raise AuthenticationError(
                f"Expected ServerHandshakeHMAC, got: {server_msg.action_id}")

        # Step 8: Verify server digest
        server_digest = server_msg.params.get("Digest", "")
        if not crypto.verify_hmac(self.password, self._ra_decimal,
                                  self._rb_decimal, server_digest):
            raise AuthenticationError("Server HMAC verification failed")
        logger.info("Server HMAC verified OK")

        # Step 9: Send AckMsg
        ack = protocol.build_ack(sid, pid)
        await self._write(ack)
        self._authenticated = True
        logger.info("Authentication successful")

    # --- Background tasks ---

    async def _reader_loop(self) -> None:
        """Continuous reader: read from socket, dispatch EVT and RSP messages."""
        try:
            while True:
                # Extract any buffered messages first
                while True:
                    xml_str = self._extract_message()
                    if not xml_str:
                        break
                    self._dispatch(protocol.parse_message(xml_str))

                # Read more data
                try:
                    data = await self._reader.read(RECV_BUFFER)
                except (OSError, ConnectionResetError):
                    data = b""
                if not data:
                    logger.warning("Reader: connection closed by remote")
                    break
                self._buffer += data.decode('utf-8', errors='replace')
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reader loop error")
        finally:
            if not self._closing:
                await self._handle_disconnect()

    def _dispatch(self, msg: ParsedMessage) -> None:
        """Route a parsed message to the right handler."""
        logger.debug("DISPATCH: type=%s action=%s seq=%s",
                     msg.service_type, msg.action_id, msg.seq_id)

        # RSP messages: complete pending futures
        if msg.service_type == "RSP":
            # Try exact SeqID match first
            if msg.seq_id and msg.seq_id in self._pending:
                fut = self._pending.pop(msg.seq_id)
                if not fut.done():
                    fut.set_result(msg)
                return
            # Fallback: thermostat sometimes replies without SeqID
            # (e.g. NackMsg/AckMsg to SET commands). Complete the oldest
            # pending future if there is exactly one.
            if not msg.seq_id and self._pending:
                seq_id, fut = next(iter(self._pending.items()))
                self._pending.pop(seq_id)
                if not fut.done():
                    fut.set_result(msg)
                return

        # EVT messages (or unsolicited RSP): notify event callbacks
        if msg.service_type == "EVT":
            for cb in self._event_callbacks:
                try:
                    cb(msg)
                except Exception:
                    logger.exception("Error in event callback")

    async def _keepalive_loop(self) -> None:
        """Send keep-alive every KEEPALIVE_INTERVAL seconds."""
        failures = 0
        try:
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if not self.connected or not self._authenticated:
                    continue
                try:
                    resp = await self.send_command(
                        protocol.build_keep_alive(), timeout=5.0)
                    if resp.action_id == "NackMsg":
                        failures += 1
                        logger.warning("Keep-alive NACK (%d/%d)",
                                       failures, KEEPALIVE_MAX_FAILURES)
                    else:
                        failures = 0
                        logger.debug("Keep-alive OK")
                except Exception:
                    failures += 1
                    logger.warning("Keep-alive failed (%d/%d)",
                                   failures, KEEPALIVE_MAX_FAILURES)

                if failures >= KEEPALIVE_MAX_FAILURES:
                    logger.error("Keep-alive: %d failures, disconnecting",
                                 failures)
                    break
        except asyncio.CancelledError:
            raise
        finally:
            if not self._closing:
                await self._handle_disconnect()

    async def _handle_disconnect(self) -> None:
        """Handle unexpected disconnection: notify callbacks, attempt reconnect."""
        self._authenticated = False

        # Fail pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Disconnected"))
        self._pending.clear()

        # Notify
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception:
                logger.exception("Error in disconnect callback")

        # Reconnect
        if self._auto_reconnect and not self._closing and not self._reconnecting:
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt reconnection with exponential backoff."""
        self._reconnecting = True
        delay = RECONNECT_BASE_DELAY
        try:
            while self._auto_reconnect and not self._closing:
                logger.info("Reconnecting in %.1fs...", delay)
                await asyncio.sleep(delay)
                try:
                    # Close existing resources
                    if self._writer:
                        try:
                            self._writer.close()
                            await self._writer.wait_closed()
                        except OSError:
                            pass
                        self._writer = None
                        self._reader = None
                    self._buffer = ""

                    await self._do_connect()

                    # Restart background tasks
                    self._reader_task = asyncio.create_task(self._reader_loop())
                    self._keepalive_task = asyncio.create_task(
                        self._keepalive_loop())

                    logger.info("Reconnected successfully")
                    for cb in self._connect_callbacks:
                        try:
                            cb()
                        except Exception:
                            logger.exception("Error in connect callback")
                    return
                except Exception as e:
                    logger.warning("Reconnection failed: %s", e)
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
        finally:
            self._reconnecting = False


def _inject_seq_id(xml: str, seq_id: str) -> str:
    """Replace the SeqID ID attribute in an XML message with a new value."""
    return re.sub(
        r'SeqID ID="[^"]*"',
        f'SeqID ID="{seq_id}"',
        xml,
        count=1,
    )
