#!/usr/bin/env python3
"""WASAPI loopback recorder for iTEST assistant.

Captures the digital audio stream that is being rendered to a speaker endpoint.
This is equivalent to putting a recorder next to the speaker: it does NOT touch
the web page, the audio element, or any network request.

Requires: pip install soundcard (brings numpy + cffi). Windows 10/11 only.

Examples:
  python record_loopback.py --list
  python record_loopback.py --out audio/cap.wav --seconds 12 --play audio/ref.wav
  python record_loopback.py --out audio/cap.wav --seconds 12 --device "Senary"
"""
import argparse
import json
import os
import sys
import threading
import wave

import numpy as np
import soundcard as sc

REF_TEXT = ""


def fail(msg, code=1):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(code)


def loopback_devices():
    return [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]


def pick_device(fragment):
    cands = loopback_devices()
    if fragment:
        cands = [m for m in cands if fragment.lower() in m.name.lower()]
        if not cands:
            fail("no loopback device matches %r; available: %s" % (
                fragment, [m.name for m in loopback_devices()]))
        return cands[0]
    spk = sc.default_speaker()
    match = [m for m in cands if m.id == spk.id]
    return match[0] if match else cands[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="output wav path")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--device", default=None,
                    help="substring of the loopback device name; default = current default speaker")
    ap.add_argument("--play", default=None,
                    help="wav to play asynchronously right after recording starts")
    ap.add_argument("--samplerate", type=int, default=48000)
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print(json.dumps({
            "ok": True,
            "default_speaker": sc.default_speaker().name,
            "loopback_devices": [{"name": m.name, "id": m.id} for m in loopback_devices()],
        }, ensure_ascii=False, indent=2))
        return

    if not args.out:
        fail("--out is required (or use --list)")

    mic = pick_device(args.device)
    nframes = int(args.samplerate * args.seconds)

    player = None
    if args.play:
        if not os.path.isfile(args.play):
            fail("play file not found: " + args.play)
        import winsound

        def _play():
            try:
                winsound.PlaySound(args.play, winsound.SND_FILENAME)
            except Exception as ex:
                print("play error: %s" % ex, file=sys.stderr)

        player = threading.Thread(target=_play, daemon=True)

    if player:
        player.start()

    try:
        data = mic.record(samplerate=args.samplerate, numframes=nframes,
                          channels=args.channels)
    except Exception as ex:
        fail("record failed: %s: %s" % (type(ex).__name__, ex))

    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    ch = data.shape[1]
    mono = data.mean(axis=1)
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(mono ** 2)))
    nonzero = float(np.mean(np.abs(mono) > 1e-4))

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(args.samplerate)
        w.writeframes(pcm.tobytes())

    print(json.dumps({
        "ok": True,
        "out": out,
        "device": mic.name,
        "samplerate": args.samplerate,
        "channels": ch,
        "seconds": round(nframes / args.samplerate, 2),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "nonzero_ratio": round(nonzero, 4),
        "silence": peak < 1e-4,
        "played": os.path.basename(args.play) if args.play else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
