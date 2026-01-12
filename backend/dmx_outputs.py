"""
DMX Output Protocol Implementations.
Provides abstract base class and concrete implementations for Art-Net, sACN, and Mock outputs.
Uses pyartnet 2.0+ which supports both Art-Net and sACN.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import asyncio
import logging

logger = logging.getLogger(__name__)

# Try to import pyartnet (supports both Art-Net and sACN in v2.0+)
try:
    from pyartnet import ArtNetNode, SacnNode
    PYARTNET_AVAILABLE = True
except ImportError:
    PYARTNET_AVAILABLE = False
    logger.warning("pyartnet not available - Art-Net and sACN output disabled")


class DMXOutput(ABC):
    """Abstract base class for DMX output protocols."""

    def __init__(self, universe_id: int, config: dict):
        self.universe_id = universe_id
        self.config = config
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @abstractmethod
    async def start(self) -> bool:
        """Initialize and start the output. Returns success status."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop and cleanup the output."""
        pass

    @abstractmethod
    async def send_dmx(self, channels: List[int]) -> None:
        """Send 512 channel values to the output."""
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """Return status information about this output."""
        pass


class ArtNetOutput(DMXOutput):
    """Art-Net protocol output using pyartnet 2.0+."""

    # Shared nodes per IP to avoid socket conflicts
    _shared_nodes: Dict[str, Any] = {}
    _node_refs: Dict[str, int] = {}

    def __init__(self, universe_id: int, config: dict):
        super().__init__(universe_id, config)
        self._node = None
        self._channel = None
        self._node_key: Optional[str] = None

    async def start(self) -> bool:
        if not PYARTNET_AVAILABLE:
            logger.error(f"Universe {self.universe_id}: Art-Net not available (pyartnet not installed)")
            return False

        try:
            ip = self.config.get("ip", "255.255.255.255")
            port = self.config.get("port", 6454)
            artnet_universe = self.config.get("universe", self.universe_id - 1)  # Art-Net is 0-indexed
            fps = self.config.get("fps", 40)

            self._node_key = f"artnet:{ip}:{port}"

            # Reuse existing node for same IP:port or create new one
            if self._node_key in ArtNetOutput._shared_nodes:
                self._node = ArtNetOutput._shared_nodes[self._node_key]
                ArtNetOutput._node_refs[self._node_key] += 1
            else:
                # pyartnet 2.0 API: use create() factory method for simpler setup
                self._node = ArtNetNode.create(ip, port, max_fps=fps, refresh_every=2)
                # Enter the async context to open socket
                await self._node.__aenter__()
                ArtNetOutput._shared_nodes[self._node_key] = self._node
                ArtNetOutput._node_refs[self._node_key] = 1

            # Add universe and channel to the node
            universe = self._node.add_universe(artnet_universe)
            self._channel = universe.add_channel(start=1, width=512)

            self._running = True
            logger.info(f"Universe {self.universe_id}: Art-Net started -> {ip}:{port} universe {artnet_universe}")
            return True

        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Failed to start Art-Net: {e}")
            return False

    async def stop(self) -> None:
        if not self._running:
            return

        try:
            if self._node_key and self._node_key in ArtNetOutput._node_refs:
                ArtNetOutput._node_refs[self._node_key] -= 1

                # Only stop node if no more universes are using it
                if ArtNetOutput._node_refs[self._node_key] <= 0:
                    if self._node:
                        await self._node.__aexit__(None, None, None)
                    del ArtNetOutput._shared_nodes[self._node_key]
                    del ArtNetOutput._node_refs[self._node_key]

            self._running = False
            self._node = None
            self._channel = None
            logger.info(f"Universe {self.universe_id}: Art-Net stopped")

        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Error stopping Art-Net: {e}")

    async def send_dmx(self, channels: List[int]) -> None:
        if not self._running or not self._channel:
            return

        try:
            self._channel.set_values(channels)
        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Art-Net send error: {e}")

    def get_status(self) -> dict:
        return {
            "protocol": "artnet",
            "running": self._running,
            "ip": self.config.get("ip", "255.255.255.255"),
            "port": self.config.get("port", 6454),
            "artnet_universe": self.config.get("universe", self.universe_id - 1)
        }


