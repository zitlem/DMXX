"""
DMX Input Protocol Implementations.
Provides abstract base class and concrete implementations for Art-Net and sACN inputs.
These allow receiving DMX data from external sources to control DMXX.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable, Set
import asyncio
import socket
import struct
import logging

logger = logging.getLogger(__name__)


def _get_local_ips() -> Set[str]:
    """Get all local IP addresses for loopback detection."""
    ips = {'127.0.0.1', '::1'}
    try:
        hostname = socket.gethostname()
        # Get IPs from hostname resolution
        ips.update(socket.gethostbyname_ex(hostname)[2])
        # Also try to get IPs from all interfaces
        for info in socket.getaddrinfo(hostname, None):
            ips.add(info[4][0])
    except Exception:
        pass
    # Try to get the actual network interface IPs
    try:
        # Connect to external address to find our IP (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return ips


# Cache local IPs at module load time
LOCAL_IPS = _get_local_ips()
logger.info(f"Detected local IPs for loopback filtering: {LOCAL_IPS}")


class DMXInput(ABC):
    """Abstract base class for DMX input protocols."""

    def __init__(self, universe_id: int, config: dict, callback: Callable[[int, List[int]], None]):
        """
        Initialize DMX input.

        Args:
            universe_id: The DMXX universe this input is mapped to
            config: Protocol-specific configuration
            callback: Function called with (universe_id, channel_values) when data received
        """
        self.universe_id = universe_id
        self.config = config
        self.callback = callback
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @abstractmethod
    async def start(self) -> bool:
        """Initialize and start the input listener. Returns success status."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop and cleanup the input listener."""
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """Return status information about this input."""
        pass


class ArtNetProtocol(asyncio.DatagramProtocol):
    """Asyncio protocol for Art-Net UDP reception."""

    def __init__(self, input_handler: 'ArtNetInput'):
        self.input_handler = input_handler
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        source_ip = addr[0]

        # Ignore self (loopback prevention) - check if packet is from this machine
        if self.input_handler._ignore_self and source_ip in LOCAL_IPS:
            return

        # Blacklist check - ignore packets from specific IP
        if self.input_handler._ignore_ip_filter and source_ip == self.input_handler._ignore_ip_filter:
            return

        # Whitelist check - only accept from specific IP
        if self.input_handler._source_ip_filter and source_ip != self.input_handler._source_ip_filter:
            return

        self.input_handler._parse_artnet_packet(data)

    def error_received(self, exc):
        logger.error(f"Universe {self.input_handler.universe_id}: Art-Net protocol error: {exc}")

    def connection_lost(self, exc):
        pass


