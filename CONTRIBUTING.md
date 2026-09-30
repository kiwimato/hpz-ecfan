# Contributing

Reports from other HP Z-series machines are the most valuable contribution. If you have a
Z440, Z640, Z820, Z620 or anything else with the same EC, please open an issue with:

- `cat /sys/class/dmi/id/product_name /sys/class/dmi/id/bios_version`
- the output of `python3 -m hpz_ecfan.cli --force status` and `... dump`
- which fans moved when you nudged each `PWMmin` (see AGENTS.md for the safe procedure)

Code changes: read `AGENTS.md` first, keep the standard-library-only rule, and describe how
you tested on hardware in the pull request.

Do not submit firmware images, disassembly, or code copied from HP modules.