class SACNOutput(DMXOutput):
    """sACN/E1.31 protocol output using pyartnet 2.0+ SacnNode."""

    # Shared nodes per multicast group
    _shared_nodes: Dict[str, Any] = {}
    _node_refs: Dict[str, int] = {}

    def __init__(self, universe_id: int, config: dict):
        super().__init__(universe_id, config)
        self._node = None
        self._channel = None
        self._node_key: Optional[str] = None

    async def start(self) -> bool:
        if not PYARTNET_AVAILABLE:
            logger.error(f"Universe {self.universe_id}: sACN not available (pyartnet not installed)")
            return False

        try:
            sacn_universe = self.config.get("universe", self.universe_id)
            multicast = self.config.get("multicast", True)
            unicast_ip = self.config.get("unicast_ip")
            fps = self.config.get("fps", 40)
            source_name = self.config.get("source_name", "DMXX")

            # Determine target - multicast or unicast
            if multicast:
                self._node_key = f"sacn:multicast"
            else:
                target_ip = unicast_ip or "255.255.255.255"
                self._node_key = f"sacn:unicast:{target_ip}"

            # Create or reuse node
            if self._node_key in SACNOutput._shared_nodes:
                self._node = SACNOutput._shared_nodes[self._node_key]
                SACNOutput._node_refs[self._node_key] += 1
            else:
                # pyartnet 2.0 SacnNode API - use factory methods
                if multicast:
                    # create_multicast uses multicast for all universes
                    self._node = SacnNode.create_multicast("0.0.0.0", max_fps=fps)
                else:
                    # create() for unicast to specific IP
                    self._node = SacnNode.create(target_ip, max_fps=fps)

                # Enter the async context to open socket
                await self._node.__aenter__()
                SACNOutput._shared_nodes[self._node_key] = self._node
                SACNOutput._node_refs[self._node_key] = 1

            # Add universe and channel
            universe = self._node.add_universe(sacn_universe)
            self._channel = universe.add_channel(start=1, width=512)

            self._running = True
            mode = "multicast" if multicast else f"unicast to {unicast_ip}"
            logger.info(f"Universe {self.universe_id}: sACN started -> universe {sacn_universe} ({mode})")
            return True

        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Failed to start sACN: {e}")
            return False

    async def stop(self) -> None:
        if not self._running:
            return

        try:
            if self._node_key and self._node_key in SACNOutput._node_refs:
                SACNOutput._node_refs[self._node_key] -= 1

                if SACNOutput._node_refs[self._node_key] <= 0:
                    if self._node:
                        await self._node.__aexit__(None, None, None)
                    del SACNOutput._shared_nodes[self._node_key]
                    del SACNOutput._node_refs[self._node_key]

            self._running = False
            self._node = None
            self._channel = None
            logger.info(f"Universe {self.universe_id}: sACN stopped")

        except Exception as e:
            logger.error(f"Universe {self.universe_id}: Error stopping sACN: {e}")

    async def send_dmx(self, channels: List[int]) -> None:
        if not self._running or not self._channel:
            return

        try:
            self._channel.set_values(channels)
        except Exception as e:
            logger.error(f"Universe {self.universe_id}: sACN send error: {e}")

    def get_status(self) -> dict:
        return {
            "protocol": "sacn",
            "running": self._running,
            "sacn_universe": self.config.get("universe", self.universe_id),
            "multicast": self.config.get("multicast", True)
        }


class MockOutput(DMXOutput):
    """Mock output for development and testing without hardware."""

    def __init__(self, universe_id: int, config: dict):
        super().__init__(universe_id, config)
        self._last_send: Optional[List[int]] = None

    async def start(self) -> bool:
        self._running = True
        log_level = self.config.get("log_level", "info")
        logger.info(f"Universe {self.universe_id}: Mock output started (log_level={log_level})")
        return True

    async def stop(self) -> None:
        self._running = False
        logger.info(f"Universe {self.universe_id}: Mock output stopped")

    async def send_dmx(self, channels: List[int]) -> None:
        if not self._running:
            return

        self._last_send = channels

        log_level = self.config.get("log_level", "info")
        if log_level == "debug":
            active = sum(1 for v in channels if v > 0)
            logger.debug(f"Universe {self.universe_id}: Mock send ({active} active channels)")

    def get_status(self) -> dict:
        return {
            "protocol": "mock",
            "running": self._running,
            "last_send": self._last_send is not None
        }


def create_output(universe_id: int, device_type: str, config: dict) -> DMXOutput:
    """Factory function to create the appropriate output for a device type."""

    device_type = device_type.lower() if device_type else "mock"

    if device_type == "artnet":
        if not PYARTNET_AVAILABLE:
            logger.warning(f"Universe {universe_id}: Art-Net requested but not available, falling back to mock")
            return MockOutput(universe_id, config)
        return ArtNetOutput(universe_id, config)

    elif device_type == "sacn" or device_type == "e131":
        if not PYARTNET_AVAILABLE:
            logger.warning(f"Universe {universe_id}: sACN requested but not available, falling back to mock")
            return MockOutput(universe_id, config)
        return SACNOutput(universe_id, config)

    else:
        if device_type != "mock":
            logger.warning(f"Universe {universe_id}: Unknown device type '{device_type}', using mock")
        return MockOutput(universe_id, config)


def get_available_protocols() -> List[dict]:
    """Return list of available protocols and their configuration schemas."""
    return [
        {
            "id": "artnet",
            "name": "Art-Net",
            "available": PYARTNET_AVAILABLE,
            "config_schema": {
                "ip": {"type": "string", "default": "255.255.255.255", "description": "Target IP address"},
                "port": {"type": "integer", "default": 6454, "description": "Art-Net port"},
                "universe": {"type": "integer", "default": 0, "description": "Art-Net universe (0-32767)"},
                "fps": {"type": "integer", "default": 40, "description": "Refresh rate in Hz"}
            }
        },
        {
            "id": "sacn",
            "name": "sACN / E1.31",
            "available": PYARTNET_AVAILABLE,
            "config_schema": {
                "universe": {"type": "integer", "default": 1, "description": "sACN universe (1-63999)"},
                "multicast": {"type": "boolean", "default": True, "description": "Use multicast"},
                "unicast_ip": {"type": "string", "default": None, "description": "Unicast destination IP"},
                "fps": {"type": "integer", "default": 40, "description": "Refresh rate in Hz"},
                "source_name": {"type": "string", "default": "DMXX", "description": "Source name in packets"}
            }
        },
        {
            "id": "mock",
            "name": "Mock (Testing)",
            "available": True,
            "config_schema": {
                "log_level": {"type": "string", "default": "info", "description": "Logging level (debug/info)"}
            }
        }
    ]
