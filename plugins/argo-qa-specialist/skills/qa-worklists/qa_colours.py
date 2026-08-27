#!/usr/bin/env python3
"""The two highlight colours a QA worklist uses — defined once, for everything that reads them.

Four separate files used to carry their own copy of these hex codes: the builder that paints the
cells, the reviewer and the ingester that recognise them again in a returned workbook, and the
fixture generator that imitates an RA filling them in. Any one of them drifting means answers
silently stop being recognised — a whole site's work discarded with no error — so they live here
and are imported, never retyped.

YELLOW is "this field applies to this patient and is blank" — the confirmed gap the RA is being
asked to close. It has to actually LOOK yellow: it was `FFC7CE` (a pale rose) for a long time
while every instruction to every RA said "fill in the yellow cells", which is a sentence that
cannot be followed. It is now a plain yellow.

AMBER is a different message: "we couldn't read this field's condition — please check whether it
applies at all". It must stay clearly distinguishable from YELLOW, because the two ask for
different things.

LEGACY_FLAG_HEXES are colours we no longer PAINT but must still READ. Worklists sent to sites
before the colour change come back months later still filled in the old rose — the RAs did the
work, and the only thing standing between that work and the audit is whether the reader
recognises the fill. One live round reported 5 of 36 answers because it didn't. Nothing is ever
retired from this tuple; a colour once painted is a colour forever readable.

Excel/openpyxl want RRGGBB with no leading '#'.
"""

YELLOW_HEX = "FFFF99"   # "this applies and is blank" — the RA fills it in
AMBER_HEX = "FFE9B8"    # "we couldn't read this field's condition — please check"

# Fills that MEANT yellow in an older release. Read as flagged; never painted again.
LEGACY_FLAG_HEXES = ("FFC7CE",)   # the pale rose that "yellow" used to be, pre-0.18

__all__ = ["YELLOW_HEX", "AMBER_HEX", "LEGACY_FLAG_HEXES"]


if __name__ == "__main__":
    print(__doc__)
    print(f"YELLOW_HEX = {YELLOW_HEX}\nAMBER_HEX  = {AMBER_HEX}")
    print(f"LEGACY_FLAG_HEXES = {', '.join(LEGACY_FLAG_HEXES)}  (read-only)")
