# Magic Mute

Here's a Python script to automatically mute your microphone when you are typing on your noisy keyboard. Designed for and tested with Gnome Wayland, but should be good for any Linux desktop environment.

Just in case it isn't obvious, AI helped with the code and also made this cute depiction of our use case:

![Clicky the kitten](clicky.png)

## The Problem

I love mechanical keyboards like my beloved IBM Model M, but they are loud and can disrupt video calls. It's easy to forget to mute yourself while typing notes or multitasking during meetings.

## The Solution

Magic Mute monitors your keyboard device and automatically:
- 🔇 **Mutes** your microphone as soon as you start typing
- 🔊 **Unmutes** your microphone just after you stop typing

Works directly with kernel input devices and PipeWire/PulseAudio, so it's desktop-environment agnostic and it even works with annoying Wayland.

## Features

- 🎯 **Device-specific**: Monitor only your mechanical keyboard, not your laptop's built-in keyboard
- 🎤 **Microphone-specific**: Mute only your headset mic, not your laptop's internal microphone
- ⚡ **Low latency**: Instant muting when you press a key
- 🔧 **Configurable**: Adjust the unmute delay to your preference
- 🪶 **Lightweight**: Python daemon is simple and with minimal dependencies
- ✨ **Graceful**: Automatically unmutes after you exit with Ctrl-C

## Requirements

- Linux with PipeWire or PulseAudio
- Python 3.7+
- Read access to input devices (udev rule or running as appropriate user)

## Installation

1. Clone or download this repository to your desired location:
```bash
git clone https://github.com/swapdisk/magic-mute.git
```

2. Install Python dependencies:
```bash
cd magic-mute 
pip install -r requirements.txt
```

## Finding Your Devices

### Find Your Keyboard Device

List all available keyboard devices:
```bash
./magic_mute.py --list-keyboards
```

Look for your mechanical keyboard and note its name, for example, "IBM Model M" or "HID 04d9:1400". You can use the full name or any substring that uniquely identifies it.

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
-k, --keyboard NAME       Keyboard device name or substring (e.g., "Model M", "HID 04d9")
-m, --mic NAME            Microphone source name or substring (e.g., "Headset")
-d, --delay SECONDS       Seconds to wait before unmuting (default: 1.0)
-r, --retry-interval SEC  Seconds between retries when devices not found (default: 60.0)
--no-retry                Exit if devices not found instead of retrying
-v, --verbose             Enable verbose output
--list-keyboards          List all available keyboard devices
--list-mics               List all available microphone sources
```

## Environment Variables

Configuration can also be provided via environment variables. Command-line arguments take precedence.

```
MAGIC_MUTE_KEYBOARD        Keyboard device name (same as --keyboard)
MAGIC_MUTE_MIC             Microphone source name (same as --mic)
MAGIC_MUTE_DELAY           Unmute delay in seconds (same as --delay)
MAGIC_MUTE_RETRY_INTERVAL  Retry interval in seconds (same as --retry-interval)
```

## Device Permissions

Your user needs read access to the keyboard device file. Typically, this is achieved with `input` group membership. For example:

```bash
sudo usermod -aG input $USER
```

### Important Note for Gnome Wayland Users

If you're using Gnome on Wayland, there's a security gotcha: Gnome deliberately drops the `input` group from your desktop session processes to prevent applications from keylogging via raw input device access. This is intentional security hardening.

**Symptoms:**
- `/etc/group` shows you're in the `input` group
- Running `id` in a terminal window doesn't show the `input` group
- `--list-keyboards` works with `sudo` but not without it
- SSH sessions show the `input` group, but desktop terminals don't

To get around this annoyance, the script automatically handles it by re-executing itself via `sg input` when needed.

## Running on Startup

The script should work under a regular user service on all desktop environments including Gnome Wayland.

### Using systemd User Service

**Step 1:** Create a configuration file at `INSTALL_PATH/magic-mute.conf`:

```bash
MAGIC_MUTE_KEYBOARD="Model M"
MAGIC_MUTE_MIC="Headset"
MAGIC_MUTE_DELAY=1.0
MAGIC_MUTE_RETRY_INTERVAL=60.0
```

Replace the values with your actual device names (use `--list-keyboards` and `--list-mics` to find them).

**Step 2:** Create `~/.config/systemd/user/magic-mute.service`:

```ini
[Unit]
Description=Magic Mute - Auto-mute mic while typing
After=pipewire.service

[Service]
Type=simple
EnvironmentFile=-INSTALL_PATH/magic-mute.conf
ExecStart=INSTALL_PATH/magic_mute.py
Restart=on-failure
RestartSec=5
KillSignal=SIGINT

[Install]
WantedBy=default.target
```

Replace `INSTALL_PATH` with the full path to where you installed magic-mute.

The `-` prefix before the path makes the config file optional - the service will work with command-line args if the file doesn't exist.

**Step 3:** Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable magic-mute.service
systemctl --user start magic-mute.service
```

**Changing configuration:**

To change keyboard or microphone settings, just edit `magic-mute.conf` and restart:
```bash
systemctl --user restart magic-mute.service
```

No need to run `daemon-reload` when only the config file changes!

**Check status:**
```bash
systemctl --user status magic-mute.service
```

**View logs:**
```bash
journalctl --user -u magic-mute.service -f
```

**Alternative: Command-line arguments**

You can also configure via command-line arguments in the service file instead of using a config file:

```ini
ExecStart=INSTALL_PATH/magic_mute.py --keyboard "Model M" --mic "Headset"
```

Command-line arguments take precedence over environment variables, so you can mix both approaches.

## How It Works

1. **Keyboard Discovery**: Searches for your keyboard by name across all input devices, so it works even if the device path changes between reboots

2. **Device Retry Logic**: If devices aren't found (e.g., laptop undocked), waits and retries every 60 seconds instead of failing. Perfect for dock/undock scenarios - no systemd restart spam!

3. **Keyboard Monitoring**: Uses the `evdev` library to read events directly from the keyboard device at the kernel level (`/dev/input/eventX`)

4. **Microphone Control**: Uses `pulsectl` to interface with PipeWire/PulseAudio's API for muting/unmuting audio sources

5. **Smart Timing**: When a key is pressed:
   - Immediately mutes the microphone
   - Starts/resets a countdown timer
   - When the timer expires (no keys pressed for N seconds), unmutes the microphone

6. **Desktop Environment Agnostic**: Works on Wayland, Xorg, or even headless systems because it operates at the kernel device level

## Troubleshooting

### "Waiting for keyboard..." / Devices not found
- By default, the script will retry every 60 seconds if devices aren't found
- This is normal when your laptop is undocked or devices are unplugged
- The script will automatically start working when you reconnect the devices
- Use `--no-retry` if you want it to exit immediately instead of waiting
- Check available keyboards with `--list-keyboards`
- Verify permissions (see Device Permissions section)
- Make sure you're using a substring that uniquely identifies your keyboard

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

## License

MIT
