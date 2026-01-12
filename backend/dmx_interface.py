"""
DMX Interface for sending DMX data via Art-Net, sACN, or mock output.
Also handles DMX inputs and passthrough routing.
"""
import asyncio
import time
from typing import Dict, List, Optional, Callable
import logging

from .dmx_outputs import DMXOutput, create_output, get_available_protocols
from .dmx_inputs import DMXInput, create_input, get_available_input_protocols
from .websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class DMXUniverse:
    """Represents a single DMX universe with 512 channels."""

    def __init__(self, universe_id: int):
        self.universe_id = universe_id
        self.channels = [0] * 512
        self.active = False

    def set_channel(self, channel: int, value: int) -> None:
        """Set a single channel value (1-512, value 0-255)."""
        if 1 <= channel <= 512 and 0 <= value <= 255:
            self.channels[channel - 1] = value

    def get_channel(self, channel: int) -> int:
        """Get a single channel value (1-512)."""
        if 1 <= channel <= 512:
            return self.channels[channel - 1]
        return 0

    def set_all(self, values: List[int]) -> None:
        """Set all 512 channels at once."""
        for i, v in enumerate(values[:512]):
            self.channels[i] = max(0, min(255, v))

    def blackout(self) -> None:
        """Set all channels to zero."""
        self.channels = [0] * 512

    def get_all(self) -> List[int]:
        """Get all channel values."""
        return self.channels.copy()


