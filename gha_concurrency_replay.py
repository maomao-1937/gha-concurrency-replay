"""Replay one normalized concurrency group from a bounded local JSON trace."""

from collections import deque
import json
import os
import re
import stat
import sys


MAX_INPUT_BYTES = 1024 * 1024
MAX_PENDING = 100
DRIVE_PREFIX = re.compile(r"[A-Za-z]:/(?!/)")
DEVICE_NAMES = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]")
NATIVE_ROOTS = ("/??/", "/device/", "/global??/", "/dosdevices/", "/systemroot/", "/globalroot/")
HELP = (
    "Usage: python gha_concurrency_replay.py INPUT\n"
    "Replay an ordered local JSON trace for one concurrency group.\n"
)


def require_local_path(path):
    normalized = path.replace("\\", "/")
    root = normalized.lstrip(" ").lower()
    if not path or "\0" in path or root.startswith(("//", *NATIVE_ROOTS)):
        raise ValueError
    drive = DRIVE_PREFIX.match(normalized)
    tail = normalized[drive.end():] if drive else normalized
    if ":" in tail:
        raise ValueError
    for part in tail.split("/"):
        base = part.partition(".")[0].rstrip(" ").upper()
        if DEVICE_NAMES.fullmatch(base):
            raise ValueError


def bounded_regular(info):
    return stat.S_ISREG(info.st_mode) and info.st_size <= MAX_INPUT_BYTES


def open_nonblocking(path, flags):
    return os.open(path, flags | getattr(os, "O_NONBLOCK", 0))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def reject_number(_value):
    raise ValueError


def read_trace(path):
    require_local_path(path)
    if not bounded_regular(os.stat(path)):
        raise ValueError
    with open(path, "rb", opener=open_nonblocking) as stream:
        if not bounded_regular(os.fstat(stream.fileno())):
            raise ValueError
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError
    # No numbers are part of this schema, including nonfinite JSON extensions.
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_int=reject_number, parse_float=reject_number,
                      parse_constant=reject_number)


def replay(trace):
    if not isinstance(trace, dict) or trace.keys() != {"queue", "cancel_in_progress", "events"}:
        raise ValueError
    queue, cancel, events = trace["queue"], trace["cancel_in_progress"], trace["events"]
    # Exact allowed strings also exclude escaped surrogate code points.
    if (queue not in ("single", "max") or not isinstance(cancel, bool)
            or (queue == "max" and cancel) or not isinstance(events, list)
            or any(event not in ("arrive", "finish") for event in events)):
        raise ValueError

    running = None
    pending = deque()
    history = []
    next_id = 0
    for event in events:
        if event == "finish":
            if running is None:
                raise ValueError
            record = {"id": running, "action": "finished"}
            running = pending.popleft() if pending else None
            if running is not None:
                record["promoted_id"] = running
        else:
            next_id += 1
            record = {"id": next_id}
            if running is None:
                running = next_id
                record["action"] = "started"
            elif cancel:
                record.update(action="preempted", cancelled_id=running)
                running = next_id
            elif queue == "single" and pending:
                record.update(action="replaced", replaced_id=pending.pop())
                pending.append(next_id)
            elif len(pending) == MAX_PENDING:
                record["action"] = "rejected"
            else:
                record["action"] = "queued"
                pending.append(next_id)
        history.append(record)
    return {"events": history, "running": running, "pending": list(pending)}


def write_message(stream, message):
    if stream is None:
        return False
    try:
        stream.write(message)
        stream.flush()
    except (OSError, ValueError):
        # Redirect the failed descriptor so interpreter shutdown cannot retry a broken pipe.
        try:
            failed_fd = stream.fileno()
            null_fd = os.open(os.devnull, os.O_WRONLY)
            if null_fd != failed_fd:
                try:
                    os.dup2(null_fd, failed_fd)
                finally:
                    os.close(null_fd)
        except (OSError, ValueError):
            pass
        return False
    return True


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args in (["-h"], ["--help"]):
        output = HELP
    else:
        try:
            if len(args) == 2 and args[0] == "--":
                path = args[1]
            elif len(args) == 1 and not args[0].startswith("-"):
                path = args[0]
            else:
                raise ValueError
            output = json.dumps(replay(read_trace(path)), separators=(",", ":")) + "\n"
        except (OSError, ValueError, RecursionError):
            write_message(sys.stderr, "error: invalid input\n")
            return 2
    if not write_message(sys.stdout, output):
        write_message(sys.stderr, "error: output unavailable\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
