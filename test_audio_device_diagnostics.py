"""
Diagnostic script to test sounddevice playback callback for underflow, jitter, and blocksize.
"""

import time
import numpy as np
import sounddevice as sd

def test_device(dev_idx, blocksize, latency):
    print(f"\n--- Testing Device [{dev_idx}] '{sd.query_devices(dev_idx)['name']}' (blocksize={blocksize}, latency={latency}) ---")
    sr = 48000
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False, dtype=np.float32)
    # 440 Hz test tone
    tone = 0.3 * np.sin(2 * np.pi * 440.0 * t)
    audio = np.column_stack((tone, tone))
    
    pos = 0
    statuses = []
    callback_count = 0
    t_start = time.perf_counter()

    def callback(outdata, frames, time_info, status):
        nonlocal pos, callback_count
        callback_count += 1
        if status:
            statuses.append((status, time.perf_counter() - t_start))
        if pos < len(audio):
            chunk = audio[pos : pos + frames]
            if len(chunk) < frames:
                outdata[:len(chunk)] = chunk
                outdata[len(chunk):] = 0
            else:
                outdata[:] = chunk
            pos += frames
        else:
            outdata[:] = 0

    try:
        stream = sd.OutputStream(
            samplerate=sr,
            channels=2,
            dtype="float32",
            device=dev_idx,
            blocksize=blocksize,
            latency=latency,
            callback=callback,
        )
        stream.start()
        time.sleep(3.2)
        stream.stop()
        stream.close()
        print(f"-> Total callbacks: {callback_count}")
        print(f"-> Status warnings (underflows/overflows): {len(statuses)}")
        for st, ts in statuses[:10]:
            print(f"   Warning at {ts:.3f}s: {st}")
    except Exception as e:
        print(f"-> Failed to open device: {e}")

if __name__ == "__main__":
    print("Testing device 18 with blocksize=800:")
    test_device(18, blocksize=800, latency="high")

    print("\nTesting device 18 with blocksize=0 (driver native):")
    test_device(18, blocksize=0, latency="high")

    print("\nTesting default DirectSound device 15 with blocksize=0:")
    test_device(15, blocksize=0, latency="high")

    print("\nTesting default MME device 7 with blocksize=0:")
    test_device(7, blocksize=0, latency="high")