class DMXInterface:
    """Interface for communicating with DMX inputs and outputs (Art-Net, sACN, Mock)."""

    def __init__(self):
        self.universes: Dict[int, DMXUniverse] = {}
        self.outputs: Dict[int, List[DMXOutput]] = {}  # Changed to list for multiple outputs
        self._output_configs: Dict[int, List[dict]] = {}  # Store output configs with IDs
        self.inputs: Dict[int, DMXInput] = {}
        self._input_values: Dict[int, List[int]] = {}  # Last received input values per universe
        self._passthrough_config: Dict[int, dict] = {}  # Passthrough settings per universe
        self._running = False
        self._callbacks: List[Callable] = []
        self._blackout_active = False
        self._pre_blackout_values: Dict[int, List[int]] = {}
        # Throttle input broadcasts to prevent WebSocket flooding
        self._last_input_broadcast: Dict[int, float] = {}
        self._input_broadcast_interval = 0.1  # 100ms = 10 updates/sec max (was 50ms)
        # Throttle group broadcasts to prevent flooding when many groups are mapped to input
        self._last_group_broadcast: Dict[int, float] = {}  # {group_id: timestamp}
        self._group_broadcast_interval = 0.1  # 100ms = 10 updates/sec max per group
        self._last_group_values: Dict[int, int] = {}  # {group_id: last_value} for change detection
        # Source tracking - tracks where each channel's last value came from
        self._channel_sources: Dict[int, Dict[int, str]] = {}  # {universe: {channel: "local"|"input"|"user_xxx"|"group"}}
        # Channel mapping configuration
        self._mapping_enabled = False
        self._unmapped_behavior = "passthrough"  # "passthrough" or "ignore"
        # Forward map: {(src_universe, src_channel): [(dst_universe, dst_channel), ...]}
        self._channel_map: Dict[tuple, List[tuple]] = {}
        # Reverse map for UI lookups: {(dst_universe, dst_channel): (src_universe, src_channel)}
        self._reverse_map: Dict[tuple, tuple] = {}
        # Groups/Masters configuration
        self._groups: Dict[int, dict] = {}  # {group_id: group_config}
        self._master_to_groups: Dict[tuple, List[int]] = {}  # {(universe, channel): [group_ids]} - one master can control multiple groups
        # Track each group's contribution per channel for HTP merge
        # Key: (universe_id, channel), Value: {group_id: output_value}
        self._group_contributions: Dict[tuple, Dict[int, int]] = {}

    async def connect(self) -> bool:
        """Initialize the DMX interface."""
        self._running = True
        logger.info("DMX interface initialized")
        return True

    async def disconnect(self) -> None:
        """Disconnect and cleanup all inputs and outputs."""
        self._running = False
        # Stop all inputs
        for universe_id in list(self.inputs.keys()):
            await self.remove_input(universe_id)
        # Stop all outputs for all universes
        for universe_id in list(self.outputs.keys()):
            await self.remove_all_outputs(universe_id)
        logger.info("DMX interface disconnected")

    async def add_universe(self, universe_id: int, device_type: str = "mock", config: dict = None) -> DMXUniverse:
        """Add a universe with a single output (legacy compatibility).

        For multiple outputs, use add_output() instead.
        """
        config = config or {}

        # Create universe data structure if not exists
        if universe_id not in self.universes:
            self.universes[universe_id] = DMXUniverse(universe_id)

        # Remove all existing outputs if reconfiguring via legacy method
        if universe_id in self.outputs:
            await self.remove_all_outputs(universe_id)

        # Add the single output
        await self.add_output(universe_id, device_type, config)

        return self.universes[universe_id]

    async def add_output(self, universe_id: int, device_type: str, config: dict = None,
                         output_id: int = None, enabled: bool = True) -> Optional[int]:
        """Add an output to a universe. Returns the output_id."""
        config = config or {}

        # Create universe data structure if not exists
        if universe_id not in self.universes:
            self.universes[universe_id] = DMXUniverse(universe_id)

        # Initialize outputs list if needed
        if universe_id not in self.outputs:
            self.outputs[universe_id] = []
            self._output_configs[universe_id] = []

        # Create and start the protocol output
        output = create_output(universe_id, device_type, config)

        if enabled:
            success = await output.start()
            if not success:
                logger.warning(f"Universe {universe_id}: Output {device_type} failed to start")
                # Don't fallback to mock - just mark as not running

        # Store output and config
        self.outputs[universe_id].append(output)
        output_config = {
            "id": output_id,
            "device_type": device_type,
            "config": config,
            "enabled": enabled
        }
        self._output_configs[universe_id].append(output_config)

        self.universes[universe_id].active = any(o.running for o in self.outputs[universe_id])

        logger.info(f"Universe {universe_id}: Added output {device_type} (id={output_id}, enabled={enabled})")
        return output_id

    async def remove_output(self, universe_id: int, output_id: int) -> bool:
        """Remove a specific output from a universe by its database ID."""
        if universe_id not in self.outputs:
            return False

        # Find and remove the output with matching ID
        for i, config in enumerate(self._output_configs.get(universe_id, [])):
            if config.get("id") == output_id:
                output = self.outputs[universe_id][i]
                if output.running:
                    await output.stop()
                self.outputs[universe_id].pop(i)
                self._output_configs[universe_id].pop(i)
                logger.info(f"Universe {universe_id}: Removed output id={output_id}")
                return True

        return False

    async def remove_all_outputs(self, universe_id: int) -> None:
        """Remove all outputs from a universe."""
        if universe_id in self.outputs:
            for output in self.outputs[universe_id]:
                if output.running:
                    await output.stop()
            del self.outputs[universe_id]
        if universe_id in self._output_configs:
            del self._output_configs[universe_id]

    async def remove_universe(self, universe_id: int) -> None:
        """Remove a universe and stop all its outputs."""
        # Also remove any input for this universe
        if universe_id in self.inputs:
            await self.remove_input(universe_id)

        # Remove all outputs
        await self.remove_all_outputs(universe_id)

        if universe_id in self.universes:
            del self.universes[universe_id]

        if universe_id in self._passthrough_config:
            del self._passthrough_config[universe_id]

    async def add_input(self, universe_id: int, input_type: str, config: dict = None,
                       passthrough_enabled: bool = False, passthrough_mode: str = "htp",
                       passthrough_show_ui: bool = False) -> bool:
        """Add an input listener to a universe."""
        config = config or {}

        # Ensure universe exists
        if universe_id not in self.universes:
            self.universes[universe_id] = DMXUniverse(universe_id)

        # Remove existing input if reconfiguring
        if universe_id in self.inputs:
            await self.inputs[universe_id].stop()
            del self.inputs[universe_id]

        # Derive new passthrough_mode from old fields for backwards compatibility
        if passthrough_enabled and passthrough_show_ui:
            pt_mode = "faders_output"
        elif passthrough_enabled and not passthrough_show_ui:
            pt_mode = "output_only"
        elif not passthrough_enabled and passthrough_show_ui:
            pt_mode = "view_only"
        else:
            pt_mode = "off"

        # Store passthrough config with both old and new formats
        self._passthrough_config[universe_id] = {
            "passthrough_mode": pt_mode,
            "mode": passthrough_mode,  # This is the HTP/LTP merge mode
            "enabled": passthrough_enabled,
            "show_ui": passthrough_show_ui
        }
        logger.info(f"Universe {universe_id}: Input passthrough_mode={pt_mode}, merge={passthrough_mode}")

        # Create and start input if type is not "none"
        if input_type and input_type.lower() != "none":
            input_handler = create_input(universe_id, input_type, config, self._on_input_received)
            if input_handler:
                success = await input_handler.start()
                if success:
                    self.inputs[universe_id] = input_handler
                    self._input_values[universe_id] = [0] * 512
                    return True
                else:
                    logger.error(f"Universe {universe_id}: Failed to start input")
                    return False
        return True

    async def remove_input(self, universe_id: int) -> None:
        """Remove input listener from a universe."""
        if universe_id in self.inputs:
            await self.inputs[universe_id].stop()
            del self.inputs[universe_id]
        if universe_id in self._input_values:
            del self._input_values[universe_id]

    def _on_input_received(self, universe_id: int, channels: List[int]) -> None:
        """Callback when input data is received."""
        self._input_values[universe_id] = channels

        # Get passthrough config
        config = self._passthrough_config.get(universe_id, {})

        # Support both old format (enabled/show_ui) and new format (passthrough_mode)
        # New modes: "off", "view_only", "faders_output"
        passthrough_mode = config.get("passthrough_mode", "off")

        # Backwards compatibility: convert old format to new
        if passthrough_mode == "off" and config.get("enabled", False):
            if config.get("show_ui", False):
                passthrough_mode = "faders_output"
            else:
                passthrough_mode = "output_only"

        merge_mode = config.get("mode", "htp")  # HTP or LTP

        # Handle passthrough to output (faders_output or output_only modes)
        if passthrough_mode in ("faders_output", "output_only"):
            if self._mapping_enabled:
                self._apply_mapped_passthrough(universe_id, channels, merge_mode)
            else:
                self._apply_passthrough(universe_id, channels, merge_mode)

        # Throttle WebSocket broadcasts to prevent flooding (Art-Net sends ~44 packets/sec)
        now = time.time()
        last_broadcast = self._last_input_broadcast.get(universe_id, 0)
        if now - last_broadcast >= self._input_broadcast_interval:
            self._last_input_broadcast[universe_id] = now
            self._notify_input_received(universe_id, channels)

            # Show on faders UI (view_only or faders_output modes)
            if passthrough_mode in ("view_only", "faders_output"):
                if self._mapping_enabled:
                    self._notify_mapped_input_to_ui(universe_id, channels)
                else:
                    self._notify_input_to_ui(universe_id, channels)

    def _apply_passthrough(self, universe_id: int, input_channels: List[int], mode: str) -> None:
        """Apply input values to the universe based on passthrough mode."""
        universe = self.get_universe(universe_id)
        if not universe or self._blackout_active:
            return

        if mode == "ltp":
            # Latest Takes Precedence - input completely overrides local
            universe.set_all(input_channels)
        else:
            # HTP - Highest Takes Precedence (default)
            current = universe.get_all()
            merged = [max(current[i], input_channels[i]) for i in range(512)]
            universe.set_all(merged)

        self._send_universe(universe_id)

        # Check if any channels are group masters and trigger them
        # Use raw input values (not HTP-merged) so groups respond directly to input=0
        all_channels = set(range(512))
        self._check_group_masters_for_input(universe_id, all_channels, input_channels)

    def _apply_mapped_passthrough(self, src_universe_id: int, input_channels: List[int], mode: str) -> None:
        """Apply input values with channel mapping to destination universes.

        Key behavior:
        - Mapped source channels route to their destinations only
        - Unmapped channels pass through 1:1 (if passthrough mode) or are ignored
        - Channels with no input value retain their current (local fader) value
        - Mapped destination channels are protected from unmapped passthrough
        """
        if self._blackout_active:
            return

        # Build per-destination-universe value arrays
        dst_values: Dict[int, List[int]] = {}  # {dst_universe: [512 values]}
        dst_has_value: Dict[int, set] = {}  # Track which output channels have values to apply

        # Pre-calculate all mapped destinations to protect them from passthrough
        mapped_destinations: Dict[int, set] = {}  # {dst_universe: set of dst_channel indices}
        for src_ch in range(1, 513):
            destinations = self._channel_map.get((src_universe_id, src_ch), [])
            for dst_universe, dst_ch in destinations:
                if dst_universe not in mapped_destinations:
                    mapped_destinations[dst_universe] = set()
                mapped_destinations[dst_universe].add(dst_ch - 1)

        # Process all 512 input channels
        for src_ch in range(1, 513):
            value = input_channels[src_ch - 1]
            destinations = self._channel_map.get((src_universe_id, src_ch), [])

            if destinations:
                # Mapped channel - apply to all destinations
                # IMPORTANT: Only include in dst_has_value if value > 0
                # This prevents zero values from overwriting local fader values
                # (especially important in LTP mode where zero would zero the output)
                for dst_universe, dst_ch in destinations:
                    if dst_universe not in dst_values:
                        dst_values[dst_universe] = [0] * 512
                        dst_has_value[dst_universe] = set()
                    if value > 0:
                        dst_values[dst_universe][dst_ch - 1] = value
                        dst_has_value[dst_universe].add(dst_ch - 1)
            elif self._unmapped_behavior == "passthrough":
                # Unmapped channel with passthrough - pass to same channel 1:1
                # BUT skip if this output position is a mapped destination
                dst_ch_idx = src_ch - 1
                if dst_ch_idx not in mapped_destinations.get(src_universe_id, set()):
                    if src_universe_id not in dst_values:
                        dst_values[src_universe_id] = [0] * 512
                        dst_has_value[src_universe_id] = set()
                    dst_values[src_universe_id][dst_ch_idx] = value
                    dst_has_value[src_universe_id].add(dst_ch_idx)

        # Apply to each destination universe - ONLY channels that have values
        for dst_universe_id, values in dst_values.items():
            self._apply_selective_values(dst_universe_id, values, dst_has_value[dst_universe_id], mode)

    def _apply_selective_values(self, universe_id: int, input_channels: List[int],
                                active_channels: set, mode: str) -> None:
        """Apply values only to specific channels, leaving others unchanged.

        This ensures that channels without input values (e.g., mapped source channels
        in passthrough mode) retain their local fader values instead of being zeroed.
        """
        universe = self.get_universe(universe_id)
        if not universe:
            logger.warning(f"_apply_selective_values: universe {universe_id} not found!")
            return

        current = universe.get_all()

        for ch_idx in active_channels:
            input_val = input_channels[ch_idx]
            if mode == "ltp":
                current[ch_idx] = input_val
            else:  # HTP
                current[ch_idx] = max(current[ch_idx], input_val)

        universe.set_all(current)
        self._send_universe(universe_id)

        # Check if any of the changed channels are group masters
        # Use raw input values (not HTP-merged) so groups respond directly to input=0
        self._check_group_masters_for_input(universe_id, active_channels, input_channels)

    def _check_group_masters_for_input(self, universe_id: int, channels_changed: set, values: List[int]) -> None:
        """After passthrough applies values, check if any are group masters and trigger them.

        This allows DMX input to control groups via passthrough - when input arrives
        on a channel that's configured as a group master, the group will be triggered.
        """
        # Quick check: skip if no groups have masters in this universe
        # This is an optimization to avoid iterating channels unnecessarily
        has_masters = False
        for ch_idx in channels_changed:
            if (universe_id, ch_idx + 1) in self._master_to_groups:
                has_masters = True
                break

        if not has_masters:
            return

        now = time.time()
        groups_to_broadcast = []

        # Process channels that are group masters
        for ch_idx in channels_changed:
            channel = ch_idx + 1  # Convert to 1-based
            group_ids = self._master_to_groups.get((universe_id, channel), [])
            for group_id in group_ids:
                value = values[ch_idx]

                # Skip if value hasn't changed (reduces redundant processing)
                if self._last_group_values.get(group_id) == value:
                    continue
                self._last_group_values[group_id] = value

                # Store master value for effective base calculations
                if group_id in self._groups:
                    self._groups[group_id]["master_value"] = value
                self._apply_group(group_id, value)

                # Throttle broadcasts - only broadcast if enough time has passed
                last_broadcast = self._last_group_broadcast.get(group_id, 0)
                if now - last_broadcast >= self._group_broadcast_interval:
                    self._last_group_broadcast[group_id] = now
                    groups_to_broadcast.append((group_id, value))

        # Broadcast all changed groups (fewer tasks than before due to throttling)
        for group_id, value in groups_to_broadcast:
            asyncio.create_task(ws_manager.broadcast_group_value_changed(group_id, value))

    def set_passthrough(self, universe_id: int, enabled: bool = None, mode: str = "htp", show_ui: bool = False,
                        passthrough_mode: str = None) -> None:
        """Enable or disable passthrough for a universe.

        Args:
            universe_id: Universe ID
            enabled: (deprecated) Use passthrough_mode instead
            mode: HTP or LTP merge mode
            show_ui: (deprecated) Use passthrough_mode instead
            passthrough_mode: "off", "view_only", "faders_output", or "output_only"
        """
        # Support new passthrough_mode parameter
        if passthrough_mode is not None:
            self._passthrough_config[universe_id] = {
                "passthrough_mode": passthrough_mode,
                "mode": mode,
                # Keep old fields for backwards compatibility
                "enabled": passthrough_mode in ("faders_output", "output_only"),
                "show_ui": passthrough_mode in ("view_only", "faders_output")
            }
            logger.info(f"Universe {universe_id}: Passthrough mode={passthrough_mode}, merge={mode}")
        else:
            # Legacy support
            self._passthrough_config[universe_id] = {
                "enabled": enabled,
                "mode": mode,
                "show_ui": show_ui
            }
            logger.info(f"Universe {universe_id}: Passthrough {'enabled' if enabled else 'disabled'} (mode={mode}, show_ui={show_ui})")

    def set_channel_mapping(self, mappings: List[dict], unmapped_behavior: str = "passthrough") -> None:
        """Load channel mapping configuration.

        Args:
            mappings: List of mapping dicts with keys: src_universe, src_channel, dst_universe, dst_channel
            unmapped_behavior: "passthrough" (unmapped channels pass 1:1) or "ignore" (unmapped are zeroed)
        """
        self._channel_map.clear()
        self._reverse_map.clear()
        self._unmapped_behavior = unmapped_behavior

        for m in mappings:
            src = (m["src_universe"], m["src_channel"])
            dst = (m["dst_universe"], m["dst_channel"])
            if src not in self._channel_map:
                self._channel_map[src] = []
            self._channel_map[src].append(dst)
            self._reverse_map[dst] = src

        self._mapping_enabled = len(self._channel_map) > 0
        logger.info(f"Channel mapping {'enabled' if self._mapping_enabled else 'disabled'}: {len(self._channel_map)} mappings, unmapped={unmapped_behavior}")
        logger.info(f"Channel map contents: {self._channel_map}")

    def get_channel_mapping_status(self) -> dict:
        """Get current channel mapping status."""
        return {
            "enabled": self._mapping_enabled,
            "unmapped_behavior": self._unmapped_behavior,
            "mapping_count": len(self._channel_map)
        }

    def get_mapped_destination(self, src_universe: int, src_channel: int) -> List[tuple]:
        """Get destination(s) for a source channel."""
        return self._channel_map.get((src_universe, src_channel), [])

    def get_mapped_source(self, dst_universe: int, dst_channel: int) -> Optional[tuple]:
        """Get source for a destination channel (for UI display)."""
        return self._reverse_map.get((dst_universe, dst_channel))

    def get_input_values(self, universe_id: int) -> List[int]:
        """Get the last received input values for a universe."""
        return self._input_values.get(universe_id, [0] * 512)

    def get_input_status(self, universe_id: int) -> Optional[dict]:
        """Get status of a universe's input."""
        input_handler = self.inputs.get(universe_id)
        if input_handler:
            status = input_handler.get_status()
            status["passthrough"] = self._passthrough_config.get(universe_id, {})
            return status
        return None

    def get_input_protocols(self) -> List[dict]:
        """Get list of available input protocols."""
        return get_available_input_protocols()

    def _notify_input_received(self, universe_id: int, channels: List[int]) -> None:
        """Notify callbacks that input data was received."""
        for callback in self._callbacks:
            try:
                callback("input_received", {
                    "universe_id": universe_id,
                    "values": channels
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _notify_input_to_ui(self, universe_id: int, channels: List[int]) -> None:
        """Notify callbacks to update UI with input values (for show_ui feature)."""
        # Mark channels as coming from input source
        universe_sources = self._channel_sources.setdefault(universe_id, {})
        for i, val in enumerate(channels):
            if val > 0:  # Only track non-zero values as "input" source
                universe_sources[i + 1] = "input"

        for callback in self._callbacks:
            try:
                callback("input_to_ui", {
                    "universe_id": universe_id,
                    "values": channels
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _notify_mapped_input_to_ui(self, src_universe_id: int, channels: List[int]) -> None:
        """Notify callbacks to update UI with mapped input values."""
        # Build per-destination-universe notifications
        dst_notifications: Dict[int, List[int]] = {}

        # Pre-calculate mapped destinations to protect them from passthrough overwrite
        mapped_destinations: Dict[int, set] = {}
        for src_ch in range(1, 513):
            destinations = self._channel_map.get((src_universe_id, src_ch), [])
            for dst_universe, dst_ch in destinations:
                if dst_universe not in mapped_destinations:
                    mapped_destinations[dst_universe] = set()
                mapped_destinations[dst_universe].add(dst_ch - 1)

        for src_ch in range(1, 513):
            val = channels[src_ch - 1]
            destinations = self._channel_map.get((src_universe_id, src_ch), [])

            if destinations:
                # Send to mapped destination faders
                for dst_universe, dst_ch in destinations:
                    if dst_universe not in dst_notifications:
                        dst_notifications[dst_universe] = [0] * 512
                    dst_notifications[dst_universe][dst_ch - 1] = val
            elif self._unmapped_behavior == "passthrough":
                # Unmapped channel with passthrough - show on original fader
                # BUT skip if this output position is a mapped destination (protect mapped values)
                dst_ch_idx = src_ch - 1
                if dst_ch_idx not in mapped_destinations.get(src_universe_id, set()):
                    if src_universe_id not in dst_notifications:
                        dst_notifications[src_universe_id] = [0] * 512
                    dst_notifications[src_universe_id][dst_ch_idx] = val

        # Send notifications for each destination universe
        for dst_universe_id, values in dst_notifications.items():
            # Mark channels as coming from input source
            universe_sources = self._channel_sources.setdefault(dst_universe_id, {})
            for i, val in enumerate(values):
                if val > 0:
                    universe_sources[i + 1] = "input"

            for callback in self._callbacks:
                try:
                    callback("input_to_ui", {
                        "universe_id": dst_universe_id,
                        "values": values
                    })
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    def get_channel_source(self, universe_id: int, channel: int) -> str:
        """Get the source of a channel's last value change."""
        return self._channel_sources.get(universe_id, {}).get(channel, "unknown")

    def get_channel_sources(self, universe_id: int) -> Dict[int, str]:
        """Get all channel sources for a universe."""
        return self._channel_sources.get(universe_id, {}).copy()

    def get_universe(self, universe_id: int) -> Optional[DMXUniverse]:
        """Get a universe by ID."""
        return self.universes.get(universe_id)

    def set_channel(self, universe_id: int, channel: int, value: int, source: str = "local",
                    _from_group: bool = False) -> None:
        """Set a channel value in a universe.

        Args:
            universe_id: Universe ID
            channel: Channel number (1-512)
            value: Value (0-255)
            source: Source of the change - "local", "input", "group", or "user_<client_id>"
            _from_group: Internal flag to prevent group recursion
        """
        if self._blackout_active:
            # Store the value but don't output it
            if universe_id in self.universes:
                self._pre_blackout_values.setdefault(universe_id, self.universes[universe_id].get_all())
                self._pre_blackout_values[universe_id][channel - 1] = value
            return

        universe = self.get_universe(universe_id)
        if universe:
            universe.set_channel(channel, value)
            self._send_universe(universe_id)
            # Track the source of this channel change
            self._channel_sources.setdefault(universe_id, {})[channel] = source
            self._notify_callbacks(universe_id, channel, value, source)

            # Check if this channel is a group master (only if not already from a group)
            if not _from_group:
                group_ids = self._master_to_groups.get((universe_id, channel), [])
                for group_id in group_ids:
                    # Store master value for effective base calculations
                    if group_id in self._groups:
                        self._groups[group_id]["master_value"] = value
                    self._apply_group(group_id, value)

    def set_channels(self, universe_id: int, values: Dict[int, int], source: str = "local") -> None:
        """Set multiple channel values at once."""
        universe = self.get_universe(universe_id)
        if universe:
            for channel, value in values.items():
                if self._blackout_active:
                    self._pre_blackout_values.setdefault(universe_id, universe.get_all())
                    self._pre_blackout_values[universe_id][channel - 1] = value
                else:
                    universe.set_channel(channel, value)
                    self._channel_sources.setdefault(universe_id, {})[channel] = source

            if not self._blackout_active:
                self._send_universe(universe_id)
                for channel, value in values.items():
                    self._notify_callbacks(universe_id, channel, value, source)

    def get_channel(self, universe_id: int, channel: int) -> int:
        """Get a channel value."""
        universe = self.get_universe(universe_id)
        if universe:
            return universe.get_channel(channel)
        return 0

    def get_all_values(self, universe_id: int) -> List[int]:
        """Get all channel values for a universe."""
        universe = self.get_universe(universe_id)
        if universe:
            return universe.get_all()
        return [0] * 512

    def blackout(self) -> None:
        """Activate global blackout."""
        self._blackout_active = True
        self._pre_blackout_values = {}

        for universe_id, universe in self.universes.items():
            self._pre_blackout_values[universe_id] = universe.get_all()
            universe.blackout()
            self._send_universe(universe_id)

        self._notify_blackout(True)

    def release_blackout(self) -> None:
        """Release global blackout and restore previous values."""
        self._blackout_active = False

        for universe_id, values in self._pre_blackout_values.items():
            universe = self.get_universe(universe_id)
            if universe:
                universe.set_all(values)
                self._send_universe(universe_id)

        self._pre_blackout_values = {}
        self._notify_blackout(False)

    def is_blackout_active(self) -> bool:
        """Check if blackout is active."""
        return self._blackout_active

    def _send_universe(self, universe_id: int) -> None:
        """Send universe data to all configured outputs."""
        universe = self.get_universe(universe_id)
        if not universe:
            return

        universe.active = True

        outputs = self.outputs.get(universe_id, [])
        active_count = 0
        for output in outputs:
            if output and output.running:
                # Schedule async send in the event loop
                asyncio.create_task(output.send_dmx(universe.channels))
                active_count += 1

        if active_count == 0:
            logger.debug(f"Universe {universe_id}: No active outputs")

    def register_callback(self, callback: Callable) -> None:
        """Register a callback for value changes."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, universe_id: int, channel: int, value: int, source: str = "local") -> None:
        """Notify all callbacks of a value change."""
        for callback in self._callbacks:
            try:
                callback("channel_change", {
                    "universe_id": universe_id,
                    "channel": channel,
                    "value": value,
                    "source": source
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _notify_blackout(self, active: bool) -> None:
        """Notify callbacks of blackout state change."""
        for callback in self._callbacks:
            try:
                callback("blackout", {"active": active})
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def get_output_status(self, universe_id: int) -> Optional[List[dict]]:
        """Get status of all outputs for a universe."""
        outputs = self.outputs.get(universe_id, [])
        configs = self._output_configs.get(universe_id, [])

        if not outputs:
            return None

        result = []
        for i, output in enumerate(outputs):
            status = output.get_status()
            # Add the database ID if available
            if i < len(configs):
                status["id"] = configs[i].get("id")
                status["enabled"] = configs[i].get("enabled", True)
            result.append(status)

        return result

    def get_output_configs(self, universe_id: int) -> List[dict]:
        """Get output configurations for a universe."""
        return self._output_configs.get(universe_id, [])

    def get_protocols(self) -> List[dict]:
        """Get list of available protocols."""
        return get_available_protocols()

    # =========================================================================
    # Groups/Masters methods
    # =========================================================================

    def _apply_group(self, group_id: int, master_value: int) -> None:
        """Apply master value to all group members using HTP merge.

        When multiple groups control the same channel, HTP (Highest Takes Precedence)
        ensures smooth crossfades instead of flickering.
        """
        group = self._groups.get(group_id)
        if not group or not group.get("enabled", True):
            return

        affected_channels = []  # [(universe_id, channel), ...]

        for member in group.get("members", []):
            member_universe_id = member["universe_id"]
            member_channel = member["channel"]

            if group["mode"] == "follow":
                output_value = master_value
            else:  # proportional
                base_value = member.get("base_value", 255)
                output_value = round((base_value * master_value) / 255)

            # Store this group's contribution for HTP merge
            ch_key = (member_universe_id, member_channel)
            if ch_key not in self._group_contributions:
                self._group_contributions[ch_key] = {}
            self._group_contributions[ch_key][group_id] = output_value

            affected_channels.append(ch_key)

        # Apply HTP for all affected channels
        affected_universes = set()
        for ch_key in affected_channels:
            universe_id, channel = ch_key
            contributions = self._group_contributions.get(ch_key, {})

            # HTP: use highest value from all groups
            htp_value = max(contributions.values()) if contributions else 0

            universe = self.get_universe(universe_id)
            if universe:
                universe.set_channel(channel, htp_value)
                affected_universes.add(universe_id)
                # Track source as "group"
                self._channel_sources.setdefault(universe_id, {})[channel] = "group"

        # Send all affected universes and notify callbacks
        for uid in affected_universes:
            self._send_universe(uid)
            # Notify callbacks for each affected channel in this universe
            for universe_id, channel in affected_channels:
                if universe_id == uid:
                    universe = self.get_universe(uid)
                    if universe:
                        value = universe.get_channel(channel)
                        self._notify_callbacks(uid, channel, value, "group")

    def load_groups(self, groups: List[dict]) -> None:
        """Load group configurations from database.

        Args:
            groups: List of group dicts with keys: id, name, mode, master_universe,
                    master_channel, master_value, enabled, members (list of member dicts)
        """
        self._groups.clear()
        self._master_to_groups.clear()

        for group in groups:
            group_id = group["id"]
            self._groups[group_id] = group

            # Build master -> groups lookup (only for groups with physical master)
            if group.get("master_universe") and group.get("master_channel"):
                master_key = (group["master_universe"], group["master_channel"])
                if master_key not in self._master_to_groups:
                    self._master_to_groups[master_key] = []
                self._master_to_groups[master_key].append(group_id)

        logger.info(f"Loaded {len(self._groups)} groups")

    def apply_group_direct(self, group_id: int, master_value: int) -> None:
        """Apply master value to group members directly (for virtual masters).

        This bypasses the set_channel -> group trigger flow and applies the
        master value directly to all member channels.
        """
        # Store current master value for effective base calculations
        if group_id in self._groups:
            self._groups[group_id]["master_value"] = master_value
        self._apply_group(group_id, master_value)

    def add_group(self, group: dict) -> None:
        """Add a single group configuration."""
        group_id = group["id"]
        self._groups[group_id] = group

        # Only add master mapping if group has physical master
        if group.get("master_universe") and group.get("master_channel"):
            master_key = (group["master_universe"], group["master_channel"])
            if master_key not in self._master_to_groups:
                self._master_to_groups[master_key] = []
            if group_id not in self._master_to_groups[master_key]:
                self._master_to_groups[master_key].append(group_id)

        logger.info(f"Added group {group_id}: {group['name']}")

    def remove_group(self, group_id: int) -> None:
        """Remove a group configuration."""
        group = self._groups.pop(group_id, None)
        if group:
            # Clear this group's contributions and reapply HTP
            affected_universes = set()
            for ch_key in list(self._group_contributions.keys()):
                if group_id in self._group_contributions[ch_key]:
                    del self._group_contributions[ch_key][group_id]
                    universe_id, channel = ch_key
                    # Reapply HTP for this channel
                    if self._group_contributions[ch_key]:
                        htp_value = max(self._group_contributions[ch_key].values())
                    else:
                        htp_value = 0  # No groups controlling this channel
                        del self._group_contributions[ch_key]
                    universe = self.get_universe(universe_id)
                    if universe:
                        universe.set_channel(channel, htp_value)
                        affected_universes.add(universe_id)

            # Send updates for affected universes
            for uid in affected_universes:
                self._send_universe(uid)

            # Only remove from master mapping if group had physical master
            if group.get("master_universe") and group.get("master_channel"):
                master_key = (group["master_universe"], group["master_channel"])
                if master_key in self._master_to_groups:
                    if group_id in self._master_to_groups[master_key]:
                        self._master_to_groups[master_key].remove(group_id)
                    if not self._master_to_groups[master_key]:
                        del self._master_to_groups[master_key]
            logger.info(f"Removed group {group_id}")

    def update_group(self, group: dict) -> None:
        """Update a group configuration."""
        group_id = group["id"]

        # Remove old master mapping if exists (only if group had physical master)
        old_group = self._groups.get(group_id)
        if old_group and old_group.get("master_universe") and old_group.get("master_channel"):
            old_master_key = (old_group["master_universe"], old_group["master_channel"])
            if old_master_key in self._master_to_groups:
                if group_id in self._master_to_groups[old_master_key]:
                    self._master_to_groups[old_master_key].remove(group_id)
                if not self._master_to_groups[old_master_key]:
                    del self._master_to_groups[old_master_key]

        # Add new group config
        self._groups[group_id] = group

        # Add new master mapping (only if group has physical master)
        if group.get("master_universe") and group.get("master_channel"):
            master_key = (group["master_universe"], group["master_channel"])
            if master_key not in self._master_to_groups:
                self._master_to_groups[master_key] = []
            if group_id not in self._master_to_groups[master_key]:
                self._master_to_groups[master_key].append(group_id)

        logger.info(f"Updated group {group_id}: {group['name']}")

    def clear_group_contribution(self, group_id: int, universe_id: int, channel: int) -> None:
        """Clear a group's contribution for a specific channel and reapply HTP.

        Called when a member is updated or removed.
        """
        ch_key = (universe_id, channel)
        if ch_key in self._group_contributions and group_id in self._group_contributions[ch_key]:
            del self._group_contributions[ch_key][group_id]
            # Reapply HTP for this channel
            if self._group_contributions[ch_key]:
                htp_value = max(self._group_contributions[ch_key].values())
            else:
                htp_value = 0
                del self._group_contributions[ch_key]
            universe = self.get_universe(universe_id)
            if universe:
                universe.set_channel(channel, htp_value)
                self._send_universe(universe_id)

    def get_groups(self) -> Dict[int, dict]:
        """Get all loaded groups."""
        return self._groups.copy()

    def get_group(self, group_id: int) -> Optional[dict]:
        """Get a specific group by ID."""
        return self._groups.get(group_id)

    def is_channel_group_controlled(self, universe_id: int, channel: int) -> bool:
        """Check if a channel is controlled by a group (is a member)."""
        for group in self._groups.values():
            for member in group.get("members", []):
                if member["universe_id"] == universe_id and member["channel"] == channel:
                    return True
        return False

    def get_channel_group_info(self, universe_id: int, channel: int) -> Optional[dict]:
        """Get group info for a channel if it's a group member."""
        for group in self._groups.values():
            for member in group.get("members", []):
                if member["universe_id"] == universe_id and member["channel"] == channel:
                    return {
                        "group_id": group["id"],
                        "group_name": group["name"],
                        "mode": group["mode"],
                        "master_universe": group["master_universe"],
                        "master_channel": group["master_channel"],
                        "base_value": member.get("base_value", 255)
                    }
        return None


# Global DMX interface instance
dmx_interface = DMXInterface()
