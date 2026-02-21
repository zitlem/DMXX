"""MIDI input/output handler for external controller support."""
import asyncio
import threading
import queue
import time
from typing import Callable, Optional, List, Dict, Any

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False
    mido = None

# Import network MIDI handler
from .midi_network import NetworkMIDIHandler, PYMIDI_AVAILABLE


class MIDIHandler:
    """Handles MIDI input and output for DMX control.

    Supports both USB/hardware MIDI (via mido/rtmidi) and
    Network MIDI over IP (via rtpMIDI/pymidi).
    """

    def __init__(self, on_message_callback: Optional[Callable] = None):
        """
        Initialize MIDI handler.

        Args:
            on_message_callback: Callback function for incoming MIDI messages.
                                 Signature: callback(msg_type: str, data: dict)
        """
        self._callback = on_message_callback
        self._running = False

        # Multi-device support: dict of device_name -> port/thread
        self._input_ports: Dict[str, Any] = {}  # {device_name: mido.InputPort}
        self._input_threads: Dict[str, threading.Thread] = {}  # {device_name: Thread}

        # Single output port (multi-output less common use case)
        self._output_port = None
        self._output_device: Optional[str] = None

        self._message_queue: queue.Queue = queue.Queue()
        self._process_task: Optional[asyncio.Task] = None
        self._learn_mode = False
        self._last_message: Optional[Dict] = None
        self._messages_received = 0
        self._messages_sent = 0

        # Network MIDI handler
        self._network_handler: Optional[NetworkMIDIHandler] = None

    @staticmethod
    def is_available() -> bool:
        """Check if MIDI support is available."""
        return MIDO_AVAILABLE

    @staticmethod
    def list_input_devices() -> List[str]:
        """List available MIDI input devices."""
        if not MIDO_AVAILABLE:
            return []
        try:
            return mido.get_input_names()
        except Exception:
            return []

    @staticmethod
    def list_output_devices() -> List[str]:
        """List available MIDI output devices."""
        if not MIDO_AVAILABLE:
            return []
        try:
            return mido.get_output_names()
        except Exception:
            return []

    async def start_input(self, device_name: Optional[str] = None) -> bool:
        """
        Start MIDI input on a specific device (additive - can call multiple times).

        Args:
            device_name: Name of MIDI device to open. If None, opens default.

        Returns:
            True if started successfully.
        """
        if not MIDO_AVAILABLE:
            return False

        # If no device specified, pick the first available
        if not device_name:
            inputs = mido.get_input_names()
            if not inputs:
                return False
            device_name = inputs[0]

        # Already connected to this device
        if device_name in self._input_ports:
            return True

        try:
            # Open input port for this device
            port = mido.open_input(device_name)
            self._input_ports[device_name] = port

            # Start background thread for reading MIDI messages from this device
            thread = threading.Thread(
                target=self._read_loop,
                args=(device_name, port),
                daemon=True
            )
            self._input_threads[device_name] = thread
            thread.start()

            # Start the process loop if not already running
            if not self._running:
                self._running = True
                self._process_task = asyncio.create_task(self._process_loop())

            return True

        except Exception as e:
            print(f"Failed to start MIDI input on {device_name}: {e}")
            return False

    async def stop_input(self, device_name: Optional[str] = None) -> None:
        """
        Stop MIDI input.

        Args:
            device_name: Specific device to stop. If None, stops all devices.
        """
        if device_name:
            # Stop only the specified device
            devices_to_stop = [device_name] if device_name in self._input_ports else []
        else:
            # Stop all devices
            devices_to_stop = list(self._input_ports.keys())

        for dev in devices_to_stop:
            # Close port
            if dev in self._input_ports:
                try:
                    self._input_ports[dev].close()
                except Exception:
                    pass
                del self._input_ports[dev]

            # Wait for thread to finish
            if dev in self._input_threads:
                self._input_threads[dev].join(timeout=1.0)
                del self._input_threads[dev]

        # If no more devices, stop the process loop
        if not self._input_ports:
            self._running = False
            if self._process_task:
                self._process_task.cancel()
                try:
                    await self._process_task
                except asyncio.CancelledError:
                    pass
                self._process_task = None

    async def start_output(self, device_name: Optional[str] = None) -> bool:
        """
        Start MIDI output.

        Args:
            device_name: Name of MIDI device to open. If None, opens default.

        Returns:
            True if started successfully.
        """
        if not MIDO_AVAILABLE:
            return False

        try:
            # Close existing output if open
            if self._output_port:
                self._output_port.close()

            # Open output port
            if device_name:
                self._output_port = mido.open_output(device_name)
            else:
                # Try to open default output
                outputs = mido.get_output_names()
                if not outputs:
                    return False
                self._output_port = mido.open_output(outputs[0])
                device_name = outputs[0]

            self._output_device = device_name
            return True

        except Exception as e:
            print(f"Failed to start MIDI output: {e}")
            return False

    async def stop_output(self) -> None:
        """Stop MIDI output."""
        if self._output_port:
            try:
                self._output_port.close()
            except Exception:
                pass
            self._output_port = None
        self._output_device = None

    def _read_loop(self, device_name: str, port) -> None:
        """Background thread: Read MIDI messages from a specific device."""
        while self._running and device_name in self._input_ports:
            try:
                # Poll for messages with timeout
                msg = port.poll()
                if msg:
                    # Include device_name with the message
                    self._message_queue.put((device_name, msg))
                else:
                    # Small sleep to prevent CPU spin
                    time.sleep(0.001)
            except Exception:
                break

    async def _process_loop(self) -> None:
        """Async task: Process messages from queue."""
        while self._running:
            try:
                # Check queue without blocking
                try:
                    item = self._message_queue.get_nowait()
                    # Item is (device_name, msg) tuple
                    device_name, msg = item
                    self._handle_message(device_name, msg)
                except queue.Empty:
                    pass

                # Small delay to prevent CPU spin
                await asyncio.sleep(0.001)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"MIDI process error: {e}")

    def _handle_message(self, device_name: str, msg) -> None:
        """Handle an incoming MIDI message from a specific device."""
        self._messages_received += 1

        # Convert mido message to dict, including device_name
        msg_data = {
            "type": msg.type,
            "channel": getattr(msg, "channel", None),
            "time": time.time(),
            "device_name": device_name  # Include source device
        }

        if msg.type == "control_change":
            msg_data["control"] = msg.control
            msg_data["value"] = msg.value
        elif msg.type == "note_on":
            msg_data["note"] = msg.note
            msg_data["velocity"] = msg.velocity
        elif msg.type == "note_off":
            msg_data["note"] = msg.note
            msg_data["velocity"] = msg.velocity
        elif msg.type == "program_change":
            msg_data["program"] = msg.program

        # Store for learn mode
        if self._learn_mode:
            self._last_message = msg_data

        # Call callback if set
        if self._callback:
            try:
                self._callback(msg.type, msg_data)
            except Exception as e:
                print(f"MIDI callback error: {e}")

    def send_cc(self, channel: int, control: int, value: int) -> bool:
        """
        Send a MIDI Control Change message.

        Args:
            channel: MIDI channel (0-15)
            control: CC number (0-127)
            value: CC value (0-127)

        Returns:
            True if sent successfully.
        """
        if not self._output_port or not MIDO_AVAILABLE:
            return False

        try:
            msg = mido.Message(
                "control_change",
                channel=channel,
                control=control,
                value=max(0, min(127, value))
            )
            self._output_port.send(msg)
            self._messages_sent += 1
            return True
        except Exception as e:
            print(f"Failed to send MIDI CC: {e}")
            return False

    def send_note_on(self, channel: int, note: int, velocity: int = 127) -> bool:
        """
        Send a MIDI Note On message.

        Args:
            channel: MIDI channel (0-15)
            note: Note number (0-127)
            velocity: Note velocity (0-127)

        Returns:
            True if sent successfully.
        """
        if not self._output_port or not MIDO_AVAILABLE:
            return False

        try:
            msg = mido.Message(
                "note_on",
                channel=channel,
                note=note,
                velocity=max(0, min(127, velocity))
            )
            self._output_port.send(msg)
            self._messages_sent += 1
            return True
        except Exception as e:
            print(f"Failed to send MIDI Note On: {e}")
            return False

    def send_note_off(self, channel: int, note: int) -> bool:
        """
        Send a MIDI Note Off message.

        Args:
            channel: MIDI channel (0-15)
            note: Note number (0-127)

        Returns:
            True if sent successfully.
        """
        if not self._output_port or not MIDO_AVAILABLE:
            return False

        try:
            msg = mido.Message(
                "note_off",
                channel=channel,
                note=note,
                velocity=0
            )
            self._output_port.send(msg)
            self._messages_sent += 1
            return True
        except Exception as e:
            print(f"Failed to send MIDI Note Off: {e}")
            return False

    def start_learn_mode(self) -> None:
        """Start MIDI learn mode to capture incoming messages."""
        self._learn_mode = True
        self._last_message = None

    def stop_learn_mode(self) -> None:
        """Stop MIDI learn mode."""
        self._learn_mode = False

    def get_last_learned_message(self) -> Optional[Dict]:
        """Get the last received message during learn mode."""
        return self._last_message

    def get_status(self) -> Dict[str, Any]:
        """Get current MIDI handler status."""
        connected_devices = list(self._input_ports.keys())
        status = {
            "available": MIDO_AVAILABLE,
            "input": {
                "running": self._running,
                "device": connected_devices[0] if connected_devices else None,  # Backwards compat
                "devices": connected_devices,  # All connected devices
                "messages_received": self._messages_received
            },
            "output": {
                "running": self._output_port is not None,
                "device": self._output_device,
                "messages_sent": self._messages_sent
            },
            "learn_mode": self._learn_mode,
            "last_message": self._last_message,
            "network": self.get_network_status()
        }
        return status

    # =========================================================================
    # Network MIDI (rtpMIDI) methods
    # =========================================================================

    @staticmethod
    def is_network_available() -> bool:
        """Check if network MIDI support is available."""
        return PYMIDI_AVAILABLE

    def _get_or_create_network_handler(self) -> NetworkMIDIHandler:
        """Get or create the network MIDI handler."""
        if self._network_handler is None:
            self._network_handler = NetworkMIDIHandler(
                on_message_callback=self._on_network_message
            )
        return self._network_handler

    def _on_network_message(self, msg_type: str, data: dict) -> None:
        """Handle incoming network MIDI message."""
        self._messages_received += 1

        # Store for learn mode
        if self._learn_mode:
            self._last_message = data

        # Forward to main callback
        if self._callback:
            try:
                self._callback(msg_type, data)
            except Exception as e:
                print(f"Network MIDI callback error: {e}")

    async def start_network_server(self, port: int = 5004, name: str = "DMXX") -> bool:
        """
        Start rtpMIDI server to accept incoming connections.

        Args:
            port: Port to listen on (default 5004)
            name: Service name visible to other devices

        Returns:
            True if server started successfully.
        """
        handler = self._get_or_create_network_handler()
        return await handler.start_server(port, name)

    async def stop_network_server(self) -> None:
        """Stop the rtpMIDI server."""
        if self._network_handler:
            await self._network_handler.stop_server()

    def get_network_status(self) -> Dict[str, Any]:
        """Get network MIDI status."""
        if self._network_handler:
            return self._network_handler.get_status()
        return {
            "available": PYMIDI_AVAILABLE,
            "server_running": False,
            "port": None,
            "name": None,
            "peers": [],
            "peer_count": 0,
            "messages_received": 0,
            "messages_sent": 0
        }

    def get_network_peers(self) -> List[Dict[str, Any]]:
        """Get list of connected network MIDI peers."""
        if self._network_handler:
            return self._network_handler.get_connected_peers()
        return []

    def send_network_cc(self, channel: int, control: int, value: int) -> int:
        """
        Send CC to all connected network MIDI peers.

        Returns:
            Number of peers the message was sent to.
        """
        if self._network_handler:
            from .midi_network import make_cc_bytes
            midi_bytes = make_cc_bytes(channel, control, value)
            return self._network_handler.send_to_all(midi_bytes)
        return 0

    def send_network_note_on(self, channel: int, note: int, velocity: int) -> int:
        """
        Send Note On to all connected network MIDI peers.

        Returns:
            Number of peers the message was sent to.
        """
        if self._network_handler:
            from .midi_network import make_note_on_bytes
            midi_bytes = make_note_on_bytes(channel, note, velocity)
            return self._network_handler.send_to_all(midi_bytes)
        return 0

    def send_network_note_off(self, channel: int, note: int) -> int:
        """
        Send Note Off to all connected network MIDI peers.

        Returns:
            Number of peers the message was sent to.
        """
        if self._network_handler:
            from .midi_network import make_note_off_bytes
            midi_bytes = make_note_off_bytes(channel, note)
            return self._network_handler.send_to_all(midi_bytes)
        return 0


