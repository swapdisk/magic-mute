# Magic Mute

Automatically mute your microphone while typing on your mechanical keyboard. Designed for Wayland environments on Linux.

## The Problem

Mechanical keyboards (like the IBM Model M) are loud and can disrupt video calls. It's easy to forget to mute yourself while typing notes or multitasking during meetings.

## The Solution

Magic Mute monitors your keyboard device and automatically:
- **Mutes** your microphone as soon as you start typing
- **Unmutes** your microphone a few seconds after you stop typing

Works directly with kernel input devices and PipeWire/PulseAudio, making it desktop-environment agnostic (perfect for Wayland).

## Features

- 🎯 **Device-specific**: Monitor only your mechanical keyboard, not your laptop's built-in keyboard
- 🎤 **Microphone-specific**: Mute only your headset mic, not your laptop's internal microphone
- ⚡ **Low latency**: Instant muting when you press a key
- 🔧 **Configurable**: Adjust the unmute delay to your preference
- 🪶 **Lightweight**: Simple Python daemon with minimal dependencies

## Requirements

- Linux with PipeWire or PulseAudio
- Python 3.7+
- Read access to input devices (udev rule or running as appropriate user)

## Installation

1. Clone or download this repository to your desired location:
```bash
cd INSTALL_PATH
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Make the script executable:
```bash
chmod +x magic_mute.py
```

## Finding Your Devices

### Find Your Keyboard Device

List all available keyboard devices:
```bash
./magic_mute.py --list-keyboards
```

Look for your mechanical keyboard (e.g., "IBM Model M", "HID 04d9:1400") and note its name. You can use the full name or any substring that uniquely identifies it.

### Find Your Microphone

List all available microphone sources:
```bash
./magic_mute.py --list-mics
```

Look for your headset or desired microphone and note its name or description.

## Usage

### Basic Usage

```bash
./magic_mute.py --keyboard "Model M" --mic "Headset"
```

Or using short options:
```bash
./magic_mute.py -k "HID 04d9" -m "Headset"
```

### With Custom Unmute Delay

Wait 3 seconds after typing stops before unmuting:
```bash
./magic_mute.py -k "Model M" -m "Headset" -d 3.0
```

### Verbose Mode

See what's happening in real-time:
```bash
./magic_mute.py -k "Model M" -m "Headset" -v
```

### Complete Example

```bash
./magic_mute.py \
  --keyboard "Model M" \
  --mic "USB Audio Device Mono" \
  --delay 2.5 \
  --verbose
```

## Command-Line Options

```
-k, --keyboard NAME    Keyboard device name or substring (e.g., "Model M", "HID 04d9")
-m, --mic NAME         Microphone source name or substring (e.g., "Headset")
-d, --delay SECONDS    Seconds to wait before unmuting (default: 1.0)
-v, --verbose          Enable verbose output
--list-keyboards       List all available keyboard devices
--list-mics           List all available microphone sources
```

## Device Permissions

Your user needs read-write access to the keyboard device file. If you get a permission error, you have a few options:

### Important Note for Gnome Wayland Users

**If you're using Gnome on Wayland, there's a security gotcha:** Gnome deliberately drops the `input` group from your desktop session processes to prevent applications from keylogging via raw input device access. This is intentional security hardening.

**Symptoms:**
- `/etc/group` shows you're in the `input` group
- Running `id` in a terminal doesn't show the `input` group
- `--list-keyboards` works with `sudo` but not without it
- SSH sessions show the `input` group, but desktop terminals don't

**Solution:** Use a systemd **system service** (not user service) instead of running manually. See the "Running on Startup" section below for the correct configuration.

### Option 1: udev Rule + systemd System Service (Recommended)

Create a udev rule to grant the `input` group access to input devices. Create `/etc/udev/rules.d/99-input-events.rules`:

```
KERNEL=="event*", SUBSYSTEM=="input", GROUP="input", MODE="0660"
```

Then add your user to the `input` group:
```bash
sudo usermod -a -G input $USER
```

Reload udev rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

**Note:** Even with this setup, you may not be able to run the script manually from a Gnome desktop session due to the security feature mentioned above. The script will automatically re-execute itself via `sg input` when needed to gain the necessary permissions.

### Option 2: Run as Root (Not Recommended for Production)

For testing only:
```bash
sudo ./magic_mute.py -k /dev/input/event5 -m "Headset"
```

## Running on Startup

### Using systemd User Service (Recommended)

The script automatically handles the `input` group permission issue by re-executing itself via `sg input` when needed, so it works as a regular user service on all desktop environments including Gnome Wayland.

Create `~/.config/systemd/user/magic-mute.service`:

```ini
[Unit]
Description=Magic Mute - Auto-mute mic while typing
After=pipewire.service

[Service]
Type=simple
ExecStart=INSTALL_PATH/magic_mute.py \
  --keyboard "Model M" \
  --mic "Headset" \
  --delay 1.0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Replace `INSTALL_PATH` with the full path to where you installed magic-mute, and adjust the keyboard/mic parameters to match your devices.

Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable magic-mute.service
systemctl --user start magic-mute.service
```

Check status:
```bash
systemctl --user status magic-mute.service
```

View logs:
```bash
journalctl --user -u magic-mute.service -f
```

## How It Works

1. **Keyboard Discovery**: Searches for your keyboard by name across all input devices, so it works even if the device path changes between reboots

2. **Keyboard Monitoring**: Uses the `evdev` library to read events directly from the keyboard device at the kernel level (`/dev/input/eventX`)

3. **Microphone Control**: Uses `pulsectl` to interface with PipeWire/PulseAudio's API for muting/unmuting audio sources

4. **Smart Timing**: When a key is pressed:
   - Immediately mutes the microphone
   - Starts/resets a countdown timer
   - When the timer expires (no keys pressed for N seconds), unmutes the microphone

5. **Desktop Environment Agnostic**: Works on Wayland, X11, or even headless systems because it operates at the kernel device level

## Troubleshooting

### "Cannot find keyboard device"
- Check available keyboards with `--list-keyboards`
- Verify permissions (see Device Permissions section)
- Make sure you're using a substring that uniquely identifies your keyboard
- Try using a more specific part of the name (e.g., "04d9" instead of just "HID")

### "Cannot find microphone source"
- Check available sources with `--list-mics`
- Try using a substring of the microphone name (e.g., "Headset" instead of full name)
- Make sure PipeWire/PulseAudio is running

### Microphone not muting
- Verify the mic name matches with `--list-mics`
- Run with `--verbose` to see what's happening
- Check that PipeWire/PulseAudio is controlling the correct device

### Wrong keyboard being monitored
- Use `--list-keyboards` to see all available keyboards
- Make your search string more specific to match only your mechanical keyboard
- Check the "Name" and "Physical" fields to identify your mechanical keyboard uniquely

## Technical Details

- Written in Python 3
- Uses `evdev` for keyboard event monitoring (works on Wayland)
- Uses `pulsectl` for PipeWire/PulseAudio control
- Threading for non-blocking unmute timers
- Graceful shutdown on Ctrl+C with automatic unmute

## License

This project is provided as-is for personal use.

## Contributing

This is a personal project, but suggestions and improvements are welcome!
