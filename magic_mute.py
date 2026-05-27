#!/usr/bin/env python3
"""
Magic Mute - Automatically mute microphone while typing on mechanical keyboard

Monitors a specific keyboard device and automatically mutes/unmutes a specified
microphone when typing starts/stops. Designed for Wayland environments.
"""

import argparse
import os
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Optional

try:
    import evdev
except ImportError:
    print("Error: evdev library not found. Install with: pip install evdev")
    sys.exit(1)

try:
    import pulsectl
except ImportError:
    print("Error: pulsectl library not found. Install with: pip install pulsectl")
    sys.exit(1)


class MagicMute:
    def __init__(
        self,
        keyboard_device: str,
        mic_name: str,
        unmute_delay: float = 2.0,
        verbose: bool = False,
    ):
        self.keyboard_device = keyboard_device
        self.mic_name = mic_name
        self.unmute_delay = unmute_delay
        self.verbose = verbose

        self.device: Optional[evdev.InputDevice] = None
        self.pulse: Optional[pulsectl.Pulse] = None
        self.mic_index: Optional[int] = None
        self.mic_source_name: Optional[str] = None

        self.is_muted = False
        self.unmute_timer: Optional[threading.Timer] = None
        self.timer_lock = threading.Lock()

        # Track if running as root via sudo
        self.is_sudo = os.geteuid() == 0 and 'SUDO_USER' in os.environ
        self.real_user = os.environ.get('SUDO_USER') if self.is_sudo else None
        self.real_uid = os.environ.get('SUDO_UID') if self.is_sudo else None
        self.xdg_runtime_dir = f"/run/user/{self.real_uid}" if self.is_sudo else os.environ.get('XDG_RUNTIME_DIR')

    def log(self, message: str):
        """Print message if verbose mode is enabled"""
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _get_pulse_server(self) -> Optional[str]:
        """Get PulseAudio server path, handling sudo case"""
        # If running as root via sudo, connect to the real user's PulseAudio
        if os.geteuid() == 0 and 'SUDO_UID' in os.environ:
            sudo_uid = os.environ['SUDO_UID']
            pulse_socket = f"/run/user/{sudo_uid}/pulse/native"

            # Check if socket exists
            if os.path.exists(pulse_socket):
                self.log(f"Running as root, connecting to user's PulseAudio: {pulse_socket}")
                return f"unix:{pulse_socket}"
            else:
                self.log(f"Warning: User's PulseAudio socket not found at {pulse_socket}")

        # Return None to use default connection
        return None

    def setup(self) -> bool:
        """Initialize keyboard device and microphone connection"""
        # Setup keyboard device
        try:
            self.device = evdev.InputDevice(self.keyboard_device)
            self.log(f"Monitoring keyboard: {self.device.name} ({self.keyboard_device})")
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error: Cannot access keyboard device {self.keyboard_device}: {e}")
            print("Make sure the device exists and you have permission to read it.")
            return False

        # Setup PulseAudio/PipeWire connection
        try:
            pulse_server = self._get_pulse_server()
            if pulse_server:
                self.pulse = pulsectl.Pulse('magic-mute', server=pulse_server)
            else:
                self.pulse = pulsectl.Pulse('magic-mute')
        except Exception as e:
            print(f"Error: Cannot connect to PulseAudio/PipeWire: {e}")
            if os.geteuid() == 0:
                print("Hint: When running as root, make sure the user's PulseAudio/PipeWire is running")
            return False

        # Find microphone source
        self.mic_index = self._find_mic_source()
        if self.mic_index is None:
            print(f"Error: Cannot find microphone source matching '{self.mic_name}'")
            print("\nAvailable sources:")
            self._list_sources()
            return False

        source = self.pulse.source_list()[self.mic_index]
        self.mic_source_name = source.name
        self.log(f"Controlling microphone: {source.description} ({source.name})")

        return True

    def _find_mic_source(self) -> Optional[int]:
        """Find the index of the microphone source by name or description"""
        sources = self.pulse.source_list()

        # Filter out monitor sources (these are for recording output, not real mics)
        real_sources = [(idx, source) for idx, source in enumerate(sources)
                        if '.monitor' not in source.name]

        # Try exact name match first
        for idx, source in real_sources:
            if source.name == self.mic_name:
                return idx

        # Try substring match in name
        for idx, source in real_sources:
            if self.mic_name.lower() in source.name.lower():
                return idx

        # Try substring match in description
        for idx, source in real_sources:
            if self.mic_name.lower() in source.description.lower():
                return idx

        return None

    def _list_sources(self):
        """List all available audio sources (excluding monitors)"""
        sources = self.pulse.source_list()
        for source in sources:
            # Skip monitor sources
            if '.monitor' not in source.name:
                print(f"  - {source.description}")
                print(f"    Name: {source.name}")
                print(f"    Muted: {bool(source.mute)}")
                print()

    def _run_pactl_as_user(self, args: list) -> bool:
        """Run pactl command as the real user (when running via sudo)"""
        env = {
            'XDG_RUNTIME_DIR': self.xdg_runtime_dir,
            'PULSE_RUNTIME_PATH': f"{self.xdg_runtime_dir}/pulse",
        }

        try:
            if self.is_sudo:
                # Run as the actual user
                cmd = ['sudo', '-u', self.real_user] + args
                result = subprocess.run(
                    cmd,
                    env={**os.environ, **env},
                    capture_output=True,
                    text=True,
                    timeout=2
                )
            else:
                # Run directly
                result = subprocess.run(
                    args,
                    env={**os.environ, **env},
                    capture_output=True,
                    text=True,
                    timeout=2
                )

            if result.returncode != 0:
                self.log(f"pactl error: {result.stderr.strip()}")
                return False
            return True

        except Exception as e:
            self.log(f"Error running pactl: {e}")
            return False

    def mute_mic(self):
        """Mute the microphone"""
        if not self.is_muted:
            success = self._run_pactl_as_user(['pactl', 'set-source-mute', self.mic_source_name, '1'])
            if success:
                self.is_muted = True
                self.log("🔇 Microphone MUTED")
            else:
                print(f"Error muting microphone: {self.mic_source_name}")

    def unmute_mic(self):
        """Unmute the microphone"""
        if self.is_muted:
            success = self._run_pactl_as_user(['pactl', 'set-source-mute', self.mic_source_name, '0'])
            if success:
                self.is_muted = False
                self.log("🔊 Microphone UNMUTED")
            else:
                print(f"Error unmuting microphone: {self.mic_source_name}")

    def schedule_unmute(self):
        """Schedule microphone unmute after delay"""
        with self.timer_lock:
            # Cancel existing timer if any
            if self.unmute_timer is not None:
                self.unmute_timer.cancel()

            # Schedule new timer
            self.unmute_timer = threading.Timer(self.unmute_delay, self.unmute_mic)
            self.unmute_timer.start()

    def run(self):
        """Main event loop - monitor keyboard and control microphone"""
        print(f"Magic Mute started - monitoring {self.device.name}")
        print(f"Press Ctrl+C to stop")
        print()

        try:
            # Grab the device to receive all events
            for event in self.device.read_loop():
                # Only process key events (not SYN, MSC, etc.)
                if event.type == evdev.ecodes.EV_KEY:
                    key_event = evdev.categorize(event)

                    # Only react to key down and repeat events (not key up)
                    if key_event.keystate in (evdev.KeyEvent.key_down, evdev.KeyEvent.key_hold):
                        self.log(f"Key pressed: {key_event.keycode}")

                        # Mute microphone immediately
                        self.mute_mic()

                        # Schedule unmute
                        self.schedule_unmute()

        except KeyboardInterrupt:
            print("\n\nStopping Magic Mute...")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        # Cancel any pending unmute timer
        with self.timer_lock:
            if self.unmute_timer is not None:
                self.unmute_timer.cancel()

        # Ensure microphone is unmuted on exit
        if self.is_muted:
            self.unmute_mic()

        # Close PulseAudio connection
        if self.pulse is not None:
            self.pulse.close()

        self.log("Cleanup complete")


