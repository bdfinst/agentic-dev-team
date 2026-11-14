"""Encode vehicle telemetry samples into radio-link frames.

The ground station decodes these frames with firmware we do not control, so
the byte layout below is a wire contract. The layout, field order and every
constant follow docs/adr/0042-telemetry-frame-format.md and the ground-station
interface control document (ICD rev F); the section of each is cited inline.
"""

from __future__ import annotations

import struct
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

# ICD rev F section 3.1: every frame starts with this two-byte sync word. The
# ground station scans the byte stream for it to find frame boundaries.
SYNC_WORD = 0xEB90

# ICD rev F section 3.2: protocol version the ground station accepts. Version 2
# added the battery field; version 1 frames are rejected.
PROTOCOL_VERSION = 2

# ICD rev F section 3.3: the radio modem's MTU is 255 bytes and the modem adds a
# 3-byte link header, so a frame may carry at most 252 bytes including the CRC.
MAX_FRAME_BYTES = 252

# ICD rev F section 3.4: the header is big-endian (network order) and its fields
# are read by offset, so the order sync, version, sequence, sample count, payload
# length is fixed. ADR 0042 records why: reordering it broke decoding in the
# 2024 field trial.
HEADER_FORMAT = ">HBHBH"
HEADER_BYTES = struct.calcsize(HEADER_FORMAT)

# ICD rev F section 3.5: one sample is timestamp (u32 ms since boot), latitude
# and longitude (i32, degrees * 1e7), altitude (i16, decimetres) and battery
# (u8, percent), big-endian, read by offset.
SAMPLE_FORMAT = ">IiihB"
SAMPLE_BYTES = struct.calcsize(SAMPLE_FORMAT)

# ICD rev F section 3.5: degrees are scaled by 1e7 to fit an i32 with
# centimetre resolution.
COORDINATE_SCALE = 10_000_000

# ICD rev F section 3.5: altitude travels in decimetres so an i16 covers
# -3276.8 m to +3276.7 m, enough for the flight envelope.
ALTITUDE_SCALE = 10

# ICD rev F section 3.6: CRC-16 polynomial (CCITT, x^16 + x^12 + x^5 + 1).
CRC_POLYNOMIAL = 0x1021

CRC_INITIAL = 0x1D0F

# ICD rev F section 4.2: callsigns are NFC-normalized ASCII, upper case, at most
# 8 bytes, space padded. The ground station compares them byte for byte.
CALLSIGN_BYTES = 8


@dataclass(frozen=True)
class Sample:
    timestamp_ms: int
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    battery_percent: int


class FrameTooLargeError(ValueError):
    """Raised when one sample alone cannot fit in a frame."""


def crc16(data: bytes) -> int:
    """CRC-16 over `data`, bitwise, as specified in ICD rev F section 3.6."""
    crc = CRC_INITIAL
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ CRC_POLYNOMIAL) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_callsign(callsign: str) -> bytes:
    """Return the callsign as the 8-byte field ICD rev F section 4.2 requires."""
    normalized = unicodedata.normalize("NFC", callsign).upper()
    encoded = normalized.encode("ascii")
    if len(encoded) > CALLSIGN_BYTES:
        raise ValueError(f"callsign longer than {CALLSIGN_BYTES} bytes: {callsign!r}")
    return encoded.ljust(CALLSIGN_BYTES, b" ")


def encode_sample(sample: Sample) -> bytes:
    """Pack one sample in the ICD rev F section 3.5 layout."""
    return struct.pack(
        SAMPLE_FORMAT,
        sample.timestamp_ms,
        round(sample.latitude_deg * COORDINATE_SCALE),
        round(sample.longitude_deg * COORDINATE_SCALE),
        round(sample.altitude_m * ALTITUDE_SCALE),
        sample.battery_percent,
    )


def encode_frame(sequence: int, callsign: str, samples: list[Sample]) -> bytes:
    """Build one frame: header, callsign, samples, then the CRC of all of it."""
    body = encode_callsign(callsign) + b"".join(encode_sample(s) for s in samples)
    header = struct.pack(
        HEADER_FORMAT,
        SYNC_WORD,
        PROTOCOL_VERSION,
        sequence & 0xFFFF,  # ICD rev F section 3.4: sequence wraps at 16 bits.
        len(samples),
        len(body),
    )
    unsigned = header + body
    frame = unsigned + struct.pack(">H", crc16(unsigned))
    if len(frame) > MAX_FRAME_BYTES:
        raise FrameTooLargeError(f"frame is {len(frame)} bytes, max {MAX_FRAME_BYTES}")
    return frame


def samples_per_frame() -> int:
    """How many samples fit in one frame next to the header, callsign and CRC."""
    fixed = HEADER_BYTES + CALLSIGN_BYTES + 2
    return (MAX_FRAME_BYTES - fixed) // SAMPLE_BYTES


def batch(samples: Iterable[Sample], size: int) -> Iterator[list[Sample]]:
    """Yield consecutive lists of at most `size` samples."""
    current: list[Sample] = []
    for sample in samples:
        current.append(sample)
        if len(current) == size:
            yield current
            current = []
    if current:
        yield current


def encode_stream(
    callsign: str, samples: Iterable[Sample], first_sequence: int = 0
) -> Iterator[bytes]:
    """Split `samples` into as few frames as fit, numbering them from `first_sequence`."""
    size = samples_per_frame()
    if size < 1:
        raise FrameTooLargeError("a single sample does not fit in a frame")
    for offset, group in enumerate(batch(samples, size)):
        yield encode_frame(first_sequence + offset, callsign, group)


def decode_header(frame: bytes) -> dict[str, int]:
    """Read the header fields back, for the loopback self-test."""
    sync, version, sequence, count, length = struct.unpack_from(HEADER_FORMAT, frame)
    return {
        "sync": sync,
        "version": version,
        "sequence": sequence,
        "sample_count": count,
        "payload_length": length,
    }


def verify_frame(frame: bytes) -> bool:
    """True when the trailing CRC matches the rest of the frame."""
    if len(frame) < HEADER_BYTES + 2:
        return False
    (expected,) = struct.unpack(">H", frame[-2:])
    return crc16(frame[:-2]) == expected


def self_test() -> None:
    """Encode two samples, then check the header and CRC round-trip."""
    samples = [
        Sample(1_000, 52.5200066, 13.4049540, 34.5, 97),
        Sample(2_000, 52.5200100, 13.4049600, 35.0, 97),
    ]
    frame = next(encode_stream("dl1abc", samples, first_sequence=7))
    header = decode_header(frame)
    assert header["sync"] == SYNC_WORD
    assert header["version"] == PROTOCOL_VERSION
    assert header["sequence"] == 7
    assert header["sample_count"] == 2
    assert verify_frame(frame)


if __name__ == "__main__":
    self_test()
    print("telemetry frame encoder self-test passed")
