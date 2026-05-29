#!/usr/bin/env python3
"""
Magic Mute - Automatically mute microphone while typing on mechanical keyboard

Monitors a specific keyboard device and automatically mutes/unmutes a specified
microphone when typing starts/stops. Designed for Wayland environments.
"""

import argparse
import grp
import os
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
        keyboard_name: str,
        mic_name: str,
        unmute_delay: float = 1.0,
        retry_interval: float = 60.0,
        no_retry: bool = False,
        verbose: bool = False,
    ):
        self.keyboard_name = keyboard_name
        self.mic_name = mic_name
        self.unmute_delay = unmute_delay
        self.retry_interval = retry_interval
        self.no_retry = no_retry
        self.verbose = verbose

        self.device: Optional[evdev.InputDevice] = None
        self.device_path: Optional[str] = None
        self.pulse: Optional[pulsectl.Pulse] = None
        self.mic_index: Optional[int] = None  # PulseAudio source index, not list position

        self.is_muted = False
        self.unmute_timer: Optional[threading.Timer] = None
        self.timer_lock = threading.Lock()

        self.devices_found = False

    def log(self, message: str, force: bool = False):
        """Print message if verbose mode is enabled or force is True"""
        if self.verbose or force:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _find_keyboard_device(self) -> Optional[str]:
        """Find keyboard device path by name"""
        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        except Exception as e:
            print(f"Error listing devices: {e}")
            return None

        # Filter to keyboard devices only
        keyboards = []
        for device in devices:
            try:
                caps = device.capabilities()
                if evdev.ecodes.EV_KEY in caps:
                    keys = caps[evdev.ecodes.EV_KEY]
                    has_letters = any(k in keys for k in range(evdev.ecodes.KEY_Q, evdev.ecodes.KEY_P + 1))
                    has_numbers = any(k in keys for k in range(evdev.ecodes.KEY_1, evdev.ecodes.KEY_0 + 1))
                    has_function = any(k in keys for k in range(evdev.ecodes.KEY_F1, evdev.ecodes.KEY_F12 + 1))
                    has_space = evdev.ecodes.KEY_SPACE in keys

                    if has_letters or has_numbers or has_function or has_space:
                        keyboards.append(device)
            except (PermissionError, OSError):
                continue

        # Try exact name match first
        for device in keyboards:
            if device.name == self.keyboard_name:
                return device.path

        # Try substring match in name
        for device in keyboards:
            if self.keyboard_name.lower() in device.name.lower():
                return device.path

        # Try substring match in physical address
        for device in keyboards:
            if device.phys and self.keyboard_name.lower() in device.phys.lower():
                return device.path

        return None

    def _list_keyboard_devices(self):
        """List available keyboard devices for error messages"""
        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        except Exception:
            return

        print("  Available keyboards:")
        for device in devices:
            try:
                caps = device.capabilities()
                if evdev.ecodes.EV_KEY in caps:
                    keys = caps[evdev.ecodes.EV_KEY]
                    has_letters = any(k in keys for k in range(evdev.ecodes.KEY_Q, evdev.ecodes.KEY_P + 1))
                    has_numbers = any(k in keys for k in range(evdev.ecodes.KEY_1, evdev.ecodes.KEY_0 + 1))
                    has_function = any(k in keys for k in range(evdev.ecodes.KEY_F1, evdev.ecodes.KEY_F12 + 1))
                    has_space = evdev.ecodes.KEY_SPACE in keys

                    if has_letters or has_numbers or has_function or has_space:
                        print(f"    - {device.name}")
                        print(f"      Path: {device.path}")
                        if device.phys:
                            print(f"      Physical: {device.phys}")
                        print()
            except (PermissionError, OSError):
                continue

    def setup(self, show_details: bool = True) -> bool:
        """Initialize keyboard device and microphone connection"""
        # Clean up any existing connections first
        if self.pulse is not None:
            try:
                self.pulse.close()
            except:
                pass
            self.pulse = None
            self.mic_index = None

        if self.device is not None:
            try:
                self.device.close()
            except:
                pass
            self.device = None
            self.device_path = None

        # Find keyboard device by name
        self.device_path = self._find_keyboard_device()
        if self.device_path is None:
            if show_details:
                print(f"Error: Cannot find keyboard device matching '{self.keyboard_name}'")
                print()
                self._list_keyboard_devices()
            return False

        # Setup keyboard device
        try:
            self.device = evdev.InputDevice(self.device_path)
            self.log(f"Monitoring keyboard: {self.device.name} ({self.device_path})", force=True)
        except (FileNotFoundError, PermissionError) as e:
            if show_details:
                print(f"Error: Cannot access keyboard device {self.device_path}: {e}")
                print("Make sure you have permission to read it.")
            return False

        # Setup PulseAudio/PipeWire connection (fresh connection each time)
        try:
            self.pulse = pulsectl.Pulse('magic-mute')
        except Exception as e:
            if show_details:
                print(f"Error: Cannot connect to PulseAudio/PipeWire: {e}")
            return False

        # Find microphone source (index may have changed if device was reconnected)
        self.mic_index = self._find_mic_source()
        if self.mic_index is None:
            if show_details:
                print(f"Error: Cannot find microphone source matching '{self.mic_name}'")
                print("\nAvailable sources:")
                self._list_sources()
            return False

        # Find the source object by its index for logging
        source = next((s for s in self.pulse.source_list() if s.index == self.mic_index), None)
        if source:
            self.log(f"Controlling microphone: {source.description} ({source.name})", force=True)
        else:
            self.log(f"Controlling microphone index: {self.mic_index}", force=True)

        return True

    def _find_mic_source(self) -> Optional[int]:
        """Find the PulseAudio index of the microphone source by name or description"""
        sources = self.pulse.source_list()

        # Filter out monitor sources (these are for recording output, not real mics)
        real_sources = [source for source in sources if '.monitor' not in source.name]

        # Try exact name match first
        for source in real_sources:
            if source.name == self.mic_name:
                return source.index

        # Try substring match in name
        for source in real_sources:
            if self.mic_name.lower() in source.name.lower():
                return source.index

        # Try substring match in description
        for source in real_sources:
            if self.mic_name.lower() in source.description.lower():
                return source.index

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

    def mute_mic(self) -> bool:
        """Mute the microphone. Returns False if operation failed (device gone)."""
        if not self.is_muted:
            try:
                self.pulse.source_mute(self.mic_index, 1)
                self.is_muted = True
                self.log("🔇 Microphone MUTED")
                return True
            except Exception as e:
                self.log(f"Error muting microphone: {e}", force=True)
                return False
        return True

    def unmute_mic(self) -> bool:
        """Unmute the microphone. Returns False if operation failed (device gone)."""
        if self.is_muted:
            try:
                self.pulse.source_mute(self.mic_index, 0)
                self.is_muted = False
                self.log("🔊 Microphone UNMUTED")
                return True
            except Exception as e:
                self.log(f"Error unmuting microphone: {e}", force=True)
                return False
        return True

    def schedule_unmute(self):
        """Schedule microphone unmute after delay"""
        with self.timer_lock:
            # Cancel existing timer if any
            if self.unmute_timer is not None:
                self.unmute_timer.cancel()

            # Schedule new timer
            # Note: If unmute fails, we'll catch it on the next mute attempt
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
                        if not self.mute_mic():
                            # Microphone operation failed - device disconnected
                            self.log("Microphone disconnected", force=True)
                            return False  # Signal to retry

                        # Schedule unmute
                        self.schedule_unmute()

        except (OSError, IOError) as e:
            # Device disconnected while running
            self.log(f"Device disconnected: {e}", force=True)
            return False  # Signal to retry
        except KeyboardInterrupt:
            print("\n\nStopping Magic Mute...")
            return True  # Signal clean exit
        finally:
            self.cleanup()

    def run_with_retry(self):
        """Main loop with device retry logic"""
        print("Magic Mute started")
        print("Press Ctrl+C to stop")
        print()

        first_attempt = True

        try:
            while True:
                # Try to setup devices
                if self.setup(show_details=first_attempt):
                    self.devices_found = True

                    # Run monitoring loop
                    clean_exit = self.run()

                    if clean_exit:
                        # User pressed Ctrl+C, exit normally
                        break
                    else:
                        # Device disconnected, go back to retry mode
                        self.devices_found = False
                        self.log("Devices disconnected, waiting for reconnection...", force=True)
                        first_attempt = False

                        if self.no_retry:
                            print("Device disconnected and --no-retry specified, exiting")
                            break

                        time.sleep(self.retry_interval)
                        self.log("Retrying device detection...", force=False)
                else:
                    # Devices not found
                    if first_attempt:
                        print(f"Waiting for keyboard '{self.keyboard_name}' and microphone '{self.mic_name}'...")
                        first_attempt = False

                    if self.no_retry:
                        print("Devices not found and --no-retry specified, exiting")
                        break

                    # Sleep and retry
                    time.sleep(self.retry_interval)
                    self.log("Retrying device detection...", force=False)

        except KeyboardInterrupt:
            print("\n\nStopping Magic Mute...")
        finally:
            if self.devices_found:
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