def list_keyboards():
    """List all keyboard input devices"""
    print("Available keyboard devices:\n")

    try:
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    except Exception as e:
        print(f"Error listing devices: {e}")
        return

    keyboard_count = 0

    for device in devices:
        try:
            # Check if device has keyboard capabilities
            caps = device.capabilities()
            if evdev.ecodes.EV_KEY in caps:
                keys = caps[evdev.ecodes.EV_KEY]

                # Check for common keyboard keys (not just mouse buttons)
                # Checking for letter keys, number keys, or function keys
                has_letters = any(k in keys for k in range(evdev.ecodes.KEY_Q, evdev.ecodes.KEY_P + 1))
                has_numbers = any(k in keys for k in range(evdev.ecodes.KEY_1, evdev.ecodes.KEY_0 + 1))
                has_function = any(k in keys for k in range(evdev.ecodes.KEY_F1, evdev.ecodes.KEY_F12 + 1))
                has_space = evdev.ecodes.KEY_SPACE in keys

                is_keyboard = has_letters or has_numbers or has_function or has_space

                if is_keyboard:
                    keyboard_count += 1
                    print(f"  {device.path}")
                    print(f"    Name: {device.name}")
                    print(f"    Physical: {device.phys}")
                    print()
        except (PermissionError, OSError) as e:
            # Skip devices we can't access
            continue

    if keyboard_count == 0:
        print("  No keyboard devices found.")
        print("  You may need permission to access input devices.")
        print("  Try running with sudo or check your udev rules.")


