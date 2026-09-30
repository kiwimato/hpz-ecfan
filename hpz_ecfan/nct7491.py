"""ON Semi NCT7491 (ADT7475/ADT7490 family) chassis fan controller behind the HP EC proxy."""
from __future__ import annotations

from dataclasses import dataclass

from .mailbox import ECMailbox, MailboxError

DEFAULT_ADDR = 0x2E
TACH_HZ = 4_680_000          # rpm = TACH_HZ / count, matches HP's own readout on the Z840
VENDOR_ID, DEVICE_ID = 0x1A, 0x91

# register map (subset)
TEMP = {"remote1": 0x25, "local": 0x26, "remote2": 0x27}
TACH = {"tach1": 0x28, "tach2": 0x2A, "tach3": 0x2C, "tach4": 0x2E}   # low, high = +1
PWM_DUTY = (0x30, 0x31, 0x32)
PWM_MAX = (0x38, 0x39, 0x3A)
PWM_MIN = (0x64, 0x65, 0x66)
TMIN = {"remote1": 0x67, "local": 0x68, "remote2": 0x69}
THERM = {"remote1": 0x6A, "local": 0x6B, "remote2": 0x6C}
TRANGE = {"remote1": 0x5F, "local": 0x60, "remote2": 0x61}
PWM_CFG = (0x5C, 0x5D, 0x5E)
PWM_ZONES = (0x8A, 0x8D, 0x90)   # bit0 local, bit1 remote1, bit2 remote2, bits3-6 PECI0-3
CONFIG1, CONFIG5 = 0x40, 0x7C
TRANGE_TABLE = [2, 2.5, 3.33, 4, 5, 6.67, 8, 10, 13.33, 16, 20, 26.67, 32, 40, 53.33, 80]

# HP Z840 wiring of the four tach inputs (rear pair on PWM1/PWM2, front pair on PWM3)
Z840_FANS = {"rear0": "tach1", "rear1": "tach2", "front0": "tach3", "front1": "tach4"}
Z840_PWM = {"rear": (0, 1), "front": (2,)}


@dataclass
class PwmChannel:
    index: int
    duty: int
    minimum: int
    maximum: int
    zones: int

    @property
    def duty_pct(self) -> float:
        return self.duty * 100 / 255


class NCT7491:
    def __init__(self, mbox: ECMailbox, addr: int = DEFAULT_ADDR):
        self.mbox, self.addr = mbox, addr

    def read(self, reg: int) -> int:
        return self.mbox.smbus_read_byte(self.addr, reg)

    def write(self, reg: int, value: int) -> None:
        self.mbox.smbus_write_verified(self.addr, reg, value)

    def identify(self) -> None:
        vid, did = self.read(0x3E), self.read(0x1D)
        if (vid, did) != (VENDOR_ID, DEVICE_ID):
            raise MailboxError(f"no NCT7491 at 0x{self.addr:02X} (vendor 0x{vid:02X} device 0x{did:02X})")

    def locked(self) -> bool:
        return bool(self.read(CONFIG1) & 0x02)

    def dump(self, count: int = 0xA0) -> bytes:
        return bytes(self.read(r) for r in range(count))

    def rpm(self, tach: str) -> int | None:
        lo = TACH[tach]
        count = self.read(lo) | self.read(lo + 1) << 8
        if count in (0, 0xFFFF):
            return None
        return TACH_HZ // count

    def temp(self, name: str) -> int:
        raw = self.read(TEMP[name])
        twos = self.read(CONFIG5) & 0x01
        return raw - 256 if (twos and raw > 127) else (raw if twos else raw - 64)

    def pwm(self, i: int) -> PwmChannel:
        return PwmChannel(i, self.read(PWM_DUTY[i]), self.read(PWM_MIN[i]),
                          self.read(PWM_MAX[i]), self.read(PWM_ZONES[i]))

    def set_pwm_min(self, i: int, value: int) -> None:
        """Raise/lower the floor of the chip's own auto curve; the chip stays in control."""
        self.write(PWM_MIN[i], max(0, min(255, value)))

    def set_pwm_max(self, i: int, value: int) -> None:
        self.write(PWM_MAX[i], max(0, min(255, value)))

    def set_tmin(self, zone: str, celsius: int) -> None:
        twos = self.read(CONFIG5) & 0x01
        self.write(TMIN[zone], celsius if twos else celsius + 64)

    def trange(self, zone: str) -> float:
        return TRANGE_TABLE[self.read(TRANGE[zone]) >> 4]
