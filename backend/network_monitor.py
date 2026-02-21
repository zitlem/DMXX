"""
Network Monitor for Art-Net and sACN traffic.
Passively detects ALL DMX network traffic regardless of configured inputs.
"""
import asyncio
import socket
import struct
import time
import logging
from typing import Dict, List, Set, Optional, Callable
from dataclasses import dataclass, field
from fastapi import WebSocket
from .dmx_inputs import LOCAL_IPS

logger = logging.getLogger(__name__)


@dataclass
class SourceInfo:
    """Tracks information about a DMX source."""
    ip: str
    protocol: str  # "artnet" or "sacn"
    universe: int
    first_seen: float
    last_seen: float
    packet_count: int = 0
    last_values: List[int] = field(default_factory=lambda: [0] * 512)
    changing_channels: Set[int] = field(default_factory=set)

    @property
    def packets_per_second(self) -> float:
        elapsed = time.time() - self.first_seen
        if elapsed > 0:
            return self.packet_count / elapsed
        return 0.0

    @property
    def is_active(self) -> bool:
        return (time.time() - self.last_seen) < 5.0

    def to_dict(self, include_values: bool = False) -> dict:
        result = {
            "ip": self.ip,
            "protocol": self.protocol,
            "universe": self.universe,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "packet_count": self.packet_count,
            "packets_per_second": round(self.packets_per_second, 1),
            "is_active": self.is_active,
            "changing_channels": list(self.changing_channels)[:20]  # Limit to 20 for UI
        }
        if include_values:
            result["values"] = self.last_values
        return result


class ArtNetMonitorProtocol(asyncio.DatagramProtocol):
    """Captures ALL Art-Net packets without filtering."""

    ARTNET_HEADER = b'Art-Net\x00'
    ARTNET_OPCODE_DMX = 0x5000

    def __init__(self, monitor: 'NetworkMonitor'):
        self.monitor = monitor
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        source_ip = addr[0]

        if len(data) < 18:
            return

        # Check Art-Net header
        if data[:8] != self.ARTNET_HEADER:
            return

        # Get opcode (little-endian)
        opcode = struct.unpack('<H', data[8:10])[0]
        if opcode != self.ARTNET_OPCODE_DMX:
            return

        # Extract universe (no filtering!)
        universe = struct.unpack('<H', data[14:16])[0]
        length = struct.unpack('>H', data[16:18])[0]

        # Extract DMX data
        dmx_data = list(data[18:18 + min(length, 512)])
        dmx_data.extend([0] * (512 - len(dmx_data)))

        # Report to monitor
        self.monitor.on_packet_received("artnet", source_ip, universe, dmx_data)

    def error_received(self, exc):
        logger.error(f"Art-Net monitor protocol error: {exc}")

    def connection_lost(self, exc):
        pass


class SACNMonitorProtocol(asyncio.DatagramProtocol):
    """Captures sACN packets from multicast groups."""

    ACN_ID = b'\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00'

    def __init__(self, monitor: 'NetworkMonitor'):
        self.monitor = monitor
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        source_ip = addr[0]

        if len(data) < 126:
            return

        # Check ACN packet identifier
        if data[4:16] != self.ACN_ID:
            return

        # Extract universe (no filtering!)
        universe = struct.unpack('>H', data[113:115])[0]

        # Check start code (0 = DMX)
        if data[125] != 0:
            return

        # Extract DMX data
        dmx_data = list(data[126:126 + 512])
        dmx_data.extend([0] * (512 - len(dmx_data)))

        # Report to monitor
        self.monitor.on_packet_received("sacn", source_ip, universe, dmx_data)

    def error_received(self, exc):
        logger.error(f"sACN monitor protocol error: {exc}")

    def connection_lost(self, exc):
        pass