class ArtNetInput(DMXInput):
    """Art-Net protocol input listener."""

    # Art-Net packet header
    ARTNET_HEADER = b'Art-Net\x00'
    ARTNET_OPCODE_DMX = 0x5000

    def __init__(self, universe_id: int, config: dict, callback: Callable[[int, List[int]], None]):
        super().__init__(universe_id, config, callback)
        self._transport = None
        self._protocol = None
        self._packets_received = 0
        self._last_sequence = -1
        self._artnet_universe = 0
        self._source_ip_filter = ""
        self._ignore_ip_filter = ""
        self._ignore_self = False

    async def start(self) -> bool:
        try:
            bind_ip = self.config.get("bind_ip", "0.0.0.0")
            port = self.config.get("port", 6454)
            self._artnet_universe = self.config.get("artnet_universe", self.universe_id - 1)
            self._source_ip_filter = self.config.get("source_ip", "").strip()
            self._ignore_ip_filter = self.config.get("ignore_ip", "").strip()
            self._ignore_self = self.config.get("ignore_self", False)

            loop = asyncio.get_event_loop()

            # Create socket manually for cross-platform compatibility
            # Windows doesn't support reuse_port parameter in create_datagram_endpoint
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # Windows doesn't have SO_REUSEPORT
            sock.bind((bind_ip, port))
            sock.setblocking(False)

            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: ArtNetProtocol(self),
                sock=sock
            )

            self._running = True
            filter_parts = []
            if self._source_ip_filter:
                filter_parts.append(f"accept from: {self._source_ip_filter}")
            if self._ignore_ip_filter:
                filter_parts.append(f"ignore: {self._ignore_ip_filter}")
            if self._ignore_self:
                filter_parts.append("ignore self")
            filter_info = f", {', '.join(filter_parts)}" if filter_parts else ""
            logger.info(f"Universe {self.universe_id}: Art-Net input started <- {bind_ip}:{port} (artnet universe {self._artnet_universe}{filter_info})")
            return True

        except OSError as e:
            logger.error(f"Universe {self.universe_id}: Failed to bind Art-Net input to {bind_ip}:{port} - {e}")
            return False
        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Failed to start Art-Net input: {e}")
            return False

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None

        logger.info(f"Universe {self.universe_id}: Art-Net input stopped (received {self._packets_received} packets)")

    def _parse_artnet_packet(self, data: bytes) -> None:
        """Parse Art-Net DMX packet and extract channel data."""
        if len(data) < 18:
            return

        # Check Art-Net header
        if data[:8] != self.ARTNET_HEADER:
            return

        # Get opcode (little-endian)
        opcode = struct.unpack('<H', data[8:10])[0]
        if opcode != self.ARTNET_OPCODE_DMX:
            return

        # Parse ArtDmx packet
        # Bytes 10-11: Protocol version (14)
        # Byte 12: Sequence
        # Byte 13: Physical
        # Bytes 14-15: Universe (little-endian, SubUni + Net)
        # Bytes 16-17: Length (big-endian)

        sequence = data[12]
        universe = struct.unpack('<H', data[14:16])[0]
        length = struct.unpack('>H', data[16:18])[0]

        # Check if this is for our universe
        if universe != self._artnet_universe:
            return

        # Extract DMX data
        dmx_data = data[18:18 + min(length, 512)]
        channels = list(dmx_data) + [0] * (512 - len(dmx_data))

        self._packets_received += 1
        self._last_sequence = sequence

        # Call the callback with received data
        if self.callback:
            self.callback(self.universe_id, channels)

    def get_status(self) -> dict:
        return {
            "protocol": "artnet_input",
            "running": self._running,
            "bind_ip": self.config.get("bind_ip", "0.0.0.0"),
            "port": self.config.get("port", 6454),
            "artnet_universe": self._artnet_universe,
            "packets_received": self._packets_received
        }


class SACNProtocol(asyncio.DatagramProtocol):
    """Asyncio protocol for sACN/E1.31 UDP reception."""

    def __init__(self, input_handler: 'SACNInput'):
        self.input_handler = input_handler
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        source_ip = addr[0]

        # Ignore self (loopback prevention) - check if packet is from this machine
        if self.input_handler._ignore_self and source_ip in LOCAL_IPS:
            return

        # Blacklist check - ignore packets from specific IP
        if self.input_handler._ignore_ip_filter and source_ip == self.input_handler._ignore_ip_filter:
            return

        # Whitelist check - only accept from specific IP
        if self.input_handler._source_ip_filter and source_ip != self.input_handler._source_ip_filter:
            return

        self.input_handler._parse_sacn_packet(data)

    def error_received(self, exc):
        logger.error(f"Universe {self.input_handler.universe_id}: sACN protocol error: {exc}")

    def connection_lost(self, exc):
        pass


