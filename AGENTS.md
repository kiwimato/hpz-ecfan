# AGENTS.md — guidance for AI coding agents and new contributors

This repository talks to real hardware through raw I/O ports. Read this before changing
anything under `hpz_ecfan/`.

## What this is

A userspace driver for the SMBus proxy inside the embedded controller (EC) of HP Z-series
workstations, and a thin register layer for the NCT7491 fan controller that hangs off the
EC's private SMBus. See `docs/protocol.md` for the register-level protocol and how it was
recovered.

## Ground rules

1. **Never write a register you cannot read back.** The proxy has no error flag. Every write
   path must go through `ECMailbox.smbus_write_verified`, which reads back and retries.
2. **Never touch NCT7491 `0x40` (Config1) casually.** Bit 1 is a LOCK that is only cleared by
   a power cycle; clearing bit 0 (STRT) sends every fan to 100 %.
3. **Keep the chip in automatic mode.** Control by moving `PWMmin`, `PWMmax` or `Tmin`, not by
   forcing manual duty. A daemon must never be load-bearing for cooling.
4. **Hold the lock for the whole transaction.** All mailbox I/O goes through
   `ECMailbox.locked()`. An unsynchronised second user (a shell sampler, a WMI driver) will
   corrupt the data byte mid-transaction; this was observed live, not theorised.
5. **New hardware = read first.** Before writing on a board that is not a Z840, run `dump`
   and `status`, confirm vendor/device ID (`0x3E == 0x1A`, `0x1D == 0x91`), and find the
   fan-to-tach wiring by nudging one `PWMmin` at a time and watching the tachs.
6. **Do not add HP firmware code or disassembly to this repo.** The protocol description is
   our own; the module that documents it (`HhmDxe`) stays out.

## Testing

There are no hardware mocks yet. Test on real hardware as root (or in a privileged
container with `/dev` bind-mounted) and start with read-only commands. A safe first write
is any value into a measurement register (`0x20`-`0x2F` ignore writes); a safe first
*visible* write is `set-min 3 <a bit above current duty>` and watching the tachs rise.

Preferred order for a change touching the mailbox:
`status` → `dump` (save it) → your change → `dump` again → `diff` → revert → `diff`.

## Layout

- `hpz_ecfan/mailbox.py` — port I/O, mailbox window, SMBus proxy, locking.
- `hpz_ecfan/nct7491.py` — register map and fan-controller helpers; board wiring tables.
- `hpz_ecfan/cli.py` — command-line front end and DMI guard.
- `docs/protocol.md` — the protocol and the verification record.

## Style

Standard library only. Python ≥ 3.9. Keep functions small and hardware facts commented
with the register they come from. No new dependencies without a strong reason.
