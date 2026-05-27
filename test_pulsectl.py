#!/usr/bin/env python3
"""
Simple test to debug pulsectl muting issue
"""

import sys
import pulsectl

def main():
    mic_name = "Savi 7xx Mono"

    print(f"Testing pulsectl mute/unmute for: {mic_name}")
    print()

    try:
        # Connect to PulseAudio
        print("Connecting to PulseAudio...")
        pulse = pulsectl.Pulse('test-pulsectl')
        print("✓ Connected successfully")
        print()

        # List sources
        print("Available sources:")
        sources = pulse.source_list()
        for idx, source in enumerate(sources):
            if '.monitor' not in source.name:
                print(f"  [{idx}] {source.description}")
                print(f"      Name: {source.name}")
                print(f"      Index: {source.index}")
                print(f"      Muted: {bool(source.mute)}")
                print()

        # Find our microphone
        print(f"Looking for microphone matching '{mic_name}'...")
        mic_index = None

        real_sources = [source for source in sources if '.monitor' not in source.name]

        for source in real_sources:
            if mic_name.lower() in source.description.lower():
                mic_index = source.index  # Use PulseAudio index, not enumeration index!
                print(f"✓ Found at PulseAudio index {source.index}: {source.description}")
                print(f"  Source name: {source.name}")
                break

        if mic_index is None:
            print("✗ Microphone not found!")
            return 1

        print()

        # Test muting
        print("Testing MUTE...")
        try:
            result = pulse.source_mute(mic_index, 1)
            print(f"  source_mute() returned: {result}")

            # Check if it actually muted - find source by index
            sources = pulse.source_list()
            source = next((s for s in sources if s.index == mic_index), None)
            if source:
                is_muted = bool(source.mute)
                print(f"  Microphone is now muted: {is_muted}")

                if is_muted:
                    print("  ✓ Mute SUCCESS")
                else:
                    print("  ✗ Mute FAILED - source not actually muted")
            else:
                print("  ✗ Could not find source to verify mute state")

        except Exception as e:
            print(f"  ✗ Mute FAILED with exception: {e}")
            print(f"  Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()

        print()

        # Test unmuting
        print("Testing UNMUTE...")
        try:
            result = pulse.source_mute(mic_index, 0)
            print(f"  source_mute() returned: {result}")

            # Check if it actually unmuted - find source by index
            sources = pulse.source_list()
            source = next((s for s in sources if s.index == mic_index), None)
            if source:
                is_muted = bool(source.mute)
                print(f"  Microphone is now muted: {is_muted}")

                if not is_muted:
                    print("  ✓ Unmute SUCCESS")
                else:
                    print("  ✗ Unmute FAILED - source still muted")
            else:
                print("  ✗ Could not find source to verify mute state")

        except Exception as e:
            print(f"  ✗ Unmute FAILED with exception: {e}")
            print(f"  Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()

        pulse.close()

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