def list_microphones():
    """List all microphone sources"""
    print("Available microphone sources:\n")

    # Handle sudo case - connect to user's PulseAudio
    pulse_server = None
    if os.geteuid() == 0 and 'SUDO_UID' in os.environ:
        sudo_uid = os.environ['SUDO_UID']
        pulse_socket = f"/run/user/{sudo_uid}/pulse/native"
        if os.path.exists(pulse_socket):
            pulse_server = f"unix:{pulse_socket}"

    try:
        if pulse_server:
            with pulsectl.Pulse('magic-mute-list', server=pulse_server) as pulse:
                sources = pulse.source_list()
                for source in sources:
                    if '.monitor' not in source.name:
                        print(f"  {source.description}")
                        print(f"    Name: {source.name}")
                        print(f"    Muted: {bool(source.mute)}")
                        print()
        else:
            with pulsectl.Pulse('magic-mute-list') as pulse:
                sources = pulse.source_list()
                for source in sources:
                    if '.monitor' not in source.name:
                        print(f"  {source.description}")
                        print(f"    Name: {source.name}")
                        print(f"    Muted: {bool(source.mute)}")
                        print()
    except Exception as e:
        print(f"Error listing microphones: {e}")
        if os.geteuid() == 0:
            print("Hint: When running as root, make sure the user's PulseAudio/PipeWire is running")


def main():
    parser = argparse.ArgumentParser(
        description="Automatically mute microphone while typing on mechanical keyboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available devices
  %(prog)s --list-keyboards
  %(prog)s --list-mics

  # Run with specific devices
  %(prog)s --keyboard /dev/input/event5 --mic "Headset"

  # Run with custom unmute delay
  %(prog)s -k /dev/input/event5 -m "Headset" -d 3.0 -v
        """
    )

    parser.add_argument(
        '--list-keyboards',
        action='store_true',
        help='List all available keyboard devices and exit'
    )

    parser.add_argument(
        '--list-mics',
        action='store_true',
        help='List all available microphone sources and exit'
    )

    parser.add_argument(
        '-k', '--keyboard',
        type=str,
        help='Path to keyboard device (e.g., /dev/input/event5)'
    )

    parser.add_argument(
        '-m', '--mic',
        type=str,
        help='Microphone source name or substring (e.g., "Headset" or full source name)'
    )

    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=2.0,
        help='Seconds to wait before unmuting after last keystroke (default: 2.0)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Handle listing commands
    if args.list_keyboards:
        list_keyboards()
        return 0

    if args.list_mics:
        list_microphones()
        return 0

    # Validate required arguments
    if not args.keyboard:
        parser.error("--keyboard is required (use --list-keyboards to find your device)")

    if not args.mic:
        parser.error("--mic is required (use --list-mics to find your microphone)")

    # Create and run magic mute
    magic_mute = MagicMute(
        keyboard_device=args.keyboard,
        mic_name=args.mic,
        unmute_delay=args.delay,
        verbose=args.verbose
    )

    if not magic_mute.setup():
        return 1

    magic_mute.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
