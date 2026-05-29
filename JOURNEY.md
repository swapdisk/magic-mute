# The Magic Mute Journey: A 2026 Human-AI Collaboration

**May 28, 2026**

*In which a beloved IBM Model M keyboard from the 1980s meets modern video conferencing, and Claude Sonnet 4.5 helps solve the problem it created.*

## The Problem

I have an IBM Model M keyboard. It's loud. It's clicky. It's glorious. I also have video conference calls where colleagues frequently ask me to mute while typing.

The solution seemed obvious: automatically mute the microphone when I'm typing on the Model M, and unmute shortly after I stop. Surely someone had solved this already?

## The Research Phase

We started by searching for existing solutions:
- **Hushboard** - Perfect concept, but X11-only (I'm running Gnome Wayland)
- **Automute** - Close, but requires a custom kernel module (too invasive)
- Various manual keyboard shortcut solutions (defeats the purpose)

Conclusion: Time to build our own.

## The Build: A Comedy of Edge Cases

### Act I: The Simple Version

"Just read keyboard events with evdev and mute with PulseAudio. Easy!"

And it was easy... until we tried to actually run it.

### Act II: The Permission Saga

**The Gnome Wayland Security Gotcha**: Turns out Gnome deliberately drops the `input` group from desktop session processes. This is good security (prevents keylogging) but annoying for legitimate use cases like ours.

**First attempt**: Run with sudo. This spiraled into a glorious mess of:
- Sudo can read keyboards ✓
- But sudo can't talk to user's PulseAudio ✗
- Try connecting sudo to user's PA socket with environment variables
- Try running pactl commands via `sudo -u` 
- Connection refused errors everywhere

**Git interlude**: "btw, sorry for not starting this with git in the first place!" - We initialized git right before the rollback. Good timing.

**The rollback**: "Let's roll back this whole mess." - We nuked the sudo approach and went with `sg input` to re-exec with the input group. Much cleaner. Works on Wayland.

### Act III: The Index That Changed

**The pulsectl mystery**: Muting worked in testing, failed in production. Error code: 2, 4, 6...

Debugging revealed the smoking gun: We were passing Python's enumerate index (0, 1, 2...) to `source_mute()`, but it wanted PulseAudio's actual source index (4, 5, 7, 9...). One `source.index` later, everything worked.

*Irony: Me kindly helping AI debug its own confusion. How very human.*

### Act IV: The Dock/Undock Problem

"What if I take my laptop on the road?"

Without the Model M and headset plugged in, the systemd service would fail, restart every 5 seconds, spam the journal, and eventually hit rate limiting. Not good.

**The solution**: Built-in retry logic. The daemon now:
- Waits silently for devices when undocked
- Detects device reconnection mid-run
- Handles both keyboard AND microphone disappearing
- No systemd restart spam
- Just works when you dock/undock

### Act V: The Configuration Evolution

From hardcoded paths to device names to environment variables:
1. Started with device paths (`/dev/input/event5`) - breaks on reboot
2. Switched to device names ("Model M") - survives reboots
3. Added environment variable support - change config without editing service file or running daemon-reload

The final form: `EnvironmentFile=-magic-mute.conf` with the `-` making it optional. Beautiful.

### Act VI: The Graceful Shutdown

"One last thing..." - `systemctl stop` wasn't unmuting the mic. SIGTERM vs SIGINT issue. One line fix: `KillSignal=SIGINT` in the service file. Now stopping the service properly unmutes.

## The Technical Details

What we built:
- Python daemon using `evdev` for keyboard monitoring
- `pulsectl` library for PipeWire/PulseAudio control
- Device discovery by name (not path)
- Automatic retry with 60s interval when devices missing
- Handles mid-run disconnection gracefully
- Environment variable + command-line arg configuration
- Works on Wayland via `sg input` re-exec trick
- Proper systemd integration with graceful shutdown

What we learned:
- Gnome Wayland has security features that seem annoying until you remember why they exist
- Sudo is not always the answer
- Python list indices ≠ PulseAudio source indices
- Real-world usage patterns (dock/undock) matter more than happy-path testing
- Git rollback is your friend
- The `-` prefix in systemd EnvironmentFile is a beautiful thing

## The Collaboration Pattern

**Human provides**:
- Real-world problem and use cases
- "This doesn't work" feedback
- Edge case discovery ("what if I undock?")
- Design decisions ("let's use env vars")
- Domain knowledge (Gnome security behavior)

**AI provides**:
- Code implementation
- Documentation
- Research on existing solutions
- Debugging suggestions
- "Here are 3 approaches" options

**Together we**:
- Iterated rapidly (sudo attempt → rollback → sg solution)
- Caught bugs (index confusion)
- Handled edge cases (retry logic, device reconnection)
- Made it production-ready

## The Result

After a full day of use: **Nobody complained about my typing.**

The IBM Model M lives on, clickity-clacking away in blessed silence (to everyone else on the call).

## Reflections on Human-AI Coding in 2026

**What worked well**:
- Fast iteration - try an approach, see it fail, pivot quickly
- Claude could implement while I tested/debugged
- Explaining complex issues (Gnome Wayland security) and getting immediate code solutions
- "Let me check that approach first" - quick validation before committing
- The rollback: I suggested it, AI agreed with no ego involved, clean slate

**What was interesting**:
- I still needed to understand what was happening (the pulsectl index bug)
- Testing required real hardware (the Model M, the headset, the dock)
- Real-world use revealed issues testing didn't (device disconnection)
- Git history (alpha branch) shows the messy reality: commits like "Save messy sudo version before rollback"

**The irony**:
- Using AI to write code that mutes microphones while typing
- A keyboard from 1984 requiring a solution built with 2026 AI
- "annoying Wayland" making it into the final README
- The most elegant solution came after rolling back the clever one

## Files of Note

- `magic_mute.py` - 570 lines of Python that just works
- `README.md` - Includes "Clicky the kitten" AI-generated artwork
- `test_pulsectl.py` - The debugging script that found the index bug
- `JOURNEY.md` - You're reading it

## The Final Word

Some problems are timeless: loud keyboards, video calls, forgetting to mute. Some solutions are very 2026: asking an AI to help you write a Python daemon with retry logic and systemd integration.

Would I have built this without Claude? Probably eventually. Would it have taken all day instead of a few hours? Definitely. Would I have gone down the sudo rabbit hole and then had the discipline to cleanly roll it back? Maybe not.

The collaboration worked because I knew what I wanted to build, and Claude knew how to build it. Together we took it step-by-step handling the messy reality of permissions, device indices, Wayland quirks, and real-world usage patterns.

And now my coworkers can enjoy meetings in peace, while I type away on a keyboard older than many of them (but not me).

**Mission accomplished.** ✨

---

*Written by Bob Mader with assistance from Claude Sonnet 4.5*

*Committed to git on May 28, 2026*

*The Model M clicketh on*