class NetworkMonitor:
    """Singleton service that monitors all Art-Net and sACN traffic."""

    ARTNET_PORT = 6454
    SACN_PORT = 5568
    SACN_MULTICAST_BASE = "239.255"

    def __init__(self):
        self._running = False
        self._sources: Dict[str, SourceInfo] = {}
        self._artnet_transport = None
        self._artnet_protocol = None
        self._sacn_transports: Dict[int, asyncio.DatagramTransport] = {}
        self._sacn_protocols: Dict[int, SACNMonitorProtocol] = {}
        self._clients: Set[WebSocket] = set()
        self._subscribed_sources: Dict[WebSocket, Set[str]] = {}
        self._last_broadcast = 0.0
        self._broadcast_interval = 0.1  # 100ms
        self._pending_updates: Dict[str, dict] = {}
        self._broadcast_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        # sACN universes to monitor (can be expanded dynamically)
        self._sacn_universes_to_monitor = list(range(1, 11))  # Monitor universes 1-10 by default

    def is_running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        """Start monitoring Art-Net and sACN traffic."""
        if self._running:
            return True

        try:
            loop = asyncio.get_event_loop()

            # Start Art-Net listener
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except (AttributeError, OSError):
                    pass
                sock.bind(('0.0.0.0', self.ARTNET_PORT))
                sock.setblocking(False)

                self._artnet_transport, self._artnet_protocol = await loop.create_datagram_endpoint(
                    lambda: ArtNetMonitorProtocol(self),
                    sock=sock
                )
                logger.info(f"Network Monitor: Art-Net listener started on port {self.ARTNET_PORT}")
            except OSError as e:
                logger.warning(f"Network Monitor: Could not bind to Art-Net port {self.ARTNET_PORT}: {e}")

            # Start sACN listeners for configured universes
            for universe in self._sacn_universes_to_monitor:
                await self._add_sacn_listener(universe)

            self._running = True

            # Start broadcast loop
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())

            # Start cleanup loop
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            logger.info("Network Monitor: Started")
            return True

        except Exception as e:
            logger.error(f"Network Monitor: Failed to start: {e}")
            return False

    async def _add_sacn_listener(self, universe: int) -> bool:
        """Add a sACN multicast listener for a specific universe."""
        if universe in self._sacn_transports:
            return True

        try:
            loop = asyncio.get_event_loop()

            # Calculate multicast address
            high_byte = (universe >> 8) & 0xFF
            low_byte = universe & 0xFF
            mcast_addr = f"{self.SACN_MULTICAST_BASE}.{high_byte}.{low_byte}"

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass

            sock.bind(('', self.SACN_PORT))

            # Join multicast group on all interfaces
            # This fixes Windows picking the wrong interface on multi-homed systems
            for local_ip in LOCAL_IPS:
                if local_ip not in ('127.0.0.1', '::1') and ':' not in local_ip:  # Skip loopback and IPv6
                    try:
                        mreq = struct.pack("4s4s", socket.inet_aton(mcast_addr), socket.inet_aton(local_ip))
                        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                    except OSError:
                        pass  # Interface might not support multicast
            sock.setblocking(False)

            transport, protocol = await loop.create_datagram_endpoint(
                lambda: SACNMonitorProtocol(self),
                sock=sock
            )

            self._sacn_transports[universe] = transport
            self._sacn_protocols[universe] = protocol
            logger.info(f"Network Monitor: sACN listener started for universe {universe} ({mcast_addr})")
            return True

        except OSError as e:
            logger.warning(f"Network Monitor: Could not bind sACN listener for universe {universe}: {e}")
            return False

    async def stop(self) -> None:
        """Stop monitoring."""
        if not self._running:
            return

        self._running = False

        # Cancel tasks
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close Art-Net transport
        if self._artnet_transport:
            self._artnet_transport.close()
            self._artnet_transport = None
            self._artnet_protocol = None

        # Close sACN transports
        for transport in self._sacn_transports.values():
            transport.close()
        self._sacn_transports.clear()
        self._sacn_protocols.clear()

        # Notify clients
        await self._broadcast_to_clients({
            "type": "monitor_status",
            "data": {"running": False}
        })

        logger.info("Network Monitor: Stopped")

    def on_packet_received(self, protocol: str, source_ip: str, universe: int, values: List[int]):
        """Process incoming packet and detect changes."""
        key = f"{protocol}:{source_ip}:{universe}"
        now = time.time()

        is_new = key not in self._sources

        if is_new:
            self._sources[key] = SourceInfo(
                ip=source_ip,
                protocol=protocol,
                universe=universe,
                first_seen=now,
                last_seen=now
            )
            # Queue new source notification
            asyncio.create_task(self._broadcast_to_clients({
                "type": "monitor_source_new",
                "data": {
                    "key": key,
                    "protocol": protocol,
                    "ip": source_ip,
                    "universe": universe,
                    "first_seen": now
                }
            }))

            # If this is a new sACN universe we're not monitoring, add a listener
            if protocol == "sacn" and universe not in self._sacn_universes_to_monitor:
                self._sacn_universes_to_monitor.append(universe)
                asyncio.create_task(self._add_sacn_listener(universe))

        source = self._sources[key]
        source.packet_count += 1
        source.last_seen = now

        # Detect changing channels
        changing = set()
        changed_values = {}
        for i, (old, new) in enumerate(zip(source.last_values, values)):
            if old != new:
                channel = i + 1  # 1-indexed
                changing.add(channel)
                changed_values[channel] = new

        source.changing_channels = changing
        source.last_values = values

        # Queue update for batch broadcast (always update stats, even if no channels changed)
        self._pending_updates[key] = {
            "packet_count": source.packet_count,
            "packets_per_second": round(source.packets_per_second, 1),
            "last_seen": now,
            "changing_channels": list(changing)[:20],
            "changed_values": changed_values
        }

    async def _broadcast_loop(self):
        """Periodically broadcast batched updates to clients."""
        while self._running:
            try:
                await asyncio.sleep(self._broadcast_interval)

                if self._pending_updates and self._clients:
                    updates = self._pending_updates.copy()
                    self._pending_updates.clear()

                    await self._broadcast_to_clients({
                        "type": "monitor_update",
                        "data": {"sources": updates}
                    })

                # Always send full values to subscribed clients (moved outside the if block)
                for ws, subscribed_keys in list(self._subscribed_sources.items()):
                    for key in subscribed_keys:
                        if key in self._sources:
                            try:
                                await ws.send_json({
                                    "type": "monitor_source_values",
                                    "data": {
                                        "key": key,
                                        "values": self._sources[key].last_values
                                    }
                                })
                            except Exception:
                                pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Network Monitor broadcast error: {e}")

    async def _cleanup_loop(self):
        """Periodically clean up stale sources."""
        while self._running:
            try:
                await asyncio.sleep(5.0)

                now = time.time()
                stale_keys = []
                timeout_keys = []

                for key, source in self._sources.items():
                    age = now - source.last_seen
                    if age > 30:  # Remove after 30s
                        stale_keys.append(key)
                    elif age > 5 and source.is_active:  # Notify timeout after 5s
                        timeout_keys.append(key)

                # Notify about timeouts
                for key in timeout_keys:
                    await self._broadcast_to_clients({
                        "type": "monitor_source_timeout",
                        "data": {
                            "key": key,
                            "last_seen": self._sources[key].last_seen
                        }
                    })

                # Remove stale sources
                for key in stale_keys:
                    del self._sources[key]
                    await self._broadcast_to_clients({
                        "type": "monitor_source_removed",
                        "data": {"key": key}
                    })

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Network Monitor cleanup error: {e}")

    async def _broadcast_to_clients(self, message: dict):
        """Send message to all connected monitor clients."""
        dead_clients = []
        for ws in self._clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead_clients.append(ws)

        for ws in dead_clients:
            self._clients.discard(ws)
            self._subscribed_sources.pop(ws, None)

    async def connect_client(self, websocket: WebSocket):
        """Connect a new WebSocket client."""
        await websocket.accept()
        self._clients.add(websocket)
        self._subscribed_sources[websocket] = set()

        # Send current state
        await websocket.send_json({
            "type": "monitor_status",
            "data": {
                "running": self._running,
                "sources": {
                    key: source.to_dict()
                    for key, source in self._sources.items()
                }
            }
        })

    def disconnect_client(self, websocket: WebSocket):
        """Disconnect a WebSocket client."""
        self._clients.discard(websocket)
        self._subscribed_sources.pop(websocket, None)

    async def subscribe_source(self, websocket: WebSocket, source_key: str):
        """Subscribe a client to full value updates for a source."""
        if websocket in self._subscribed_sources:
            self._subscribed_sources[websocket].add(source_key)

            # Send current values immediately
            if source_key in self._sources:
                await websocket.send_json({
                    "type": "monitor_source_values",
                    "data": {
                        "key": source_key,
                        "values": self._sources[source_key].last_values
                    }
                })

    def unsubscribe_source(self, websocket: WebSocket, source_key: str):
        """Unsubscribe a client from a source."""
        if websocket in self._subscribed_sources:
            self._subscribed_sources[websocket].discard(source_key)

    def get_all_sources(self) -> Dict[str, dict]:
        """Get all detected sources."""
        return {
            key: source.to_dict()
            for key, source in self._sources.items()
        }

    def get_source(self, key: str) -> Optional[dict]:
        """Get detailed info for a specific source."""
        if key in self._sources:
            return self._sources[key].to_dict(include_values=True)
        return None

    def get_stats(self) -> dict:
        """Get monitor statistics."""
        return {
            "total_sources": len(self._sources),
            "active_sources": sum(1 for s in self._sources.values() if s.is_active),
            "total_packets": sum(s.packet_count for s in self._sources.values()),
            "artnet_sources": sum(1 for s in self._sources.values() if s.protocol == "artnet"),
            "sacn_sources": sum(1 for s in self._sources.values() if s.protocol == "sacn"),
            "connected_clients": len(self._clients)
        }


# Singleton instance
network_monitor = NetworkMonitor()
