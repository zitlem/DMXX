"""
DMX Interface for sending DMX data via Art-Net, sACN, or mock output.
Also handles DMX inputs, passthrough routing, and MIDI integration.
"""
import asyncio
import time
from typing import Dict, List, Optional, Callable, Any, Set
import logging

from .dmx_outputs import DMXOutput, create_output, get_available_protocols
from .dmx_inputs import DMXInput, create_input, get_available_input_protocols
from .websocket_manager import manager as ws_manager
from .midi_handler import MIDIHandler, midi_to_dmx, dmx_to_midi

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
        self._local_values: Dict[int, List[int]] = {}  # Fader/local values per universe (for HTP merge)
        self._last_applied_input: Dict[int, List[int]] = {}  # Last input values applied to output (for LTP)
        self._input_jitter_threshold = 2  # Ignore input changes <= this threshold (for LTP)
        self._passthrough_config: Dict[int, dict] = {}  # Passthrough settings per universe
        self._running = False
        self._callbacks: List[Callable] = []
        self._blackout_active = False
        self._pre_blackout_values: Dict[int, List[int]] = {}
        self._input_bypass_active = False  # Global input bypass (temporary)
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
        # Grand Master control
        self._global_grandmaster: int = 255  # Global GM (0-255)
        self._universe_grandmasters: Dict[int, int] = {}  # Per-universe GM {universe_id: 0-255}
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
        # MIDI integration
        self._midi_handler: Optional[MIDIHandler] = None
        self._midi_output_enabled = False  # Whether to send DMX changes to MIDI
        self._last_midi_output_values: Dict[tuple, int] = {}  # {(universe, channel): last_sent_value} for change detection
        self._scene_recall_callback: Optional[Callable] = None  # Callback for scene recall (MIDI note -> scene)
        # New MIDI input integration (CC -> Input Channel mappings)
        self._midi_cc_mappings: List[dict] = []  # [{cc_number, midi_channel, input_channel, enabled}, ...]
        self._midi_triggers: List[dict] = []  # [{note, midi_channel, action, target_id, enabled}, ...]
        self._midi_input_values: List[int] = [0] * 512  # Virtual MIDI input universe
        self._midi_input_enabled: bool = False  # Whether MIDI input is integrated with I/O
        self._active_scene_id: Optional[int] = None  # Currently active scene for MIDI feedback
        # Throttle MIDI input broadcasts
        self._last_midi_input_broadcast: float = 0
        self._midi_input_broadcast_interval: float = 0.05  # 50ms = 20 updates/sec
        # Park channels - lock channels to fixed values (highest priority)
        self._parked_channels: Dict[int, Dict[int, int]] = {}  # {universe_id: {channel: value}}
        # Highlight/Solo mode - temporary override for fixture identification
        self._highlight_active: bool = False
        self._highlighted_channels: Dict[int, Set[int]] = {}  # {universe_id: set of channels}
        self._highlight_dim_level: int = 0  # Value for non-highlighted channels (default 0)

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
        # Get channel range from config if provided
        channel_start = config.get("channel_start", 1) if config else 1
        channel_end = config.get("channel_end", 512) if config else 512
        self._passthrough_config[universe_id] = {
            "passthrough_mode": pt_mode,
            "mode": passthrough_mode,  # This is the HTP/LTP merge mode
            "enabled": passthrough_enabled,
            "show_ui": passthrough_show_ui,
            "channel_start": channel_start,
            "channel_end": channel_end
        }
        logger.info(f"Universe {universe_id}: Input passthrough_mode={pt_mode}, merge={passthrough_mode}, channel_range={channel_start}-{channel_end}")

        # Create and start input if type is not "none"
        if input_type and input_type.lower() != "none":
            input_handler = create_input(universe_id, input_type, config, self._on_input_received)
            if input_handler:
                success = await input_handler.start()
                if success:
                    self.inputs[universe_id] = input_handler
                    self._input_values[universe_id] = [0] * 512

                    # Reset local values for input-controlled channels so first input takes priority
                    # (Same fix as bypass OFF - HTP merge needs local=0 for input to win)
                    if pt_mode in ("faders_output", "output_only"):
                        if universe_id in self._local_values:
                            for i in range(channel_start - 1, channel_end):
                                self._local_values[universe_id][i] = 0
                        # Clear throttles for immediate updates
                        self._last_input_broadcast[universe_id] = 0

                    # Clear group caches so groups trigger properly on first input
                    self._last_group_values.clear()
                    self._last_group_broadcast.clear()

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

        # Check if input bypass is active - skip all output and fader UI updates
        if self._input_bypass_active:
            # Bypass active - input values can still be seen in I/O page input monitor
            now = time.time()
            last_broadcast = self._last_input_broadcast.get(universe_id, 0)
            if now - last_broadcast >= self._input_broadcast_interval:
                self._last_input_broadcast[universe_id] = now
                # Only notify input_received for I/O monitor, NOT input_to_ui for faders
                self._notify_input_received(universe_id, channels)
            return  # Skip applying to output and fader display

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
        """Apply input values to the universe based on merge mode.

        LTP behavior: Only apply input when it actually changes beyond jitter threshold.
        This allows UI faders to override when input is stable.

        HTP behavior: Highest value wins between local fader and input.

        Only channels within the configured input range are affected.
        Channels outside the range keep their local (fader) values.
        """
        universe = self.get_universe(universe_id)
        if not universe or self._blackout_active:
            return

        # Get channel range from passthrough config
        config = self._passthrough_config.get(universe_id, {})
        channel_start = config.get("channel_start", 1)
        channel_end = config.get("channel_end", 512)

        if mode == "ltp":
            # Latest Takes Precedence - but only apply input that actually changed
            # This allows UI to override when input is stable (no change, ignore jitter)
            last = self._last_applied_input.get(universe_id, [0] * 512)
            current = universe.get_all()
            # Only apply to channels within the input range
            for i in range(channel_start - 1, channel_end):  # 0-indexed
                # Always apply if input is 0 (allow turning off lights)
                # Otherwise only apply if change exceeds jitter threshold
                if input_channels[i] == 0 or abs(input_channels[i] - last[i]) > self._input_jitter_threshold:
                    current[i] = input_channels[i]
                # else: input is stable, keep current value (allows UI override)
            universe.set_all(current)
            self._last_applied_input[universe_id] = input_channels.copy()
        else:
            # HTP - Highest Takes Precedence: max(local, input) always wins
            # Only apply to channels within the input range
            local = self._local_values.get(universe_id, [0] * 512)
            merged = local.copy()  # Start with local values
            for i in range(channel_start - 1, channel_end):  # 0-indexed
                merged[i] = max(local[i], input_channels[i])
            universe.set_all(merged)

        self._send_universe(universe_id)

        # Check if any channels are group masters and trigger them
        # Use raw input values (not HTP-merged) so groups respond directly to input=0
        # Only check channels within the input range
        range_channels = set(range(channel_start - 1, channel_end))
        self._check_group_masters_for_input(universe_id, range_channels, input_channels)

    def _apply_mapped_passthrough(self, src_universe_id: int, input_channels: List[int], mode: str) -> None:
        """Apply input values with channel mapping to destination universes.

        Key behavior:
        - Mapped source channels route to their destinations only (all 512 processed)
        - Unmapped channels pass through 1:1 ONLY if within input range (passthrough mode)
        - Channels outside input range are left for manual control
        - Mapped destination channels are protected from unmapped passthrough
        """
        if self._blackout_active:
            return

        # Get input channel range - used for unmapped passthrough only
        config = self._passthrough_config.get(src_universe_id, {})
        channel_start = config.get("channel_start", 1)
        channel_end = config.get("channel_end", 512)

        # Build per-destination-universe value arrays
        dst_values: Dict[int, List[int]] = {}  # {dst_universe: [512 values]}
        dst_has_value: Dict[int, set] = {}  # Track which output channels have values to apply

        # Pre-calculate all mapped destinations to protect them from passthrough
        # Only channel targets need protection - virtual targets don't occupy channel space
        mapped_destinations: Dict[int, set] = {}  # {dst_universe: set of dst_channel indices}
        for src_ch in range(1, 513):
            destinations = self._channel_map.get((src_universe_id, src_ch), [])
            for dst_info in destinations:
                if dst_info.get("target_type", "channel") == "channel":
                    dst_universe = dst_info.get("universe")
                    dst_ch = dst_info.get("channel")
                    if dst_universe is not None and dst_ch is not None:
                        if dst_universe not in mapped_destinations:
                            mapped_destinations[dst_universe] = set()
                        mapped_destinations[dst_universe].add(dst_ch - 1)

        # Process all 512 input channels for explicit mappings
        for src_ch in range(1, 513):
            value = input_channels[src_ch - 1]
            destinations = self._channel_map.get((src_universe_id, src_ch), [])

            if destinations:
                # Mapped channel - apply to all destinations including 0
                # For explicit mappings, always apply the input value so lights turn off
                for dst_info in destinations:
                    target_type = dst_info.get("target_type", "channel")

                    if target_type == "universe_master":
                        # Apply to universe grandmaster
                        target_uid = dst_info.get("target_universe_id")
                        if target_uid is not None:
                            self.set_universe_grandmaster(target_uid, value)
                    elif target_type == "global_master":
                        # Apply to global grandmaster
                        self.set_global_grandmaster(value)
                    else:
                        # Normal channel mapping
                        dst_universe = dst_info.get("universe")
                        dst_ch = dst_info.get("channel")
                        if dst_universe is not None and dst_ch is not None:
                            if dst_universe not in dst_values:
                                dst_values[dst_universe] = [0] * 512
                                dst_has_value[dst_universe] = set()
                            dst_values[dst_universe][dst_ch - 1] = value
                            dst_has_value[dst_universe].add(dst_ch - 1)
            elif self._unmapped_behavior == "passthrough":
                # Unmapped channel with passthrough - pass to same channel 1:1
                # BUT only for channels within the input range (don't pass 0s from unused channels)
                # AND skip if this output position is a mapped destination
                if src_ch < channel_start or src_ch > channel_end:
                    continue  # Outside input range - leave for manual control
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

        LTP behavior: Only apply input when it actually changes beyond jitter threshold.
        HTP behavior: Highest value wins between local fader and input.
        """
        universe = self.get_universe(universe_id)
        if not universe:
            logger.warning(f"_apply_selective_values: universe {universe_id} not found!")
            return

        current = universe.get_all()
        local = self._local_values.get(universe_id, [0] * 512)
        last = self._last_applied_input.get(universe_id, [0] * 512)

        for ch_idx in active_channels:
            input_val = input_channels[ch_idx]
            if mode == "ltp":
                # Always apply if input is 0 (allow turning off lights)
                # Otherwise only apply if change exceeds jitter threshold
                if input_val == 0 or abs(input_val - last[ch_idx]) > self._input_jitter_threshold:
                    current[ch_idx] = input_val
                # else: input is stable, keep current value (allows UI override)
            else:  # HTP - Highest Takes Precedence: max(local, input) always wins
                current[ch_idx] = max(local[ch_idx], input_val)

        # Update last applied input for LTP jitter detection
        if mode == "ltp":
            if universe_id not in self._last_applied_input:
                self._last_applied_input[universe_id] = [0] * 512
            for ch_idx in active_channels:
                self._last_applied_input[universe_id][ch_idx] = input_channels[ch_idx]

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
            asyncio.create_task(ws_manager.broadcast_group_value_changed(group_id, value, source="input"))

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
            mappings: List of mapping dicts with keys:
                - src_universe, src_channel: Source channel
                - dst_universe, dst_channel: For channel targets
                - dst_target_type: "channel", "universe_master", or "global_master"
                - dst_target_universe_id: For universe_master targets
            unmapped_behavior: "passthrough" (unmapped channels pass 1:1) or "ignore" (unmapped are zeroed)
        """
        self._channel_map.clear()
        self._reverse_map.clear()
        self._unmapped_behavior = unmapped_behavior

        for m in mappings:
            src = (m["src_universe"], m["src_channel"])
            target_type = m.get("dst_target_type", "channel")

            # Store full destination info as a dict
            dst_info = {
                "target_type": target_type,
                "universe": m.get("dst_universe"),
                "channel": m.get("dst_channel"),
                "target_universe_id": m.get("dst_target_universe_id")
            }

            if src not in self._channel_map:
                self._channel_map[src] = []
            self._channel_map[src].append(dst_info)

            # For channel targets, also update reverse map for UI display
            if target_type == "channel" and dst_info["universe"] is not None and dst_info["channel"] is not None:
                dst = (dst_info["universe"], dst_info["channel"])
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

    def get_input_controlled_channels(self, universe_id: int) -> set:
        """Get set of channels in this universe that are controlled by input.

        This considers:
        - Direct passthrough (input range applies to same universe, no mapping)
        - Mapped passthrough (destination channels from any input universe)
        - Unmapped passthrough (channels within input range that pass through 1:1)

        Returns a set of 1-indexed channel numbers.
        """
        controlled = set()

        # Check if this universe has direct input (non-mapped passthrough)
        if universe_id in self.inputs and not self._mapping_enabled:
            config = self._passthrough_config.get(universe_id, {})
            passthrough_mode = config.get("passthrough_mode", "off")
            if passthrough_mode in ("faders_output", "output_only"):
                channel_start = config.get("channel_start", 1)
                channel_end = config.get("channel_end", 512)
                controlled.update(range(channel_start, channel_end + 1))

        # Check if any input universe maps to this universe (mapped passthrough)
        if self._mapping_enabled:
            for src_universe_id in self.inputs:
                config = self._passthrough_config.get(src_universe_id, {})
                passthrough_mode = config.get("passthrough_mode", "off")
                if passthrough_mode in ("faders_output", "output_only"):
                    channel_start = config.get("channel_start", 1)
                    channel_end = config.get("channel_end", 512)

                    # Find all mappings from this input universe to the target universe
                    for (src_u, src_ch), destinations in self._channel_map.items():
                        if src_u == src_universe_id:
                            for dst_info in destinations:
                                if dst_info.get("target_type", "channel") == "channel":
                                    dst_u = dst_info.get("universe")
                                    dst_ch = dst_info.get("channel")
                                    if dst_u == universe_id and dst_ch is not None:
                                        controlled.add(dst_ch)

                    # Also check unmapped passthrough (1:1 within input range)
                    if self._unmapped_behavior == "passthrough" and src_universe_id == universe_id:
                        # Channels within input range pass through 1:1 to same universe
                        # But exclude:
                        # - Channels that are mapped destinations (already handled above)
                        # - Channels whose INPUT source was mapped elsewhere (source channel is remapped)
                        mapped_dests = set()
                        mapped_sources = set()
                        for (src_u, src_ch), destinations in self._channel_map.items():
                            if src_u == src_universe_id:
                                mapped_sources.add(src_ch)  # This input channel is remapped
                            for dst_info in destinations:
                                if dst_info.get("target_type", "channel") == "channel":
                                    dst_u = dst_info.get("universe")
                                    dst_ch = dst_info.get("channel")
                                    if dst_u == universe_id and dst_ch is not None:
                                        mapped_dests.add(dst_ch)
                        for ch in range(channel_start, channel_end + 1):
                            # Only passthrough if: not a mapped dest AND input source not remapped
                            if ch not in mapped_dests and ch not in mapped_sources:
                                controlled.add(ch)

        return controlled

    def is_color_mixer_member(self, universe_id: int, channel: int) -> bool:
        """Check if a channel is a member of any color_mixer group.

        Color mixer member channels should be allowed to bypass input control
        since they're controlled by the color picker, not input passthrough.
        """
        for group in self._groups.values():
            if group.get("mode") != "color_mixer":
                continue
            for member in group.get("members", []):
                if (member.get("target_type") == "channel" and
                    member.get("universe_id") == universe_id and
                    member.get("channel") == channel):
                    return True
        return False

    def get_input_value_for_channel(self, universe_id: int, channel: int) -> Optional[int]:
        """Get the input value that controls a specific channel.

        For non-mapped: returns input value for same channel
        For mapped: returns input value from the source channel that maps here
        For unmapped passthrough: returns input value for same channel (1:1)

        Returns None if channel is not input-controlled.
        """
        # Check direct input (non-mapped)
        if universe_id in self.inputs and not self._mapping_enabled:
            config = self._passthrough_config.get(universe_id, {})
            passthrough_mode = config.get("passthrough_mode", "off")
            if passthrough_mode in ("faders_output", "output_only"):
                channel_start = config.get("channel_start", 1)
                channel_end = config.get("channel_end", 512)
                if channel_start <= channel <= channel_end:
                    input_vals = self._input_values.get(universe_id, [])
                    if input_vals and channel - 1 < len(input_vals):
                        return input_vals[channel - 1]

        # Check mapped input
        if self._mapping_enabled:
            # First check explicit mapping
            source = self._reverse_map.get((universe_id, channel))
            if source:
                src_universe, src_channel = source
                if src_universe in self.inputs:
                    config = self._passthrough_config.get(src_universe, {})
                    passthrough_mode = config.get("passthrough_mode", "off")
                    if passthrough_mode in ("faders_output", "output_only"):
                        input_vals = self._input_values.get(src_universe, [])
                        if input_vals and src_channel - 1 < len(input_vals):
                            return input_vals[src_channel - 1]

            # Check unmapped passthrough (1:1 within input range, same universe)
            if self._unmapped_behavior == "passthrough" and universe_id in self.inputs:
                config = self._passthrough_config.get(universe_id, {})
                passthrough_mode = config.get("passthrough_mode", "off")
                if passthrough_mode in ("faders_output", "output_only"):
                    channel_start = config.get("channel_start", 1)
                    channel_end = config.get("channel_end", 512)
                    # Check if channel is within input range and:
                    # - NOT a mapped destination
                    # - Input source for this channel was NOT remapped elsewhere
                    if channel_start <= channel <= channel_end:
                        is_mapped_dest = self._reverse_map.get((universe_id, channel)) is not None
                        is_source_remapped = (universe_id, channel) in self._channel_map
                        if not is_mapped_dest and not is_source_remapped:
                            input_vals = self._input_values.get(universe_id, [])
                            if input_vals and channel - 1 < len(input_vals):
                                return input_vals[channel - 1]

        return None

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
        # Get channel range from passthrough config
        config = self._passthrough_config.get(universe_id, {})
        channel_start = config.get("channel_start", 1)
        channel_end = config.get("channel_end", 512)

        # Only update _local_values for channels within the input range
        # This allows channels outside the range to be freely controlled
        if universe_id not in self._local_values:
            self._local_values[universe_id] = [0] * 512
        for i in range(channel_start - 1, channel_end):  # 0-indexed
            if i < len(channels):
                self._local_values[universe_id][i] = channels[i]

        # Mark only channels in range as coming from input source
        universe_sources = self._channel_sources.setdefault(universe_id, {})
        for i in range(channel_start - 1, channel_end):
            universe_sources[i + 1] = "input"

        # Send only channels within range to UI
        # Build a modified values array: input values for channels in range, -1 for others (to skip)
        ui_values = [-1] * 512  # -1 means "don't update this channel"
        for i in range(channel_start - 1, channel_end):
            if i < len(channels):
                ui_values[i] = channels[i]

        for callback in self._callbacks:
            try:
                callback("input_to_ui", {
                    "universe_id": universe_id,
                    "values": ui_values,
                    "channel_start": channel_start,
                    "channel_end": channel_end
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _notify_mapped_input_to_ui(self, src_universe_id: int, channels: List[int]) -> None:
        """Notify callbacks to update UI with mapped input values.

        Only updates faders for mapped destination channels.
        Non-mapped channels use -1 sentinel to indicate "don't update".
        """
        # Get input channel range for unmapped passthrough
        config = self._passthrough_config.get(src_universe_id, {})
        channel_start = config.get("channel_start", 1)
        channel_end = config.get("channel_end", 512)

        # Build per-destination-universe notifications
        # Use -1 as sentinel for "don't update this channel"
        dst_notifications: Dict[int, List[int]] = {}
        dst_controlled_channels: Dict[int, set] = {}  # Track which channels are actually controlled

        # Pre-calculate mapped destinations to protect them from passthrough overwrite
        # Only channel targets - virtual targets don't affect fader display
        mapped_destinations: Dict[int, set] = {}
        for src_ch in range(1, 513):
            destinations = self._channel_map.get((src_universe_id, src_ch), [])
            for dst_info in destinations:
                if dst_info.get("target_type", "channel") == "channel":
                    dst_universe = dst_info.get("universe")
                    dst_ch = dst_info.get("channel")
                    if dst_universe is not None and dst_ch is not None:
                        if dst_universe not in mapped_destinations:
                            mapped_destinations[dst_universe] = set()
                        mapped_destinations[dst_universe].add(dst_ch - 1)

        for src_ch in range(1, 513):
            val = channels[src_ch - 1]
            destinations = self._channel_map.get((src_universe_id, src_ch), [])

            if destinations:
                # Send to mapped destination faders (only channel targets)
                for dst_info in destinations:
                    if dst_info.get("target_type", "channel") == "channel":
                        dst_universe = dst_info.get("universe")
                        dst_ch = dst_info.get("channel")
                        if dst_universe is not None and dst_ch is not None:
                            if dst_universe not in dst_notifications:
                                dst_notifications[dst_universe] = [-1] * 512  # -1 = don't update
                                dst_controlled_channels[dst_universe] = set()
                            dst_notifications[dst_universe][dst_ch - 1] = val
                            dst_controlled_channels[dst_universe].add(dst_ch)
            elif self._unmapped_behavior == "passthrough":
                # Unmapped channel with passthrough - show on original fader
                # BUT only within input channel range AND skip if mapped destination
                if src_ch < channel_start or src_ch > channel_end:
                    continue  # Outside input range - don't update this fader
                dst_ch_idx = src_ch - 1
                if dst_ch_idx not in mapped_destinations.get(src_universe_id, set()):
                    if src_universe_id not in dst_notifications:
                        dst_notifications[src_universe_id] = [-1] * 512  # -1 = don't update
                        dst_controlled_channels[src_universe_id] = set()
                    dst_notifications[src_universe_id][dst_ch_idx] = val
                    dst_controlled_channels[src_universe_id].add(src_ch)

        # Send notifications for each destination universe
        for dst_universe_id, values in dst_notifications.items():
            controlled = dst_controlled_channels.get(dst_universe_id, set())

            # Only update _local_values for controlled channels (not all 512)
            if dst_universe_id not in self._local_values:
                self._local_values[dst_universe_id] = [0] * 512
            for ch in controlled:
                self._local_values[dst_universe_id][ch - 1] = values[ch - 1]

            # Only mark controlled channels as coming from input source
            universe_sources = self._channel_sources.setdefault(dst_universe_id, {})
            for ch in controlled:
                universe_sources[ch] = "input"

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

        # Skip if channel is parked (parked channels ignore all input)
        if self.is_channel_parked(universe_id, channel):
            # Notify with parked value so frontend fader snaps back
            parked_value = self._parked_channels[universe_id][channel]
            self._notify_callbacks(universe_id, channel, parked_value, "park_reject")
            return

        universe = self.get_universe(universe_id)
        if universe:
            # Track local fader values for HTP merge (local or user sources)
            if source == "local" or source.startswith("user_"):
                if universe_id not in self._local_values:
                    self._local_values[universe_id] = [0] * 512
                self._local_values[universe_id][channel - 1] = value

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
        if not universe:
            return

        # Notify for parked channels (snap fader back) then filter them out
        parked_in_request = {}
        for ch in list(values.keys()):
            if self.is_channel_parked(universe_id, ch):
                parked_in_request[ch] = self._parked_channels[universe_id][ch]
                del values[ch]

        # Send park_reject for each parked channel so faders snap back
        for ch, parked_val in parked_in_request.items():
            self._notify_callbacks(universe_id, ch, parked_val, "park_reject")

        if not values:
            return

        # Separate channels into group members and regular channels
        regular_channels = {}
        groups_to_update = {}  # {group_id: (group, new_master, member_channel)}

        is_user_source = source == "local" or source.startswith("user_")

        for channel, value in values.items():
            if is_user_source:
                # Check if this channel is a group member
                groups = self._get_groups_containing_member(universe_id, channel)

                if len(groups) == 1:
                    group = groups[0]

                    # Check if group master is input-controlled (and bypass OFF)
                    if group.get("master_universe") and group.get("master_channel"):
                        if not self._input_bypass_active:
                            controlled = self.get_input_controlled_channels(group["master_universe"])
                            if group["master_channel"] in controlled:
                                # Send current (group-controlled) value back to snap the fader
                                # Use "group_reject" so frontend knows to cancel the drag
                                current_value = universe.get_channel(channel)
                                self._notify_callbacks(universe_id, channel, current_value, "group_reject")
                                continue

                    # Not input-controlled: reverse-calculate master value
                    if group["mode"] == "follow":
                        new_master = value
                    else:  # proportional
                        base_value = self._get_member_base_value(group, universe_id, channel)
                        new_master = min(255, round((value * 255) / base_value)) if base_value > 0 else value

                    # Track this group for update (use highest master if multiple members in same batch)
                    group_id = group["id"]
                    if group_id not in groups_to_update or new_master > groups_to_update[group_id][1]:
                        groups_to_update[group_id] = (group, new_master, channel)
                    continue

                elif len(groups) > 1:
                    # Multi-group: channel is controlled by HTP of multiple groups
                    # Can't reverse-calculate which group to update, so snap back to current value
                    current_value = universe.get_channel(channel)
                    self._notify_callbacks(universe_id, channel, current_value, "group_reject")
                    continue

            # Regular channel (not a group member)
            regular_channels[channel] = value

        # Process regular channels normally
        if regular_channels:
            if is_user_source:
                if universe_id not in self._local_values:
                    self._local_values[universe_id] = [0] * 512
                for channel, value in regular_channels.items():
                    self._local_values[universe_id][channel - 1] = value

            for channel, value in regular_channels.items():
                if self._blackout_active:
                    self._pre_blackout_values.setdefault(universe_id, universe.get_all())
                    self._pre_blackout_values[universe_id][channel - 1] = value
                else:
                    universe.set_channel(channel, value)
                    self._channel_sources.setdefault(universe_id, {})[channel] = source

            if not self._blackout_active:
                self._send_universe(universe_id)
                for channel, value in regular_channels.items():
                    self._notify_callbacks(universe_id, channel, value, source)

                # Check if any regular channels are group masters and trigger them
                for channel, value in regular_channels.items():
                    group_ids = self._master_to_groups.get((universe_id, channel), [])
                    for group_id in group_ids:
                        if group_id in self._groups:
                            self._groups[group_id]["master_value"] = value
                        self._apply_group(group_id, value)
                        # Broadcast so Groups.vue updates
                        asyncio.create_task(ws_manager.broadcast_group_value_changed(group_id, value))

        # Process group updates
        for group_id, (group, new_master, _) in groups_to_update.items():
            group["master_value"] = new_master
            self._apply_group(group_id, new_master)

            # Broadcast group value change so Groups.vue and other faders update
            asyncio.create_task(ws_manager.broadcast_group_value_changed(group_id, new_master))

            # If physical master, update that channel too
            if group.get("master_universe") and group.get("master_channel"):
                master_universe = self.get_universe(group["master_universe"])
                if master_universe and not self._blackout_active:
                    master_universe.set_channel(group["master_channel"], new_master)
                    self._send_universe(group["master_universe"])
                    self._channel_sources.setdefault(group["master_universe"], {})[group["master_channel"]] = "group_reverse"
                    self._notify_callbacks(group["master_universe"], group["master_channel"], new_master, "group_reverse")

    def set_channels_silent(self, universe_id: int, values: Dict[int, int], source: str = "local") -> None:
        """Set multiple channel values without triggering callbacks (for fades)."""
        universe = self.get_universe(universe_id)
        if universe:
            # Filter out parked channels (they ignore all input)
            values = {ch: val for ch, val in values.items()
                      if not self.is_channel_parked(universe_id, ch)}
            if not values:
                return

            # Track local fader values for HTP merge (local or user sources)
            if source == "local" or source.startswith("user_"):
                if universe_id not in self._local_values:
                    self._local_values[universe_id] = [0] * 512
                for channel, value in values.items():
                    self._local_values[universe_id][channel - 1] = value

            for channel, value in values.items():
                if self._blackout_active:
                    self._pre_blackout_values.setdefault(universe_id, universe.get_all())
                    self._pre_blackout_values[universe_id][channel - 1] = value
                else:
                    universe.set_channel(channel, value)
                    self._channel_sources.setdefault(universe_id, {})[channel] = source

            if not self._blackout_active:
                self._send_universe(universe_id)
                # NO callbacks - caller will handle bulk notification

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

    def get_scaled_values(self, universe_id: int) -> List[int]:
        """Get all channel values with overrides and grandmaster scaling applied (actual output)."""
        values = self.get_all_values(universe_id)
        values_with_overrides = self._apply_channel_overrides(values, universe_id)
        return self._apply_grandmaster_scaling(values_with_overrides, universe_id)

    def get_grandmaster_info(self) -> dict:
        """Get current grandmaster values."""
        return {
            "global": self._global_grandmaster,
            "universes": dict(self._universe_grandmasters)
        }

    def get_local_values(self, universe_id: int) -> List[int]:
        """Get local fader values (before merge with input).

        Use this instead of get_all_values() when you want the values
        the user set via faders, not the merged output values.
        """
        return self._local_values.get(universe_id, [0] * 512).copy()

    def blackout(self) -> None:
        """Activate global blackout."""
        self._blackout_active = True
        self._pre_blackout_values = {}

        for universe_id, universe in self.universes.items():
            self._pre_blackout_values[universe_id] = universe.get_all()
            universe.blackout()
            self._send_universe(universe_id)

        self._notify_blackout(True)
        self._send_midi_blackout_feedback(True)

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
        self._send_midi_blackout_feedback(False)

    def is_blackout_active(self) -> bool:
        """Check if blackout is active."""
        return self._blackout_active

    def set_input_bypass(self, bypass: bool) -> None:
        """Enable/disable input bypass globally.

        When enabled, DMX input is received but not applied to output.
        UI display may still show input values depending on passthrough mode.
        """
        was_active = self._input_bypass_active
        self._input_bypass_active = bypass
        logger.info(f"Input bypass {'enabled' if bypass else 'disabled'}")

        # When bypass is turned OFF, re-apply input using existing passthrough logic
        # This properly handles HTP/LTP merge, group triggering, and frontend notification
        if was_active and not bypass:
            # Clear group caches so groups re-trigger and broadcast properly
            self._last_group_values.clear()
            self._last_group_broadcast.clear()

            for universe_id in self.inputs:
                input_values = self._input_values.get(universe_id)
                if input_values:
                    # Reset local values for input-controlled channels so input takes priority
                    # Otherwise HTP merge would keep the higher values user set during bypass
                    config = self._passthrough_config.get(universe_id, {})
                    if config.get("passthrough_mode") in ("faders_output", "output_only"):
                        channel_start = config.get("channel_start", 1)
                        channel_end = config.get("channel_end", 512)
                        if universe_id in self._local_values:
                            for i in range(channel_start - 1, channel_end):
                                self._local_values[universe_id][i] = 0

                    # Reset throttle so fader UI update is guaranteed to be sent
                    self._last_input_broadcast[universe_id] = 0

                    self._on_input_received(universe_id, input_values)

    def get_input_bypass(self) -> bool:
        """Get current input bypass state."""
        return self._input_bypass_active

    # ============= Grand Master Control =============

    def set_global_grandmaster(self, value: int, source: str = "local") -> None:
        """Set global grand master value (0-255)."""
        self._global_grandmaster = max(0, min(255, value))
        # Re-send all universes to apply new scaling
        for universe_id in self.universes:
            self._send_universe(universe_id)
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback("grandmaster_changed", {
                    "type": "global",
                    "value": self._global_grandmaster
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")
        # Send MIDI output if configured (but not if change came from MIDI)
        if source != "midi":
            self.send_midi_grandmaster_value("global", self._global_grandmaster)

    def get_global_grandmaster(self) -> int:
        """Get global grand master value."""
        return self._global_grandmaster

    def set_universe_grandmaster(self, universe_id: int, value: int, source: str = "local") -> None:
        """Set per-universe grand master value (0-255)."""
        self._universe_grandmasters[universe_id] = max(0, min(255, value))
        # Re-send this universe to apply new scaling
        self._send_universe(universe_id)
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback("grandmaster_changed", {
                    "type": "universe",
                    "universe_id": universe_id,
                    "value": self._universe_grandmasters[universe_id]
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")
        # Send MIDI output if configured (but not if change came from MIDI)
        if source != "midi":
            self.send_midi_grandmaster_value("universe", self._universe_grandmasters[universe_id], universe_id)

    def get_universe_grandmaster(self, universe_id: int) -> int:
        """Get per-universe grand master value (default 255)."""
        return self._universe_grandmasters.get(universe_id, 255)

    def get_all_grandmasters(self) -> dict:
        """Get all grand master values."""
        return {
            "global": self._global_grandmaster,
            "universes": dict(self._universe_grandmasters)
        }

    def _apply_channel_overrides(self, channels: List[int], universe_id: int) -> List[int]:
        """Apply park and highlight overrides before grandmaster scaling.

        Priority order: Park > Highlight > Normal values
        """
        result = channels.copy()

        # Highlight mode (lower priority) - if active, set highlighted channels to 255, others to dim level
        if self._highlight_active:
            highlighted = self._highlighted_channels.get(universe_id, set())
            for i in range(512):
                if (i + 1) in highlighted:
                    result[i] = 255
                else:
                    result[i] = self._highlight_dim_level

        # Park overrides (highest priority - overrides highlight)
        parked = self._parked_channels.get(universe_id, {})
        for channel, value in parked.items():
            result[channel - 1] = value

        return result

    def _apply_grandmaster_scaling(self, channels: List[int], universe_id: int) -> List[int]:
        """Apply grand master scaling to channels before output.

        Final value = channel * (universe_gm / 255) * (global_gm / 255)
        """
        universe_gm = self._universe_grandmasters.get(universe_id, 255)
        global_gm = self._global_grandmaster

        # If both are at full, no scaling needed
        if universe_gm == 255 and global_gm == 255:
            return channels

        # Calculate combined scale factor
        scale = (universe_gm / 255.0) * (global_gm / 255.0)
        return [min(255, round(ch * scale)) for ch in channels]

    def _send_universe(self, universe_id: int) -> None:
        """Send universe data to all configured outputs."""
        universe = self.get_universe(universe_id)
        if not universe:
            logger.debug(f"_send_universe({universe_id}): universe not found")
            return

        universe.active = True

        # Apply park/highlight overrides
        channels_with_overrides = self._apply_channel_overrides(universe.channels, universe_id)

        # DEBUG: Log if highlight or park is active
        if self._highlight_active:
            highlighted = self._highlighted_channels.get(universe_id, set())
            logger.info(f"Highlight active: universe={universe_id}, highlighted={highlighted}, ch1-5={channels_with_overrides[:5]}")
        parked = self._parked_channels.get(universe_id, {})
        if parked:
            logger.info(f"Parked channels: universe={universe_id}, parked={parked}")

        # Apply grand master scaling before output
        scaled_channels = self._apply_grandmaster_scaling(channels_with_overrides, universe_id)

        outputs = self.outputs.get(universe_id, [])
        active_count = 0
        for output in outputs:
            if output and output.running:
                # Schedule async send in the event loop
                asyncio.create_task(output.send_dmx(scaled_channels))
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

        # Send MIDI output if configured (but not if change came from MIDI to avoid loops)
        if source != "midi":
            self.send_midi_channel_value(universe_id, channel, value)

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

    def _hsl_to_rgb(self, h: float, s: float, l: float) -> tuple:
        """Convert HSL to RGB.

        Args:
            h: Hue (0-360)
            s: Saturation (0-100)
            l: Lightness (0-100)

        Returns:
            Tuple of (r, g, b) values (0-255)
        """
        s = s / 100
        l = l / 100

        if s == 0:
            # Achromatic (gray)
            val = int(l * 255)
            return (val, val, val)

        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = l - c / 2

        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (
            int((r + m) * 255),
            int((g + m) * 255),
            int((b + m) * 255)
        )

    def _color_role_to_value(self, role: str, r: int, g: int, b: int) -> int:
        """Map color role to RGB value.

        Args:
            role: Color role name (red, green, blue, white, amber, etc.)
            r, g, b: RGB values (0-255)

        Returns:
            The appropriate value for this color role (0-255)
        """
        # Primary colors - direct mapping
        if role == "red":
            return r
        elif role == "green":
            return g
        elif role == "blue":
            return b

        # Secondary colors - mix of two primaries
        elif role == "yellow":
            # Yellow = red + green (no blue)
            return min(r, g)
        elif role == "cyan":
            # Cyan = green + blue (no red)
            return min(g, b)
        elif role == "magenta":
            # Magenta = red + blue (no green)
            return min(r, b)

        # White variations - all three primaries
        elif role == "white":
            return min(r, g, b)
        elif role == "warm_white":
            # Warm white - favor when red/yellow tones present
            return min(r, g, b)
        elif role == "cool_white":
            # Cool white - favor when blue tones present
            return min(r, g, b)

        # Tertiary colors - between primary and secondary
        elif role == "orange":
            # Orange: between red and yellow (red dominant, some green, no blue)
            # Fires strongest when r > g > 0 and b is low
            if r > g and b < min(r, g):
                return min(r, g * 2)
            return 0
        elif role == "amber":
            # Amber: warm yellow-orange (balanced red/green, no blue)
            # Similar to yellow but with slight red bias
            if r > 0 and g > 0 and b < min(r, g):
                return min(r, g)
            return 0
        elif role == "lime":
            # Lime: between green and yellow (green dominant, some red, no blue)
            # Fires strongest when g > r > 0 and b is low
            if g > r and b < min(r, g):
                return min(g, r * 2)
            return 0

        # UV - follows blue/purple spectrum
        elif role == "uv":
            # UV: accent for blues and purples
            # Fires when blue is present
            return b

        return 0

    def _apply_group(self, group_id: int, master_value: int) -> None:
        """Apply master value to all group members using HTP merge.

        When multiple groups control the same channel, HTP (Highest Takes Precedence)
        ensures smooth crossfades instead of flickering.

        Supports virtual targets:
        - target_type="channel": Regular DMX channel (default)
        - target_type="universe_master": Controls a universe's grandmaster
        - target_type="global_master": Controls the global grandmaster
        """
        group = self._groups.get(group_id)
        if not group or not group.get("enabled", True):
            return

        # Handle color_mixer mode - calculate RGB from stored color state
        if group.get("mode") == "color_mixer":
            # Get color state (default to white if not set)
            color_state = group.get("color_state", {"h": 0, "s": 0, "l": 100})
            h = color_state.get("h", 0)
            s = color_state.get("s", 0)
            l = color_state.get("l", 100)

            # Convert HSL to RGB
            r, g, b = self._hsl_to_rgb(h, s, l)

            # Apply brightness (master_value) scaling
            brightness = master_value

            affected_universes = set()
            for member in group.get("members", []):
                if member.get("target_type", "channel") != "channel":
                    continue
                color_role = member.get("color_role")
                if not color_role:
                    continue

                raw_value = self._color_role_to_value(color_role, r, g, b)
                output_value = int(raw_value * brightness / 255)

                uid = member.get("universe_id")
                channel = member.get("channel")

                if uid is None or channel is None:
                    continue

                # Skip if channel is parked
                if self.is_channel_parked(uid, channel):
                    continue

                universe = self.get_universe(uid)
                if universe:
                    universe.set_channel(channel, output_value)
                    affected_universes.add(uid)
                    self._channel_sources.setdefault(uid, {})[channel] = "group"

            # Send all affected universes
            for uid in affected_universes:
                self._send_universe(uid)

            # Notify callbacks for each affected channel (updates frontend faders)
            for member in group.get("members", []):
                if member.get("target_type", "channel") != "channel":
                    continue
                uid = member.get("universe_id")
                channel = member.get("channel")
                if uid and channel:
                    universe = self.get_universe(uid)
                    if universe:
                        value = universe.get_channel(channel)
                        self._notify_callbacks(uid, channel, value, "group")

            return  # Done with color_mixer

        affected_channels = []  # [(universe_id, channel), ...]

        for member in group.get("members", []):
            target_type = member.get("target_type", "channel")

            if group["mode"] == "follow":
                output_value = master_value
            else:  # proportional
                base_value = member.get("base_value", 255)
                output_value = round((base_value * master_value) / 255)

            # Handle different target types
            if target_type == "universe_master":
                # Apply to universe grandmaster
                target_uid = member.get("target_universe_id")
                if target_uid is not None:
                    self.set_universe_grandmaster(target_uid, output_value)
                continue

            elif target_type == "global_master":
                # Apply to global grandmaster
                self.set_global_grandmaster(output_value)
                continue

            # Default: regular channel target
            member_universe_id = member.get("universe_id")
            member_channel = member.get("channel")

            if member_universe_id is None or member_channel is None:
                continue

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

            # Skip if channel is parked (parked channels ignore all input including groups)
            if self.is_channel_parked(universe_id, channel):
                continue

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

            # Initialize color_state for color_mixer groups if not present
            if group.get("mode") == "color_mixer" and "color_state" not in group:
                group["color_state"] = {"h": 0, "s": 0, "l": 100}  # White default

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

        # Initialize color_state for color_mixer groups if not present
        if group.get("mode") == "color_mixer" and "color_state" not in group:
            group["color_state"] = {"h": 0, "s": 0, "l": 100}  # White default

        self._groups[group_id] = group

        # Only add master mapping if group has physical master
        if group.get("master_universe") and group.get("master_channel"):
            master_key = (group["master_universe"], group["master_channel"])
            if master_key not in self._master_to_groups:
                self._master_to_groups[master_key] = []
            if group_id not in self._master_to_groups[master_key]:
                self._master_to_groups[master_key].append(group_id)

        logger.info(f"Added group {group_id}: {group['name']}")

    def set_group_color(self, group_id: int, h: float, s: float, l: float) -> bool:
        """Update a color_mixer group's color state and reapply.

        Args:
            group_id: The group ID
            h: Hue (0-360)
            s: Saturation (0-100)
            l: Lightness (0-100)

        Returns:
            True if successful, False if group not found or not color_mixer
        """
        group = self._groups.get(group_id)
        if not group or group.get("mode") != "color_mixer":
            return False

        # Update color state
        group["color_state"] = {"h": h, "s": s, "l": l}

        # Reapply with current brightness (default to full brightness if not set)
        current_value = group.get("master_value")
        if current_value is None:
            current_value = 255
        self._apply_group(group_id, current_value)

        logger.debug(f"Set color for group {group_id}: h={h}, s={s}, l={l}")
        return True

    def get_group(self, group_id: int) -> Optional[dict]:
        """Get a group by ID."""
        return self._groups.get(group_id)

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

    def _get_groups_containing_member(self, universe_id: int, channel: int) -> list:
        """Get list of enabled groups that contain this channel as a member."""
        result = []
        for group in self._groups.values():
            if not group.get("enabled"):
                continue
            for member in group.get("members", []):
                if member["universe_id"] == universe_id and member["channel"] == channel:
                    result.append(group)
                    break
        return result

    def _get_member_base_value(self, group: dict, universe_id: int, channel: int) -> int:
        """Get the base_value for a specific member in a group."""
        for member in group.get("members", []):
            if member["universe_id"] == universe_id and member["channel"] == channel:
                return member.get("base_value", 255)
        return 255

    # =========================================================================
    # MIDI Integration methods
    # =========================================================================

    def _on_midi_message(self, msg_type: str, data: dict) -> None:
        """Handle incoming MIDI messages.

        Args:
            msg_type: Message type ('control_change', 'note_on', 'note_off', etc.)
            data: Message data dict with keys like 'channel', 'control', 'value', 'note', 'velocity', 'device_name'
        """
        midi_channel = data.get("channel")
        device_name = data.get("device_name")  # Source device for multi-device filtering

        if msg_type == "control_change":
            # CC -> Input Channel mapping
            self._handle_midi_cc_input(midi_channel, data.get("control"), data.get("value"), device_name)
        elif msg_type == "note_on":
            # Note -> Trigger action
            self._handle_midi_note_trigger(midi_channel, data.get("note"), data.get("velocity"), on=True, device_name=device_name)
        elif msg_type == "note_off":
            self._handle_midi_note_trigger(midi_channel, data.get("note"), data.get("velocity"), on=False, device_name=device_name)

        # Broadcast MIDI activity to frontend for indicator
        for callback in self._callbacks:
            try:
                callback("midi_activity", {
                    "type": msg_type,
                    "data": data
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def set_scene_recall_callback(self, callback: Callable) -> None:
        """Set callback for scene recall from MIDI.

        Args:
            callback: Function with signature (scene_id: int, velocity: int)
        """
        self._scene_recall_callback = callback

    async def start_midi_input(self, device_name: Optional[str] = None) -> bool:
        """Start MIDI input.

        Args:
            device_name: MIDI device name, or None for default

        Returns:
            True if started successfully
        """
        if self._midi_handler is None:
            self._midi_handler = MIDIHandler(on_message_callback=self._on_midi_message)

        success = await self._midi_handler.start_input(device_name)
        if success:
            logger.info(f"MIDI input started: {device_name or 'default'}")
        return success

    async def stop_midi_input(self) -> None:
        """Stop MIDI input."""
        if self._midi_handler:
            await self._midi_handler.stop_input()
            logger.info("MIDI input stopped")

    async def start_midi_output(self, device_name: Optional[str] = None) -> bool:
        """Start MIDI output.

        Args:
            device_name: MIDI device name, or None for default

        Returns:
            True if started successfully
        """
        if self._midi_handler is None:
            self._midi_handler = MIDIHandler(on_message_callback=self._on_midi_message)

        success = await self._midi_handler.start_output(device_name)
        if success:
            self._midi_output_enabled = True
            logger.info(f"MIDI output started: {device_name or 'default'}")
        return success

    async def stop_midi_output(self) -> None:
        """Stop MIDI output."""
        if self._midi_handler:
            await self._midi_handler.stop_output()
            self._midi_output_enabled = False
            logger.info("MIDI output stopped")

    def get_midi_status(self) -> dict:
        """Get current MIDI handler status."""
        if self._midi_handler:
            return self._midi_handler.get_status()
        return {
            "available": MIDIHandler.is_available(),
            "input": {"running": False, "device": None, "messages_received": 0},
            "output": {"running": False, "device": None, "messages_sent": 0},
            "learn_mode": False,
            "last_message": None
        }

    def get_midi_devices(self) -> dict:
        """Get available MIDI devices."""
        return {
            "inputs": MIDIHandler.list_input_devices(),
            "outputs": MIDIHandler.list_output_devices()
        }

    def start_midi_learn(self) -> None:
        """Start MIDI learn mode."""
        if self._midi_handler:
            self._midi_handler.start_learn_mode()

    def stop_midi_learn(self) -> None:
        """Stop MIDI learn mode."""
        if self._midi_handler:
            self._midi_handler.stop_learn_mode()

    def get_midi_last_message(self) -> Optional[dict]:
        """Get last received MIDI message (for learn mode)."""
        if self._midi_handler:
            return self._midi_handler.get_last_learned_message()
        return None

    def send_midi_channel_value(self, universe_id: int, channel: int, value: int) -> None:
        """Send MIDI CC feedback for a channel value change.

        Looks up existing CC mappings that target this input channel and sends
        the corresponding CC message back to the controller.
        """
        if not self._midi_handler or not self._midi_output_enabled:
            return

        # Check if MIDI output is running
        if not self._midi_handler._output_port:
            return

        # Reverse lookup: find CC mappings for this input channel
        for mapping in self._midi_cc_mappings:
            if mapping.get("input_channel") == channel and mapping.get("enabled", True):
                cc_number = mapping.get("cc_number")
                midi_channel = mapping.get("midi_channel", 0)
                if midi_channel == -1:
                    midi_channel = 0  # Default to channel 0 for "all"

                # Scale DMX (0-255) to MIDI (0-127)
                midi_value = value >> 1  # Fast divide by 2

                self._midi_handler.send_cc(midi_channel, cc_number, midi_value)

    def send_midi_grandmaster_value(self, gm_type: str, value: int, universe_id: int = None) -> None:
        """Send MIDI CC feedback for a grandmaster change.

        Note: Grandmaster MIDI feedback mapping is not currently implemented.
        """
        pass

    def send_midi_scene_active(self, scene_id: int, active: bool) -> None:
        """Send MIDI note feedback for scene active state change.

        Looks up existing note triggers for this scene and sends
        note on/off to light up or turn off controller buttons.
        """
        if not self._midi_handler or not self._midi_output_enabled:
            return

        # Check if MIDI output is running
        if not self._midi_handler._output_port:
            return

        # Find note triggers for this scene
        for trigger in self._midi_triggers:
            if (trigger.get("action") == "scene" and
                trigger.get("target_id") == scene_id and
                trigger.get("enabled", True)):

                note = trigger.get("note")
                midi_channel = trigger.get("midi_channel", 0)
                if midi_channel == -1:
                    midi_channel = 0

                if active:
                    self._midi_handler.send_note_on(midi_channel, note, 127)
                else:
                    self._midi_handler.send_note_off(midi_channel, note)

    def _send_midi_blackout_feedback(self, active: bool) -> None:
        """Send MIDI note feedback for blackout state change."""
        if not self._midi_handler or not self._midi_output_enabled:
            return

        # Check if MIDI output is running
        if not self._midi_handler._output_port:
            return

        # Find blackout triggers
        for trigger in self._midi_triggers:
            if trigger.get("action") == "blackout" and trigger.get("enabled", True):
                note = trigger.get("note")
                midi_channel = trigger.get("midi_channel", 0)
                if midi_channel == -1:
                    midi_channel = 0

                if active:
                    self._midi_handler.send_note_on(midi_channel, note, 127)
                else:
                    self._midi_handler.send_note_off(midi_channel, note)

    def set_midi_output_enabled(self, enabled: bool) -> None:
        """Enable/disable MIDI feedback output."""
        self._midi_output_enabled = enabled
        logger.info(f"MIDI output feedback {'enabled' if enabled else 'disabled'}")

    def set_active_scene(self, scene_id: Optional[int]) -> None:
        """Set the active scene and send MIDI feedback.

        Sends note off for previous scene (if any) and note on for new scene.
        """
        previous_scene = self._active_scene_id

        # Send note off for previous scene
        if previous_scene is not None and previous_scene != scene_id:
            self.send_midi_scene_active(previous_scene, False)

        # Update active scene
        self._active_scene_id = scene_id

        # Send note on for new scene
        if scene_id is not None:
            self.send_midi_scene_active(scene_id, True)

    def get_active_scene(self) -> Optional[int]:
        """Get the currently active scene ID."""
        return self._active_scene_id

    # =========================================================================
    # MIDI Input Integration (CC -> Input Channels, Note -> Triggers)
    # =========================================================================

    def load_midi_cc_mappings(self, mappings: List[dict]) -> None:
        """Load MIDI CC -> Input Channel mappings.

        Args:
            mappings: List of dicts with keys: cc_number, midi_channel, input_channel, enabled, label
        """
        self._midi_cc_mappings = [m for m in mappings if m.get("enabled", True)]
        logger.info(f"Loaded {len(self._midi_cc_mappings)} MIDI CC mappings")

    def load_midi_triggers(self, triggers: List[dict]) -> None:
        """Load MIDI Note -> Action triggers.

        Args:
            triggers: List of dicts with keys: note, midi_channel, action, target_id, enabled, label
        """
        self._midi_triggers = [t for t in triggers if t.get("enabled", True)]
        logger.info(f"Loaded {len(self._midi_triggers)} MIDI triggers")

    def get_midi_input_values(self) -> List[int]:
        """Get current MIDI input channel values (virtual input universe)."""
        return self._midi_input_values.copy()

    def get_midi_input_status(self) -> dict:
        """Get MIDI input status for I/O page display."""
        midi_status = self.get_midi_status()
        input_running = midi_status.get("input", {}).get("running", False)
        network_running = midi_status.get("network", {}).get("server_running", False)

        # Count active input channels (non-zero values)
        active_channels = sum(1 for v in self._midi_input_values if v > 0)

        return {
            "type": "midi",
            "enabled": self._midi_input_enabled,
            "running": input_running or network_running,
            "device_name": midi_status.get("input", {}).get("device"),
            "network_running": network_running,
            "network_port": midi_status.get("network", {}).get("port"),
            "network_peers": len(midi_status.get("network", {}).get("peers", [])),
            "active_channels": active_channels,
            "cc_mappings_count": len(self._midi_cc_mappings),
            "triggers_count": len(self._midi_triggers),
            "messages_received": midi_status.get("input", {}).get("messages_received", 0)
        }

    def set_midi_input_enabled(self, enabled: bool) -> None:
        """Enable/disable MIDI input integration with I/O system."""
        self._midi_input_enabled = enabled
        logger.info(f"MIDI input integration {'enabled' if enabled else 'disabled'}")

    def _handle_midi_cc_input(self, midi_channel: int, cc_number: int, cc_value: int, device_name: Optional[str] = None) -> None:
        """Handle MIDI CC as input to universe channels.

        CC mappings are global (CC X -> Channel Y). The value is applied to ALL
        universes that have MIDI input enabled. The /io page determines which
        universes receive MIDI input.

        Args:
            midi_channel: MIDI channel (0-15)
            cc_number: CC number (0-127)
            cc_value: CC value (0-127)
            device_name: Source device name for multi-device filtering
        """
        if cc_number is None or cc_value is None:
            return

        from .dmx_inputs import MIDIInput

        dmx_value = midi_to_dmx(cc_value)

        # Find matching CC mappings
        for mapping in self._midi_cc_mappings:
            if mapping.get("cc_number") != cc_number:
                continue
            # Check MIDI channel (-1 = any channel)
            mapping_channel = mapping.get("midi_channel", -1)
            if mapping_channel != -1 and mapping_channel != midi_channel:
                continue
            # Check device filter on mapping (None = all devices)
            mapping_device = mapping.get("device_name")
            if mapping_device is not None and mapping_device != device_name:
                continue  # Skip - mapping is for a different device

            input_channel = mapping.get("input_channel")
            if input_channel is None or not (1 <= input_channel <= 512):
                continue

            # Apply to ALL universes with MIDI input enabled
            for universe_id, input_handler in self.inputs.items():
                if not isinstance(input_handler, MIDIInput):
                    continue
                if not input_handler.running:
                    continue

                # Check if the device matches this universe's MIDI input device filter
                input_device = input_handler.get_device_name()
                if input_device and input_device != device_name:
                    # This universe's MIDI input is configured for a different device
                    continue

                # Apply value to this universe's MIDI input
                # This triggers the standard input callback -> merge -> output flow
                input_handler.set_channel(input_channel, dmx_value)

    def _handle_midi_note_trigger(self, midi_channel: int, note: int, velocity: int, on: bool, device_name: Optional[str] = None) -> None:
        """Handle MIDI Note as a direct action trigger (new I/O integration).

        These triggers bypass the channel mapping system and execute actions directly.
        Supports device-specific triggers.

        Args:
            midi_channel: MIDI channel (0-15)
            note: Note number (0-127)
            velocity: Note velocity (0-127)
            on: True for note on, False for note off
            device_name: Source device name for multi-device filtering
        """
        if note is None:
            return

        # Find matching triggers
        for trigger in self._midi_triggers:
            if trigger.get("note") != note:
                continue
            # Check MIDI channel (-1 = any channel)
            trigger_channel = trigger.get("midi_channel", -1)
            if trigger_channel != -1 and trigger_channel != midi_channel:
                continue
            # Check device filter (None = all devices)
            trigger_device = trigger.get("device_name")
            if trigger_device is not None and trigger_device != device_name:
                continue  # Skip - trigger is for a different device

            action = trigger.get("action")
            target_id = trigger.get("target_id")

            if action == "scene" and on:
                # Recall scene
                if target_id is not None and self._scene_recall_callback:
                    try:
                        self._scene_recall_callback(target_id, velocity)
                    except Exception as e:
                        logger.error(f"MIDI trigger scene recall error: {e}")

            elif action == "blackout":
                # Toggle blackout on note on
                if on:
                    if self.is_blackout_active():
                        self.release_blackout()
                    else:
                        self.blackout()

            elif action == "group" and on:
                # Trigger group at full (velocity scaled)
                if target_id is not None:
                    group_value = midi_to_dmx(velocity)
                    self.apply_group_direct(target_id, group_value)
                    asyncio.create_task(ws_manager.broadcast_group_value_changed(target_id, group_value))

    def _on_midi_input_received(self, channels_changed: set) -> None:
        """Handle MIDI input update - similar to Art-Net/sACN input handling.

        This integrates MIDI into the existing input system, allowing it to:
        - Show up in I/O page
        - Work with channel mapping (/mapping page)
        - Use HTP/LTP merge with fader values
        """
        now = time.time()

        # Throttle broadcasts
        if now - self._last_midi_input_broadcast < self._midi_input_broadcast_interval:
            return
        self._last_midi_input_broadcast = now

        # Broadcast MIDI input values to frontend (for I/O page monitor)
        for callback in self._callbacks:
            try:
                callback("midi_input_received", {
                    "values": self._midi_input_values,
                    "channels_changed": list(channels_changed)
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

        # Apply to output if MIDI input integration is enabled
        # This uses the channel mapping system if enabled
        if self._midi_input_enabled:
            if self._mapping_enabled:
                # Use channel mapping - MIDI acts as a "virtual universe" (ID 0)
                # The mapping system will route MIDI input channels to output channels
                self._apply_midi_mapped_input(channels_changed)
            else:
                # Direct passthrough - apply MIDI input values to channels
                self._apply_midi_direct_input(channels_changed)

    def _apply_midi_direct_input(self, channels_changed: set) -> None:
        """Apply MIDI input directly to output channels (no mapping).

        Uses HTP merge with local fader values.
        """
        if self._blackout_active:
            return

        # For direct mode, apply to universe 1 (or first available universe)
        if not self.universes:
            return

        universe_id = min(self.universes.keys())
        universe = self.get_universe(universe_id)
        if not universe:
            return

        local = self._local_values.get(universe_id, [0] * 512)
        current = universe.get_all()

        for channel in channels_changed:
            ch_idx = channel - 1
            midi_value = self._midi_input_values[ch_idx]
            # HTP merge: highest wins
            current[ch_idx] = max(local[ch_idx], midi_value)

        universe.set_all(current)
        self._send_universe(universe_id)

        # Notify UI
        for callback in self._callbacks:
            try:
                callback("midi_input_to_ui", {
                    "universe_id": universe_id,
                    "channels": list(channels_changed),
                    "values": self._midi_input_values
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _apply_midi_mapped_input(self, channels_changed: set) -> None:
        """Apply MIDI input using the channel mapping system.

        MIDI input channels are treated as source channels that get mapped
        to output channels via the /mapping configuration.
        """
        if self._blackout_active:
            return

        # Build values array with only changed channels
        midi_values = self._midi_input_values

        # Use special universe ID 0 for MIDI input in mapping lookups
        MIDI_UNIVERSE_ID = 0

        # Track which output channels need updating
        dst_values: Dict[int, Dict[int, int]] = {}  # {universe: {channel: value}}

        for src_ch in channels_changed:
            value = midi_values[src_ch - 1]
            destinations = self._channel_map.get((MIDI_UNIVERSE_ID, src_ch), [])

            if destinations:
                # Mapped channel - apply to all destinations
                for dst_info in destinations:
                    target_type = dst_info.get("target_type", "channel")

                    if target_type == "universe_master":
                        target_uid = dst_info.get("target_universe_id")
                        if target_uid is not None:
                            self.set_universe_grandmaster(target_uid, value)
                    elif target_type == "global_master":
                        self.set_global_grandmaster(value)
                    else:
                        # Normal channel mapping
                        dst_universe = dst_info.get("universe")
                        dst_ch = dst_info.get("channel")
                        if dst_universe is not None and dst_ch is not None:
                            if dst_universe not in dst_values:
                                dst_values[dst_universe] = {}
                            dst_values[dst_universe][dst_ch] = value

        # Apply to each destination universe using HTP merge
        for dst_universe_id, channel_values in dst_values.items():
            universe = self.get_universe(dst_universe_id)
            if not universe:
                continue

            local = self._local_values.get(dst_universe_id, [0] * 512)
            current = universe.get_all()

            for channel, value in channel_values.items():
                ch_idx = channel - 1
                # HTP merge
                current[ch_idx] = max(local[ch_idx], value)

            universe.set_all(current)
            self._send_universe(dst_universe_id)

    # =========================================================================
    # Network MIDI (rtpMIDI) methods
    # =========================================================================

    async def start_midi_network_server(self, port: int = 5004, name: str = "DMXX") -> bool:
        """Start rtpMIDI server to accept incoming connections.

        Args:
            port: Port to listen on (default 5004)
            name: Service name visible to other devices

        Returns:
            True if server started successfully
        """
        if self._midi_handler is None:
            self._midi_handler = MIDIHandler(on_message_callback=self._on_midi_message)

        success = await self._midi_handler.start_network_server(port, name)
        if success:
            logger.info(f"Network MIDI server started on port {port} as '{name}'")
        return success

    async def stop_midi_network_server(self) -> None:
        """Stop the rtpMIDI server."""
        if self._midi_handler:
            await self._midi_handler.stop_network_server()
            logger.info("Network MIDI server stopped")

    def get_midi_network_peers(self) -> list:
        """Get list of connected network MIDI peers."""
        if self._midi_handler:
            return self._midi_handler.get_network_peers()
        return []

    # =========================================================================
    # Park Channels & Highlight/Solo
    # =========================================================================

    def park_channel(self, universe_id: int, channel: int, value: int) -> None:
        """Park a channel at a fixed value, ignoring all other input.

        Args:
            universe_id: Universe ID
            channel: Channel number (1-512)
            value: Value to lock to (0-255)
        """
        if not (1 <= channel <= 512) or not (0 <= value <= 255):
            return

        if universe_id not in self._parked_channels:
            self._parked_channels[universe_id] = {}

        self._parked_channels[universe_id][channel] = value
        logger.info(f"Parked channel {channel} in universe {universe_id} at value {value}")

        # Also update universe.channels so UI shows parked value
        universe = self.get_universe(universe_id)
        if universe:
            universe.set_channel(channel, value)

        # Immediately apply to output
        self._send_universe(universe_id)

        # Broadcast update
        for callback in self._callbacks:
            try:
                callback("park_update", {
                    "universe_id": universe_id,
                    "channel": channel,
                    "value": value,
                    "parked": True
                })
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def unpark_channel(self, universe_id: int, channel: int) -> None:
        """Unpark a channel, restoring normal control.

        Args:
            universe_id: Universe ID
            channel: Channel number (1-512)
        """
        if universe_id in self._parked_channels and channel in self._parked_channels[universe_id]:
            del self._parked_channels[universe_id][channel]
            if not self._parked_channels[universe_id]:
                del self._parked_channels[universe_id]

            logger.info(f"Unparked channel {channel} in universe {universe_id}")

            # Immediately apply to output
            self._send_universe(universe_id)

            # Broadcast update
            for callback in self._callbacks:
                try:
                    callback("park_update", {
                        "universe_id": universe_id,
                        "channel": channel,
                        "value": None,
                        "parked": False
                    })
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    def get_parked_channels(self, universe_id: int) -> Dict[int, int]:
        """Get all parked channels for a universe.

        Args:
            universe_id: Universe ID

        Returns:
            Dict mapping channel number to parked value
        """
        return self._parked_channels.get(universe_id, {}).copy()

    def get_all_parked_channels(self) -> Dict[int, Dict[int, int]]:
        """Get all parked channels for all universes.

        Returns:
            Dict mapping universe_id to {channel: value}
        """
        return {uid: channels.copy() for uid, channels in self._parked_channels.items()}

    def start_highlight(self, universe_id: int, channels: List[int], dim_level: int = 0) -> None:
        """Start highlight/solo mode for specified channels.

        Highlighted channels go to 255, all others go to dim_level.

        Args:
            universe_id: Universe ID
            channels: List of channel numbers (1-512) to highlight
            dim_level: Value for non-highlighted channels (0-255, default 0)
        """
        self._highlight_active = True
        self._highlight_dim_level = max(0, min(255, dim_level))

        if universe_id not in self._highlighted_channels:
            self._highlighted_channels[universe_id] = set()

        # Add channels to highlight set
        for ch in channels:
            if 1 <= ch <= 512:
                self._highlighted_channels[universe_id].add(ch)

        logger.info(f"Highlight started: universe {universe_id}, channels {channels}, dim_level {dim_level}")

        # Apply to all universes
        for uid in self.universes:
            self._send_universe(uid)

        # Broadcast update
        self._broadcast_highlight_state()

    def add_to_highlight(self, universe_id: int, channel: int) -> None:
        """Add a single channel to the highlight set.

        Args:
            universe_id: Universe ID
            channel: Channel number (1-512)
        """
        if not (1 <= channel <= 512):
            return

        if not self._highlight_active:
            self._highlight_active = True

        if universe_id not in self._highlighted_channels:
            self._highlighted_channels[universe_id] = set()

        self._highlighted_channels[universe_id].add(channel)
        logger.info(f"Added channel {channel} in universe {universe_id} to highlight")

        # Apply to all universes
        for uid in self.universes:
            self._send_universe(uid)

        self._broadcast_highlight_state()

    def remove_from_highlight(self, universe_id: int, channel: int) -> None:
        """Remove a single channel from the highlight set.

        If no channels remain highlighted, highlight mode ends.

        Args:
            universe_id: Universe ID
            channel: Channel number (1-512)
        """
        if universe_id in self._highlighted_channels:
            self._highlighted_channels[universe_id].discard(channel)
            if not self._highlighted_channels[universe_id]:
                del self._highlighted_channels[universe_id]

        # If no more highlighted channels anywhere, end highlight mode
        if not any(self._highlighted_channels.values()):
            self.stop_highlight()
        else:
            logger.info(f"Removed channel {channel} in universe {universe_id} from highlight")
            # Apply to all universes
            for uid in self.universes:
                self._send_universe(uid)
            self._broadcast_highlight_state()

    def stop_highlight(self) -> None:
        """Stop highlight/solo mode, restoring normal output."""
        self._highlight_active = False
        self._highlighted_channels.clear()
        self._highlight_dim_level = 0

        logger.info("Highlight mode stopped")

        # Apply to all universes
        for uid in self.universes:
            self._send_universe(uid)

        self._broadcast_highlight_state()

    def get_highlight_state(self) -> dict:
        """Get current highlight state.

        Returns:
            Dict with active, dim_level, and channels per universe
        """
        return {
            "active": self._highlight_active,
            "dim_level": self._highlight_dim_level,
            "channels": {uid: list(channels) for uid, channels in self._highlighted_channels.items()}
        }

    def is_channel_highlighted(self, universe_id: int, channel: int) -> bool:
        """Check if a channel is in the highlight set."""
        return channel in self._highlighted_channels.get(universe_id, set())

    def is_channel_parked(self, universe_id: int, channel: int) -> bool:
        """Check if a channel is parked."""
        return channel in self._parked_channels.get(universe_id, {})

    def _broadcast_highlight_state(self) -> None:
        """Broadcast highlight state to all clients."""
        state = self.get_highlight_state()
        for callback in self._callbacks:
            try:
                callback("highlight_update", state)
            except Exception as e:
                logger.error(f"Callback error: {e}")


# Global DMX interface instance
dmx_interface = DMXInterface()
