"""
Record the demo narration in your own voice, one clip per line.

    .venv/bin/python record_narration.py              # record every line that has no clip yet
    .venv/bin/python record_narration.py --line 7     # redo just line 7
    .venv/bin/python record_narration.py --test-mic   # 3-second mic check

For each line: press Enter to start, read the line, press Enter to stop.
Then: Enter = keep and go on, p = play it back, r = redo, q = quit (progress is saved).

Clips are saved to narration/01.wav, 02.wav, and so on (one per line). Leading/trailing silence is
trimmed later by make_demo.py, so don't worry about pausing before you speak.
"""

import argparse
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_demo import GAP, narration_lines  # noqa: E402

LIMIT = 300          # presentation limit in seconds
ACTION_OVERHEAD = 25  # seconds the live answers and clicks typically run past the narration

BOLD, DIM, GREEN, YELLOW, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def audio_devices():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                         capture_output=True, text=True).stderr
    section = out.split("audio devices:", 1)[-1]
    return [(int(i), name.strip()) for i, name in re.findall(r"\[(\d+)\] (.+)", section)]


def pick_mic(name):
    devices = audio_devices()
    for idx, dev in devices:
        if name.lower() in dev.lower():
            return idx, dev
    listing = "\n".join(f"  [{i}] {d}" for i, d in devices) or "  (none found)"
    sys.exit(f"No microphone matching '{name}'. Available:\n{listing}\nUse --mic \"<part of the name>\".")


def duration(path):
    try:
        return float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).decode())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def peak_db(path):
    out = subprocess.run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"max_volume: (-?[\d.]+) dB", out)
    return float(m.group(1)) if m else None


def record(mic_idx, dest: Path, seconds=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "avfoundation", "-i", f":{mic_idx}",
           "-ac", "1", "-ar", "48000"]
    if seconds:
        subprocess.run(cmd + ["-t", str(seconds), str(dest)], check=True)
        return
    proc = subprocess.Popen(cmd + [str(dest)], stdin=subprocess.PIPE)
    input(f"  {RED}● recording{RESET}  press Enter to stop ")
    try:
        proc.communicate(b"q", timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def total_estimate(folder, n_lines):
    clips = [folder / f"{i:02d}.wav" for i in range(1, n_lines + 1)]
    spoken = sum(duration(c) for c in clips if c.exists())
    done = sum(c.exists() for c in clips)
    return spoken, done


def show_total(folder, n_lines):
    spoken, done = total_estimate(folder, n_lines)
    if done == 0:
        return
    # Project the full video length from the lines recorded so far
    projected = spoken / done * n_lines + GAP * n_lines + ACTION_OVERHEAD
    color = RED if projected > LIMIT else GREEN
    print(f"  {DIM}{done}/{n_lines} lines · {spoken:.0f}s spoken · projected video "
          f"{color}{int(projected // 60)}:{int(projected % 60):02d}{RESET}{DIM} (limit 5:00){RESET}")
    if projected > LIMIT:
        print(f"  {YELLOW}Running long: speak a little faster, or trim a line in make_demo.py.{RESET}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--line", type=int, action="append", help="re-record this line number (repeatable)")
    ap.add_argument("--all", action="store_true", help="re-record every line, even ones already recorded")
    ap.add_argument("--mic", default="MacBook Pro Microphone", help="part of the microphone's name")
    ap.add_argument("--dir", default=str(HERE / "narration"), help="where clips are saved")
    ap.add_argument("--test-mic", nargs="?", const=3, type=float, metavar="SECONDS",
                    help="record a few seconds and report the level, then exit")
    args = ap.parse_args()

    mic_idx, mic_name = pick_mic(args.mic)
    folder = Path(args.dir)
    folder.mkdir(parents=True, exist_ok=True)

    if args.test_mic:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "test.wav"
            print(f"Recording {args.test_mic:g}s from {mic_name}... say something.")
            record(mic_idx, dest, seconds=args.test_mic)
            peak = peak_db(dest)
            print(f"Captured {duration(dest):.1f}s, peak level {peak} dB")
            if peak is None or peak < -50:
                print("That's basically silence. Check System Settings > Privacy & Security > Microphone "
                      "and allow your terminal app, then try again.")
            elif peak > -1:
                print("That's clipping; move a little further from the mic.")
            else:
                print("Mic is working.")
        return

    lines = narration_lines()
    n = len(lines)
    if args.line:
        bad = [x for x in args.line if not 1 <= x <= n]
        if bad:
            sys.exit(f"Line numbers must be 1-{n}: {bad}")
        todo = sorted(set(args.line))
    elif args.all:
        todo = list(range(1, n + 1))
    else:
        todo = [i for i in range(1, n + 1) if not (folder / f"{i:02d}.wav").exists()]

    print(f"\n{BOLD}Narration recorder{RESET} · mic: {mic_name} · saving to {folder}")
    if not todo:
        print("All lines are recorded. Use --line N to redo one, or --all to start over.")
        show_total(folder, n)
        return
    print(f"{DIM}Read naturally. Pause before or after is fine, since silence gets trimmed.{RESET}")

    for num in todo:
        dest = folder / f"{num:02d}.wav"
        print(f"\n{BOLD}Line {num}/{n}{RESET}")
        for chunk in textwrap.wrap(lines[num - 1], 88):
            print(f"  {chunk}")
        while True:
            cmd = input(f"\n  Enter to record (s = skip, q = quit) ").strip().lower()
            if cmd == "q":
                show_total(folder, n)
                return
            if cmd == "s":
                break
            tmp = dest.with_suffix(".take.wav")
            record(mic_idx, tmp)
            secs, peak = duration(tmp), peak_db(tmp)
            warn = ""
            if peak is None or peak < -45:
                warn = f"  {YELLOW}very quiet: check mic permission or speak up{RESET}"
            elif peak > -1:
                warn = f"  {YELLOW}clipping: move back a little{RESET}"
            print(f"  took {secs:.1f}s{warn}")
            while True:
                choice = input("  Enter = keep · p = play · r = redo ").strip().lower()
                if choice == "p":
                    subprocess.run(["afplay", str(tmp)])
                    continue
                break
            if choice == "r":
                tmp.unlink(missing_ok=True)
                continue
            tmp.replace(dest)
            print(f"  {GREEN}saved {dest.name}{RESET}")
            show_total(folder, n)
            break

    spoken, done = total_estimate(folder, n)
    if done == n:
        print(f"\n{GREEN}All {n} lines recorded.{RESET} Build the video with:\n"
              f"  .venv/bin/python make_demo.py --narration narration")
    else:
        missing = [i for i in range(1, n + 1) if not (folder / f"{i:02d}.wav").exists()]
        print(f"\nStill missing lines: {missing}. Run this script again to continue.")


if __name__ == "__main__":
    main()
