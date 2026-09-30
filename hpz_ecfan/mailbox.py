"""HP Z-series (Nuvoton NPCD37x-class) embedded-controller mailbox and its SMBus proxy.

The EC exposes a 16-page x 255-byte RAM window at I/O 0x800-0x8FE with the page
selected through 0x8FF.  Page 0 holds a small SMBus proxy that lets the host talk
to devices on the EC's *private* SMBus (the PCH cannot reach them):

    0xE5  7-bit device address
    0xE6  number of bytes the EC should read back (0 or 1)
    0xE7  number of bytes the EC should send after the address (1 or 2)
    0xE8  data byte  (register for a read; result is returned here too)
    0xE9  register byte for a write
    0xF0  bit0: write 1 to start, EC clears it when the transaction is done

Read  = E5:dev, E8:reg,        E7:1, E6:1, F0:1, poll F0.0, result in E8
Write = E5:dev, E8:val, E9:reg, E7:2, E6:0, F0:1, poll F0.0

There is no error flag.  A NACK (no such device) still clears F0.0 and simply
leaves E8 untouched, so writes are only trusted after a readback.  Every
transaction is serialised with an flock so several processes can share the
mailbox: an interleaved read/write corrupts the data byte (seen live).
"""
from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager

MAILBOX_BASE = 0x800
MAILBOX_PAGE = 0x8FF
DEFAULT_LOCK = os.environ.get("HPZ_EC_LOCK", "/var/lock/ecmbox")

R_DEV, R_RXCNT, R_TXCNT, R_DATA, R_REG, R_GO = 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xF0
POLL_TRIES, POLL_SLEEP = 250, 0.001


class MailboxError(RuntimeError):
    pass


class PortIO:
    """Byte access to x86 I/O ports through /dev/port (needs root or CAP_SYS_RAWIO)."""

    def __init__(self, path: str = "/dev/port"):
        self.fd = os.open(path, os.O_RDWR)

    def inb(self, port: int) -> int:
        return os.pread(self.fd, 1, port)[0]

    def outb(self, port: int, value: int) -> None:
        os.pwrite(self.fd, bytes([value & 0xFF]), port)

    def close(self) -> None:
        os.close(self.fd)


class ECMailbox:
    def __init__(self, io: PortIO | None = None, lock_path: str = DEFAULT_LOCK):
        self.io = io or PortIO()
        self.lock_path = lock_path

    @contextmanager
    def locked(self):
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    # --- raw window access (caller holds the lock) ---
    def _read(self, addr: int) -> int:
        """addr = page<<8 | offset.  The firmware re-reads once on 0xFF (EC busy marker)."""
        self.io.outb(MAILBOX_PAGE, (addr >> 8) & 0xF)
        port = MAILBOX_BASE + (addr & 0xFF)
        v = self.io.inb(port)
        if v == 0xFF:
            v = self.io.inb(port)
        return v

    def _write(self, addr: int, value: int) -> None:
        self.io.outb(MAILBOX_PAGE, (addr >> 8) & 0xF)
        self.io.outb(MAILBOX_BASE + (addr & 0xFF), value)

    def read(self, addr: int) -> int:
        with self.locked():
            v = self._read(addr)
            self.io.outb(MAILBOX_PAGE, 0)
            return v

    def read_block(self, addr: int, count: int) -> bytes:
        with self.locked():
            out = bytes(self._read(addr + i) for i in range(count))
            self.io.outb(MAILBOX_PAGE, 0)
            return out

    def _go_and_wait(self) -> None:
        self._write(R_GO, 1)
        for _ in range(POLL_TRIES):
            if not self._read(R_GO) & 1:
                return
            time.sleep(POLL_SLEEP)
        raise MailboxError("EC SMBus proxy did not complete (F0 bit0 still set)")

    # --- SMBus proxy ---
    def smbus_read_byte(self, dev: int, reg: int) -> int:
        with self.locked():
            self._write(R_DEV, dev & 0x7F)
            self._write(R_DATA, reg & 0xFF)
            self._write(R_TXCNT, 1)
            self._write(R_RXCNT, 1)
            self._go_and_wait()
            v = self._read(R_DATA)
            self.io.outb(MAILBOX_PAGE, 0)
            return v

    def smbus_write_byte(self, dev: int, reg: int, value: int) -> None:
        with self.locked():
            self._write(R_DEV, dev & 0x7F)
            self._write(R_DATA, value & 0xFF)
            self._write(R_REG, reg & 0xFF)
            self._write(R_TXCNT, 2)
            self._write(R_RXCNT, 0)
            self._go_and_wait()
            self.io.outb(MAILBOX_PAGE, 0)

    def smbus_write_verified(self, dev: int, reg: int, value: int, retries: int = 3) -> None:
        """Write, then read back; the proxy has no error flag so this is the only proof."""
        for _ in range(retries):
            self.smbus_write_byte(dev, reg, value)
            if self.smbus_read_byte(dev, reg) == value & 0xFF:
                return
        raise MailboxError(f"register 0x{reg:02X} did not take value 0x{value:02X}")
