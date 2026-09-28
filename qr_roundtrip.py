#!/usr/bin/env python3
"""An independent QR decoder, used only by test_qr.py.

This deliberately does NOT reuse the encoder's placement code. It walks the
symbol itself, reads the format info out of it to discover which mask was
applied, rebuilds the function-pattern map from scratch, and reads the data
bits back. If a bug existed in the shared placement logic, reusing it here
would cancel out and the test would pass anyway.

Narrow like the encoder: versions 1-3, EC level M, byte mode. No Reed-Solomon
correction, because the point is to prove the bits were laid down where the
spec says, not to repair them.
"""

FORMAT_M = [0x5412, 0x5125, 0x5E7C, 0x5B4B, 0x45F9, 0x40CE, 0x4F97, 0x4AA0]
ALIGN_CENTRE = {1: 0, 2: 18, 3: 22}


def _mask_at(mask, row, col):
    return [
        (row + col) % 2 == 0,
        row % 2 == 0,
        col % 3 == 0,
        (row + col) % 3 == 0,
        (row // 2 + col // 3) % 2 == 0,
        (row * col) % 2 + (row * col) % 3 == 0,
        ((row * col) % 2 + (row * col) % 3) % 2 == 0,
        ((row + col) % 2 + (row * col) % 3) % 2 == 0,
    ][mask]


def _read_format(m):
    """Read the 15 format bits from the copy around the top-left finder and
    look up which mask they encode."""
    size = len(m)
    bits = 0
    for i in range(15):
        if i < 6:
            bit = m[i][8]
        elif i < 8:
            bit = m[i + 1][8]
        else:
            bit = m[size - 15 + i][8]
        if bit:
            bits |= (1 << i)
    if bits not in FORMAT_M:
        return None, bits
    return FORMAT_M.index(bits), bits


def _function_map(size, version):
    """True where a module is part of a function pattern or reserved area,
    i.e. everywhere that is NOT data."""
    fixed = [[False] * size for _ in range(size)]

    def block(r0, c0, h, w):
        for r in range(r0, r0 + h):
            for c in range(c0, c0 + w):
                if 0 <= r < size and 0 <= c < size:
                    fixed[r][c] = True

    # finders plus their separators
    block(0, 0, 8, 8)
    block(0, size - 8, 8, 8)
    block(size - 8, 0, 8, 8)
    # timing
    for i in range(size):
        fixed[6][i] = True
        fixed[i][6] = True
    # alignment
    centre = ALIGN_CENTRE[version]
    if centre:
        block(centre - 2, centre - 2, 5, 5)
    # format info areas
    for i in range(9):
        fixed[8][i] = True
        fixed[i][8] = True
    for i in range(8):
        fixed[8][size - 1 - i] = True
        fixed[size - 1 - i][8] = True
    return fixed


def decode(m):
    """Return the decoded string, or raise ValueError explaining what's wrong."""
    size = len(m)
    if (size - 17) % 4:
        raise ValueError("size %d is not a valid QR version" % size)
    version = (size - 17) // 4
    if version not in ALIGN_CENTRE:
        raise ValueError("version %d is outside the supported 1-3" % version)

    mask, raw = _read_format(m)
    if mask is None:
        raise ValueError("format bits %#06x match no EC-M mask" % raw)

    fixed = _function_map(size, version)

    bits = []
    inc, row = -1, size - 1
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        while True:
            for off in range(2):
                c = col - off
                if not fixed[row][c]:
                    value = m[row][c]
                    if _mask_at(mask, row, c):
                        value = not value
                    bits.append(1 if value else 0)
            row += inc
            if row < 0 or row >= size:
                row -= inc
                inc = -inc
                break
        col -= 2

    def take(n):
        nonlocal bits
        value = 0
        for bit in bits[:n]:
            value = (value << 1) | bit
        bits = bits[n:]
        return value

    mode = take(4)
    if mode != 4:
        raise ValueError("mode is %d, expected 4 (byte mode)" % mode)
    length = take(8)
    max_len = {1: 14, 2: 26, 3: 42}[version]
    if length > max_len:
        raise ValueError("length %d exceeds version %d capacity" % (length, version))
    data = bytes(take(8) for _ in range(length))
    return data.decode("utf-8"), mask
