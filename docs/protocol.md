# EC mailbox SMBus proxy — protocol and verification record

Hardware: HP Z840 (BIOS M60 v02.56), Nuvoton NPCD37x-class EC (Super I/O ID 0x1C91,
LDN 8 = HWM at I/O 0x800), ON Semi NCT7491 at SMBus address 0x2E on the EC's private bus.

## Mailbox window

| I/O port | function |
|---|---|
| `0x8FF` | page select, low 4 bits (pages 8-15 mirror 0-7) |
| `0x800 + n` | byte `n` of the selected page, 0 ≤ n ≤ 0xFE |

Reading a byte that returns `0xFF` is re-read once; the EC uses `0xFF` as a transient
"not ready" marker. HP's own firmware does the same.

## Proxy registers (page 0)

| byte | read byte | write byte |
|---|---|---|
| `0xE5` | 7-bit device address | 7-bit device address |
| `0xE6` | `1` (bytes to receive) | `0` |
| `0xE7` | `1` (bytes to send) | `2` |
| `0xE8` | register → result | **value** |
| `0xE9` | — | **register** |
| `0xF0` | `1` starts; bit 0 clears on completion | same |

Order used by the firmware: `E5, E8, (E9), E7, E6, F0`. Completion: poll `F0` bit 0 up to
250 times with 1 ms between polls. `0xE7`/`0xE6` behave as transmit/receive byte counts,
which is why a read is "send 1, receive 1" and a write is "send 2, receive 0".

## Errors

None are signalled. On a NACK (transaction to a non-existent address) `F0` still clears
and `E8` is left as written. On timeout the firmware gives up silently; the only error path
it has is a single check of `F0` after its whole POST table, logged as a status code.
Therefore a write is only trusted after reading the register back.

## Concurrency

Mailbox bytes are plain EC RAM. If a second process runs a read between another process's
`E8` load and `F0` trigger, the read's result byte replaces the write's value. Observed
live: an intended `0x66 ← 0x60` became `0x66 ← 0xDC` because a sampler read register
`0x60` (value `0xDC`) in between. All users must share one `flock`.

## The read side is public

HP's ACPI (SSDT, method `RSBS`) implements exactly the read transaction above. It is also
what the Linux `hp-wmi-sensors` driver ends up using. The write side is not exposed by
ACPI or WMI; it was recovered from the DXE module that programs the NCT7491 at POST, by
matching the routine that shares the read routine's prologue and completion poll and checking
every call site's argument order (device, register, value).

## Verification log (2026-09-30, Z840)

1. Write `0x2A ← 0x2A` (device `0x2E`): every mailbox byte inside the read-only
   measurement block, so any misinterpretation is harmless. Completed; before/after dump of
   `0x00-0x9F` differed only in live measurements.
2. PECI Tmin `0x3B` (unused: no PWM has a PECI zone bit): `CE → 2A → CE`. Proof.
3. PWM3 min `0x66`: `33 → 60`. PWM3 duty `4F → 74`, both front fans ~1030 → ~1640 rpm.
   Persisted across 6 samples over 3 minutes; nothing at runtime rewrites the chip.
4. PWM1/PWM2 min `0x64/0x65`: `4C/59 → 80/80`. Both rear fans ~1100/1316 → ~1900 rpm.
5. Config1 `0x40` stayed `0x85` (STRT set, LOCK clear) throughout.

## NCT7491 facts that matter for control

- Zone assignment lives in `0x8A/0x8D/0x90` (PWM1/2/3), not in `0x5C-0x5E` bits 7:5 as on
  the ADT7475. Z840 live values: `0x8A = 0x8D = 0x07` (local, remote1, remote2),
  `0x90 = 0x05` (local, remote2), SMBus thermal slave 0 (`0x98 = 0x4D`) added on PWM1/2.
- Tach count → rpm: HP's readout matches `4 680 000 / count`, not the datasheet's 5.4 M.
- THERM limits (`0x6A-0x6C`) override the curve independently of zone assignment.
- Tmin format follows the measurement format selected in `0x7C` bit 0 (offset-64 or 2's
  complement).
