# hpz-ecfan

Chassis fan control for HP Z-series workstations (developed on a Z840, BIOS M60 v02.56)
from Linux, without a kernel module and without rebooting.

## Why this exists

On these machines the chassis fans are driven by an ON Semi **NCT7491** (ADT7475 family)
that sits on the *private* SMBus of the Nuvoton embedded controller. The PCH's `i2c-i801`
bus cannot reach it, so `lm-sensors`, `fancontrol` and the `adt7475` driver see nothing.
HP's ACPI/WMI only exposes the read side (the `hp-wmi-sensors` driver). The write side was
recovered from HP's `HhmDxe` firmware module, which programs the chip at every POST.

## How it works

The EC exposes a RAM window at I/O `0x800-0x8FE`, page-selected through `0x8FF`.
Page 0 contains a tiny SMBus proxy:

| byte | meaning |
|------|---------|
| `0xE5` | 7-bit device address |
| `0xE6` | bytes to read back (1 for a read, 0 for a write) |
| `0xE7` | bytes to send after the address (1: register, 2: register+data) |
| `0xE8` | data: register for a read (result returned here), value for a write |
| `0xE9` | register for a write |
| `0xF0` | bit 0: write 1 to start, EC clears it on completion |

Read byte:  `E5=dev, E8=reg, E7=1, E6=1, F0=1`, poll `F0.0==0`, result in `E8`
Write byte: `E5=dev, E8=val, E9=reg, E7=2, E6=0, F0=1`, poll `F0.0==0`

There is no error flag. A NACK still clears `F0.0` and leaves `E8` untouched, so every
write is verified by reading the register back. All transactions are serialised through an
`flock` (`/var/lock/ecmbox`, override with `--lock` or `HPZ_EC_LOCK`); two unsynchronised
users *will* corrupt each other's data byte.

Fan control stays inside the chip's own automatic loop: the tool moves the floor (`PWMmin`)
or the knee (`Tmin`) of the temperature curve rather than switching to manual duty, so if
the tool dies the fans keep working. THERM limits stay armed regardless. Every failure
direction is toward faster fans.

## Usage (root)

```
python3 -m hpz_ecfan.cli status
python3 -m hpz_ecfan.cli dump                 # registers 0x00-0x9F
python3 -m hpz_ecfan.cli set-min 3 0x60       # front fans (PWM3) floor to 37% duty
python3 -m hpz_ecfan.cli set-min 1 0x80       # rear fan 0 (PWM1)
python3 -m hpz_ecfan.cli set-tmin local 35    # start the curve earlier
python3 -m hpz_ecfan.cli log --interval 30
```

Z840 wiring: tach1/tach2 = rear fans on PWM1/PWM2, tach3/tach4 = front fans (both on PWM3).
Other Z-series boards likely share the EC and the mailbox but may wire fans differently;
check `dump` and `status` before writing. The tool refuses to run on non-HP-Z DMI product
names unless `--force` is given.

Needs `/dev/port` (root or `CAP_SYS_RAWIO`); works from a privileged container on Unraid.

## Safety notes

* Config1 (`0x40`) bit 1 is the chip's LOCK bit; once set, configuration is read-only until
  a power cycle. The tool refuses writes if it is set. Never write `0x40` blindly.
* Clearing STRT (`0x40` bit 0) sends all PWMs to 100%.
* A power cycle resets both the EC and the chip to BIOS defaults; a warm reboot re-runs POST,
  which rewrites the chip anyway.
