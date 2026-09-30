import argparse
import os
import sys
import time

from .mailbox import ECMailbox, MailboxError
from .nct7491 import NCT7491, PWM_MIN, TMIN, Z840_FANS

SUPPORTED = ("HP Z840", "HP Z640", "HP Z440", "HP Z820", "HP Z620", "HP Z420")


def dmi_guard(force: bool) -> None:
    try:
        name = open("/sys/class/dmi/id/product_name").read().strip()
    except OSError:
        name = "?"
    if not name.startswith(SUPPORTED) and not force:
        sys.exit(f"'{name}' is not a known HP Z workstation; pass --force if you know the EC mailbox is there")


def status(nct: NCT7491, names: dict) -> str:
    parts = [f"T {z}={nct.temp(z)}C" for z in ("remote1", "local", "remote2")]
    for i in range(3):
        p = nct.pwm(i)
        parts.append(f"PWM{i+1} duty={p.duty_pct:.0f}% min={p.minimum} max={p.maximum} zones=0x{p.zones:02x}")
    parts += [f"{n}={nct.rpm(t) or '-'}rpm" for n, t in names.items()]
    return " | ".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hpz-ecfan", description="HP Z-series EC mailbox / NCT7491 fan control")
    ap.add_argument("--force", action="store_true", help="skip the DMI product check")
    ap.add_argument("--lock", default=None, help="lock file shared by all mailbox users")
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x2E)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("dump")
    p = sub.add_parser("read"); p.add_argument("reg", type=lambda s: int(s, 0))
    p = sub.add_parser("write"); p.add_argument("reg", type=lambda s: int(s, 0)); p.add_argument("value", type=lambda s: int(s, 0))
    p = sub.add_parser("set-min", help="PWM minimum duty 0-255 for channel 1-3");
    p.add_argument("pwm", type=int, choices=(1, 2, 3)); p.add_argument("value", type=lambda s: int(s, 0))
    p = sub.add_parser("set-tmin", help="temperature at which the auto curve starts (C)")
    p.add_argument("zone", choices=list(TMIN)); p.add_argument("celsius", type=int)
    p = sub.add_parser("log"); p.add_argument("--interval", type=float, default=30)
    a = ap.parse_args(argv)
    dmi_guard(a.force)

    mbox = ECMailbox(lock_path=a.lock) if a.lock else ECMailbox()
    nct = NCT7491(mbox, a.addr)
    try:
        nct.identify()
        if a.cmd == "status":
            print(status(nct, Z840_FANS))
        elif a.cmd == "dump":
            d = nct.dump()
            for off in range(0, len(d), 16):
                print(f"{off:02x}: " + " ".join(f"{b:02x}" for b in d[off:off + 16]))
        elif a.cmd == "read":
            print(f"0x{nct.read(a.reg):02x}")
        elif a.cmd == "write":
            if nct.locked():
                sys.exit("NCT7491 LOCK bit is set; configuration is read-only until power cycle")
            nct.write(a.reg, a.value); print("ok")
        elif a.cmd == "set-min":
            nct.set_pwm_min(a.pwm - 1, a.value); print(f"PWM{a.pwm} min = {a.value}")
        elif a.cmd == "set-tmin":
            nct.set_tmin(a.zone, a.celsius); print(f"Tmin {a.zone} = {a.celsius}C")
        elif a.cmd == "log":
            while True:
                print(time.strftime("%H:%M:%S"), status(nct, Z840_FANS), flush=True)
                time.sleep(a.interval)
    except MailboxError as e:
        sys.exit(f"error: {e}")
    except PermissionError:
        sys.exit("need root (or CAP_SYS_RAWIO) for /dev/port")
    return 0


if __name__ == "__main__":
    sys.exit(main())
