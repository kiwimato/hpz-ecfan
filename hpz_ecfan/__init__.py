"""hpz-ecfan: fan control for HP Z-series workstations through the EC mailbox SMBus proxy."""
from .mailbox import ECMailbox, MailboxError, PortIO
from .nct7491 import NCT7491

__all__ = ["ECMailbox", "MailboxError", "PortIO", "NCT7491"]
__version__ = "0.1.0"
