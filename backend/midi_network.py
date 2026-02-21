"""Network MIDI (rtpMIDI) handler for MIDI over IP support."""
import asyncio
import threading
import time
from typing import Callable, Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

try:
    from pymidi import server as pymidi_server
    PYMIDI_AVAILABLE = True
except ImportError:
    PYMIDI_AVAILABLE = False
    pymidi_server = None


class NetworkMIDIHandler:
    """Handles rtpMIDI/Network MIDI connections.

    Allows DMXX to:
    1. Run as an rtpMIDI server (other devices connect to DMXX)
    2. Receive MIDI messages over the network
    3. Send MIDI messages back to connected peers
    """

    def __init__(self, on_message_callback: Optional[Callable] = None):
        """
        Initialize Network MIDI handler.

        Args:
            on_message_callback: Callback for incoming MIDI messages.
                                 Signature: callback(msg_type: str, data: dict)
        """
        self._callback = on_message_callback
        self._server = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._port = 5004
        self._name = "DMXX"
        self._peers: Dict[str, Any] = {}  # {peer_name: peer_object}
        self._messages_received = 0
        self._messages_sent = 0

    @staticmethod
    def is_available() -> bool:
        """Check if network MIDI support is available."""
        return PYMIDI_AVAILABLE

    def _create_handler(self):
        """Create a pymidi handler class with callbacks to this instance."""
        parent = self

        class DMXXMIDIHandler(pymidi_server.Handler):
            def on_peer_connected(self, peer):
                peer_name = getattr(peer, 'name', str(peer))
                logger.info(f"Network MIDI peer connected: {peer_name}")
                parent._peers[peer_name] = peer

            def on_peer_disconnected(self, peer):
                peer_name = getattr(peer, 'name', str(peer))
                logger.info(f"Network MIDI peer disconnected: {peer_name}")
                parent._peers.pop(peer_name, None)

            def on_midi_commands(self, peer, command_list):
                for command in command_list:
                    parent._handle_command(peer, command)

        return DMXXMIDIHandler()

    def _handle_command(self, peer, command):
        """Process an incoming MIDI command from pymidi."""
        self._messages_received += 1

        cmd_type = command.command
        params = command.params
        peer_name = getattr(peer, 'name', str(peer))

        # Convert pymidi command format to our standard format
        msg_data = {
            "type": cmd_type,
            "time": time.time(),
            "peer": peer_name,
            "device_name": f"network:{peer_name}"  # Prefix to distinguish from USB
        }

        if cmd_type == "note_on":
            msg_data["channel"] = params.get("channel", 0)
            msg_data["note"] = params.get("key", 0)
            msg_data["velocity"] = params.get("velocity", 0)
        elif cmd_type == "note_off":
            msg_data["channel"] = params.get("channel", 0)
            msg_data["note"] = params.get("key", 0)
            msg_data["velocity"] = 0
        elif cmd_type == "control_change":
            msg_data["channel"] = params.get("channel", 0)
            msg_data["control"] = params.get("control", 0)
            msg_data["value"] = params.get("value", 0)
        elif cmd_type == "program_change":
            msg_data["channel"] = params.get("channel", 0)
            msg_data["program"] = params.get("program", 0)
        elif cmd_type == "pitchwheel":
            msg_data["channel"] = params.get("channel", 0)
            msg_data["pitch"] = params.get("pitch", 0)

        # Call the message callback
        if self._callback:
            try:
                self._callback(cmd_type, msg_data)
            except Exception as e:
                logger.error(f"Network MIDI callback error: {e}")

    async def start_server(self, port: int = 5004, name: str = "DMXX") -> bool:
        """
        Start rtpMIDI server to accept incoming connections.

        Args:
            port: Port to listen on (default 5004, standard rtpMIDI port)
            name: Service name visible to other devices

        Returns:
            True if server started successfully.
        """
        if not PYMIDI_AVAILABLE:
            logger.error("pymidi not available - install with: pip install pymidi")
            return False

        if self._running:
            await self.stop_server()

        try:
            self._port = port
            self._name = name
            self._running = True

            # Create server in background thread (pymidi uses blocking serve_forever)
            self._server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self._server_thread.start()

            # Give server time to start
            await asyncio.sleep(0.5)

            logger.info(f"Network MIDI server started on port {port} as '{name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to start Network MIDI server: {e}")
            self._running = False
            return False

    def _run_server(self):
        """Background thread: Run the pymidi server."""
        try:
            self._server = pymidi_server.Server([('0.0.0.0', self._port)])
            self._server.add_handler(self._create_handler())

            # serve_forever blocks, so we need to handle shutdown
            while self._running:
                # Process connections with timeout so we can check _running
                try:
                    self._server._poll(timeout=0.1)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Network MIDI server error: {e}")
        finally:
            self._running = False

    async def stop_server(self) -> None:
        """Stop the rtpMIDI server."""
        self._running = False

        if self._server_thread:
            self._server_thread.join(timeout=2.0)
            self._server_thread = None

        self._server = None
        self._peers.clear()
        logger.info("Network MIDI server stopped")

    def get_connected_peers(self) -> List[Dict[str, Any]]:
        """Get list of connected peers."""
        peers = []
        for name, peer in self._peers.items():
            peers.append({
                "name": name,
                "address": getattr(peer, 'addr', 'unknown')
            })
        return peers

    def get_status(self) -> Dict[str, Any]:
        """Get current network MIDI status."""
        return {
            "available": PYMIDI_AVAILABLE,
            "server_running": self._running,
            "port": self._port if self._running else None,
            "name": self._name if self._running else None,
            "peers": self.get_connected_peers(),
            "peer_count": len(self._peers),
            "messages_received": self._messages_received,
            "messages_sent": self._messages_sent
        }

    def send_to_all(self, midi_bytes: bytes) -> int:
        """
        Send raw MIDI bytes to all connected peers.

        Args:
            midi_bytes: Raw MIDI message bytes

        Returns:
            Number of peers the message was sent to.
        """
        if not self._running or not self._peers:
            return 0

        sent = 0
        for peer in self._peers.values():
            try:
                # pymidi peer.send() method if available
                if hasattr(peer, 'send'):
                    peer.send(midi_bytes)
                    sent += 1
                    self._messages_sent += 1
            except Exception as e:
                logger.error(f"Failed to send to peer: {e}")

        return sent


# Helper to create MIDI message bytes
def make_cc_bytes(channel: int, control: int, value: int) -> bytes:
    """Create Control Change MIDI bytes."""
    status = 0xB0 | (channel & 0x0F)
    return bytes([status, control & 0x7F, value & 0x7F])


def make_note_on_bytes(channel: int, note: int, velocity: int) -> bytes:
    """Create Note On MIDI bytes."""
    status = 0x90 | (channel & 0x0F)
    return bytes([status, note & 0x7F, velocity & 0x7F])


def make_note_off_bytes(channel: int, note: int) -> bytes:
    """Create Note Off MIDI bytes."""
    status = 0x80 | (channel & 0x0F)
    return bytes([status, note & 0x7F, 0])