class SACNInput(DMXInput):
    """sACN/E1.31 protocol input listener."""

    # sACN multicast base address: 239.255.x.x where x.x = universe
    SACN_MULTICAST_BASE = "239.255"
    SACN_PORT = 5568

    def __init__(self, universe_id: int, config: dict, callback: Callable[[int, List[int]], None]):
        super().__init__(universe_id, config, callback)
        self._transport = None
        self._protocol = None
        self._packets_received = 0
        self._sacn_universe = 1
        self._multicast_addr = None
        self._source_ip_filter = ""
        self._ignore_ip_filter = ""
        self._ignore_self = False

    async def start(self) -> bool:
        try:
            self._sacn_universe = self.config.get("sacn_universe", self.universe_id)
            multicast = self.config.get("multicast", True)
            bind_ip = self.config.get("bind_ip", "0.0.0.0")
            self._source_ip_filter = self.config.get("source_ip", "").strip()
            self._ignore_ip_filter = self.config.get("ignore_ip", "").strip()
            self._ignore_self = self.config.get("ignore_self", False)

            loop = asyncio.get_event_loop()

            if multicast:
                # Calculate multicast address for this universe
                # Universe 1 = 239.255.0.1, Universe 256 = 239.255.1.0, etc.
                high_byte = (self._sacn_universe >> 8) & 0xFF
                low_byte = self._sacn_universe & 0xFF
                mcast_addr = f"{self.SACN_MULTICAST_BASE}.{high_byte}.{low_byte}"
                self._multicast_addr = mcast_addr

                # For multicast, we need to create a socket manually to join the group
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except (AttributeError, OSError):
                    pass

                sock.bind(('', self.SACN_PORT))

                # Join multicast group
                if bind_ip == "0.0.0.0":
                    # Join on all interfaces when bind_ip is 0.0.0.0
                    # This fixes Windows picking the wrong interface on multi-homed systems
                    for local_ip in LOCAL_IPS:
                        if local_ip not in ('127.0.0.1', '::1') and ':' not in local_ip:  # Skip loopback and IPv6
                            try:
                                mreq = struct.pack("4s4s", socket.inet_aton(mcast_addr), socket.inet_aton(local_ip))
                                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                                logger.debug(f"Joined multicast {mcast_addr} on interface {local_ip}")
                            except OSError:
                                pass  # Interface might not support multicast
                else:
                    mreq = struct.pack("4s4s", socket.inet_aton(mcast_addr), socket.inet_aton(bind_ip))
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                sock.setblocking(False)

                self._transport, self._protocol = await loop.create_datagram_endpoint(
                    lambda: SACNProtocol(self),
                    sock=sock
                )

                mode = f"multicast {mcast_addr}"
            else:
                # Unicast - create socket manually for cross-platform compatibility
                # Windows doesn't support reuse_port parameter in create_datagram_endpoint
                self._multicast_addr = None
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except (AttributeError, OSError):
                    pass  # Windows doesn't have SO_REUSEPORT
                # On Windows, binding to empty string works better than "0.0.0.0" for receiving unicast
                actual_bind = '' if bind_ip == "0.0.0.0" else bind_ip
                sock.bind((actual_bind, self.SACN_PORT))
                sock.setblocking(False)

                self._transport, self._protocol = await loop.create_datagram_endpoint(
                    lambda: SACNProtocol(self),
                    sock=sock
                )
                mode = f"unicast {bind_ip}"

            self._running = True
            filter_parts = []
            if self._source_ip_filter:
                filter_parts.append(f"accept from: {self._source_ip_filter}")
            if self._ignore_ip_filter:
                filter_parts.append(f"ignore: {self._ignore_ip_filter}")
            if self._ignore_self:
                filter_parts.append("ignore self")
            filter_info = f", {', '.join(filter_parts)}" if filter_parts else ""
            logger.info(f"Universe {self.universe_id}: sACN input started <- {mode}:{self.SACN_PORT} (sacn universe {self._sacn_universe}{filter_info})")
            return True

        except OSError as e:
            logger.error(f"Universe {self.universe_id}: Failed to bind sACN input - {e}")
            return False
        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Failed to start sACN input: {e}")
            return False

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None

        logger.info(f"Universe {self.universe_id}: sACN input stopped (received {self._packets_received} packets)")

    def _parse_sacn_packet(self, data: bytes) -> None:
        """Parse sACN/E1.31 packet and extract channel data."""
        # Minimum sACN packet size
        if len(data) < 126:
            return

        # Check ACN packet identifier
        acn_id = b'\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00'
        if data[4:16] != acn_id:
            return

        # Get universe from DMP layer (bytes 113-114, big-endian)
        universe = struct.unpack('>H', data[113:115])[0]

        if universe != self._sacn_universe:
            return

        # Get DMX start code (byte 125) - should be 0 for DMX
        start_code = data[125]
        if start_code != 0:
            return

        # Extract DMX data (starting at byte 126)
        dmx_data = data[126:126 + 512]
        channels = list(dmx_data) + [0] * (512 - len(dmx_data))

        self._packets_received += 1

        # Call the callback with received data
        if self.callback:
            self.callback(self.universe_id, channels)

    def get_status(self) -> dict:
        return {
            "protocol": "sacn_input",
            "running": self._running,
            "sacn_universe": self._sacn_universe,
            "multicast": self.config.get("multicast", True),
            "multicast_addr": self._multicast_addr,
            "packets_received": self._packets_received
        }