# Helper functions for DMX <-> MIDI value conversion
def midi_to_dmx(midi_value: int) -> int:
    """Convert MIDI value (0-127) to DMX value (0-255)."""
    return int((midi_value / 127) * 255)


def dmx_to_midi(dmx_value: int) -> int:
    """Convert DMX value (0-255) to MIDI value (0-127)."""
    return int((dmx_value / 255) * 127)


def note_to_name(note: int) -> str:
    """Convert MIDI note number to name (e.g., 60 -> 'C4')."""
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (note // 12) - 1
    note_name = notes[note % 12]
    return f"{note_name}{octave}"


def name_to_note(name: str) -> Optional[int]:
    """Convert note name to MIDI note number (e.g., 'C4' -> 60)."""
    notes = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3,
             'E': 4, 'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8,
             'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11}

    name = name.upper().strip()
    if not name:
        return None

    # Extract note and octave
    if len(name) >= 2:
        if name[1] in '#B' and len(name) >= 3:
            note_part = name[:2]
            octave_part = name[2:]
        else:
            note_part = name[0]
            octave_part = name[1:]
    else:
        return None

    try:
        octave = int(octave_part)
        note_num = notes.get(note_part)
        if note_num is not None:
            return (octave + 1) * 12 + note_num
    except ValueError:
        pass

    return None