def has_input_group() -> bool:
    """Check if current process has input group membership"""
    try:
        input_gid = grp.getgrnam('input').gr_gid
        return input_gid in os.getgroups()
    except KeyError:
        # input group doesn't exist
        return False


def reexec_with_input_group():
    """Re-execute this script with input group using sg command"""
    import shlex

    # Build the command line for re-execution
    script_path = os.path.abspath(__file__)
    args = sys.argv[1:]  # Skip script name

    # Properly quote each argument
    quoted_args = [shlex.quote(arg) for arg in args]
    cmd_string = f'{shlex.quote(script_path)} {" ".join(quoted_args)}'

    # Build command to run via sg
    cmd = ['sg', 'input', '-c', cmd_string]

    print("Input group not available in current session.")
    print("Re-executing with input group permissions...")
    print()

    # Replace current process with sg command
    os.execvp('sg', cmd)


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
        if not has_input_group():
            print("  Hint: You need to be in the 'input' group. Add yourself with:")
            print("        sudo usermod -a -G input $USER")
            print("  Then log out and log back in, or run this script with sg:")
            print(f"        sg input -c '{sys.argv[0]} --list-keyboards'")


def list_microphones():
    """List all microphone sources"""
    print("Available microphone sources:\n")

    try:
        with pulsectl.Pulse('magic-mute-list') as pulse:
            sources = pulse.source_list()
            for source in sources:
                # Skip monitor sources (these are for recording output)
                if '.monitor' not in source.name:
                    print(f"  {source.description}")
                    print(f"    Name: {source.name}")
                    print(f"    Muted: {bool(source.mute)}")
                    print()
    except Exception as e:
        print(f"Error listing microphones: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Automatically mute microphone while typing on mechanical keyboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available devices
  %(prog)s --list-keyboards
  %(prog)s --list-mics

  # Run with specific devices (by name, not path)
  %(prog)s --keyboard "Model M" --mic "Headset"

  # Run with custom unmute delay
  %(prog)s -k "HID 04d9" -m "Headset" -d 3.0 -v

  # Run with no retry (exit if devices not found)
  %(prog)s -k "Model M" -m "Headset" --no-retry
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
        help='Keyboard device name or substring (e.g., "Model M" or "HID 04d9:1400")'
    )

    parser.add_argument(
        '-m', '--mic',
        type=str,
        help='Microphone source name or substring (e.g., "Headset" or full source name)'
    )

    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=1.0,
        help='Seconds to wait before unmuting after last keystroke (default: 1.0)'
    )

    parser.add_argument(
        '-r', '--retry-interval',
        type=float,
        default=60.0,
        help='Seconds to wait between retries when devices are not found (default: 60.0)'
    )

    parser.add_argument(
        '--no-retry',
        action='store_true',
        help='Exit immediately if devices are not found instead of retrying'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Handle listing commands (don't need input group for listing mics)
    if args.list_mics:
        list_microphones()
        return 0

    if args.list_keyboards:
        # Check if we have input group, re-exec if needed
        if not has_input_group():
            reexec_with_input_group()
            # If we get here, exec failed
            print("\nFailed to re-execute with input group.")
            print("You can run manually with: sg input -c './magic_mute.py --list-keyboards'")
            return 1

        list_keyboards()
        return 0

    # Get configuration from args or environment variables (args take precedence)
    keyboard = args.keyboard or os.environ.get('MAGIC_MUTE_KEYBOARD')
    mic = args.mic or os.environ.get('MAGIC_MUTE_MIC')
    delay = args.delay if args.delay != 1.0 else float(os.environ.get('MAGIC_MUTE_DELAY', '1.0'))
    retry_interval = args.retry_interval if args.retry_interval != 60.0 else float(os.environ.get('MAGIC_MUTE_RETRY_INTERVAL', '60.0'))

    # Validate required arguments
    if not keyboard:
        parser.error("--keyboard or MAGIC_MUTE_KEYBOARD environment variable is required (use --list-keyboards to find your device)")

    if not mic:
        parser.error("--mic or MAGIC_MUTE_MIC environment variable is required (use --list-mics to find your microphone)")

    # Check if we have input group for main operation
    if not has_input_group():
        reexec_with_input_group()
        # If we get here, exec failed
        print("\nFailed to re-execute with input group.")
        print(f"You can run manually with: sg input -c '{' '.join(sys.argv)}'")
        return 1

    # Create and run magic mute
    magic_mute = MagicMute(
        keyboard_name=keyboard,
        mic_name=mic,
        unmute_delay=delay,
        retry_interval=retry_interval,
        no_retry=args.no_retry,
        verbose=args.verbose
    )

    magic_mute.run_with_retry()
    return 0


if __name__ == '__main__':
    sys.exit(main())