class MIDIInput(DMXInput):
    """
    MIDI input for a specific universe.

    This is a lightweight wrapper that registers a universe for MIDI input.
    The actual MIDI device handling is done by MIDIHandler in dmx_interface.
    CC mappings in the database determine which CCs map to which channels.
    """

    def __init__(self, universe_id: int, config: dict, callback: Callable[[int, List[int]], None]):
        super().__init__(universe_id, config, callback)
        self._device_name = config.get("device_name", "")
        # Buffer for input channel values (512 channels)
        self._channel_values = [0] * 512

    async def start(self) -> bool:
        """Mark this universe as having MIDI input enabled."""
        self._running = True
        logger.info(f"MIDI input started for universe {self.universe_id} (device: {self._device_name or 'any'})")
        return True

    async def stop(self) -> None:
        """Stop MIDI input for this universe."""
        self._running = False
        logger.info(f"MIDI input stopped for universe {self.universe_id}")

    def get_status(self) -> dict:
        """Return status information about this MIDI input."""
        return {
            "type": "midi",
            "universe_id": self.universe_id,
            "device_name": self._device_name,
            "running": self._running
        }

    def set_channel(self, channel: int, value: int) -> None:
        """Set a channel value and trigger callback."""
        if 1 <= channel <= 512:
            self._channel_values[channel - 1] = value
            # Send full 512 channels to callback (like other inputs)
            self.callback(self.universe_id, self._channel_values.copy())

    def get_device_name(self) -> str:
        """Get the configured MIDI device name."""
        return self._device_name


def create_input(universe_id: int, input_type: str, config: dict, callback: Callable[[int, List[int]], None]) -> Optional[DMXInput]:
    """Factory function to create the appropriate input for a device type."""

    input_type = input_type.lower() if input_type else "none"

    if input_type == "artnet_input" or input_type == "artnet":
        return ArtNetInput(universe_id, config, callback)

    elif input_type == "sacn_input" or input_type == "sacn" or input_type == "e131":
        return SACNInput(universe_id, config, callback)

    elif input_type == "midi_input" or input_type == "midi":
        return MIDIInput(universe_id, config, callback)

    elif input_type == "none" or input_type == "":
        return None

    else:
        logger.warning(f"Universe {universe_id}: Unknown input type '{input_type}'")
        return None


def get_available_input_protocols() -> List[dict]:
    """Return list of available input protocols and their configuration schemas."""
    return [
        {
            "id": "none",
            "name": "None",
            "available": True,
            "config_schema": {}
        },
        {
            "id": "artnet_input",
            "name": "Art-Net Input",
            "available": True,
            "config_schema": {
                "bind_ip": {"type": "string", "default": "0.0.0.0", "description": "Network interface to bind (0.0.0.0 = all)"},
                "port": {"type": "integer", "default": 6454, "description": "Art-Net port"},
                "artnet_universe": {"type": "integer", "default": 0, "description": "Art-Net universe to listen for (0-32767)"},
                "source_ip": {"type": "string", "default": "", "description": "Only accept from this IP (whitelist, empty = all)"},
                "ignore_ip": {"type": "string", "default": "", "description": "Ignore packets from this IP (blacklist)"},
                "ignore_self": {"type": "boolean", "default": False, "description": "Ignore packets from this machine (loopback prevention)"}
            }
        },
        {
            "id": "sacn_input",
            "name": "sACN / E1.31 Input",
            "available": True,
            "config_schema": {
                "sacn_universe": {"type": "integer", "default": 1, "description": "sACN universe to listen for (1-63999)"},
                "multicast": {"type": "boolean", "default": True, "description": "Use multicast (recommended)"},
                "bind_ip": {"type": "string", "default": "0.0.0.0", "description": "Network interface to bind (0.0.0.0 = all)"},
                "source_ip": {"type": "string", "default": "", "description": "Only accept from this IP (whitelist, empty = all)"},
                "ignore_ip": {"type": "string", "default": "", "description": "Ignore packets from this IP (blacklist)"},
                "ignore_self": {"type": "boolean", "default": False, "description": "Ignore packets from this machine (loopback prevention)"}
            }
        },
        {
            "id": "midi_input",
            "name": "MIDI",
            "available": True,
            "config_schema": {
                "device_name": {"type": "string", "default": "", "description": "MIDI device name (empty = any connected device)"}
            }
        }
    ]
