"""Serial endpoint validation and identity helpers for Monoprice."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from time import sleep
from typing import Final

import serialx
from pymonoprice import ZoneStatus

SUPPORTED_BAUD_RATES: Final = (9600, 19200, 38400, 57600, 115200, 230400)
POWER_ON_BAUD_RATE: Final = 9600
VALIDATION_TIMEOUT: Final = 0.75
_COM_PORT = re.compile(r"^COM\d+$", re.IGNORECASE)


class MonopriceValidationError(Exception):
    """Base class for a submitted serial endpoint validation failure."""


class CannotOpenPort(MonopriceValidationError):
    """The submitted serial endpoint could not be opened."""


class NotMonopriceDevice(MonopriceValidationError):
    """The submitted endpoint did not return a valid Monoprice response."""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a short-lived Monoprice endpoint validation."""

    detected_baud: int
    # Which expansion units (1, 2, 3) answered a status query, so the config
    # flow's zone-naming step knows how many zones actually exist to name.
    detected_units: tuple[int, ...] = (1,)


@dataclass(frozen=True, slots=True)
class EndpointIdentity:
    """Stable identity derived from USB metadata or the canonical endpoint."""

    key: str
    kind: str


def _read_zone_status(port: serialx.BaseSerial) -> ZoneStatus | None:
    """Read and structurally parse a zone status response.

    Used both for the required Zone 11 confirmation and the optional
    expansion-unit probes below; see docs/protocol.md for the frame shape.
    """
    first = port.read_until(b"\r\n#", size=128, timeout=VALIDATION_TIMEOUT)
    second = port.read_until(b"\r\n#", size=128, timeout=VALIDATION_TIMEOUT)
    response = first + second
    try:
        return ZoneStatus.from_string(response.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None


def _probe_zone(port: serialx.BaseSerial, zone: int) -> bool:
    """Ask one zone for its status; return whether that exact zone answered.

    Best-effort: a missing expansion unit simply times out or answers with a
    different zone number, either of which means "not present," not a
    validation failure - only the Zone 11 confirmation above is required.
    """
    port.reset_input_buffer()
    port.write(f"?{zone}\r".encode("ascii"))
    port.flush()
    try:
        status = _read_zone_status(port)
    except TimeoutError:
        return False
    return status is not None and status.zone == zone


def _detect_expansion_units(port: serialx.BaseSerial) -> tuple[int, ...]:
    """Probe for unit 2, then unit 3 only if unit 2 answered.

    Mirrors `MonopriceCoordinator._async_discover_active_units`'s ordering:
    units are numbered contiguously, so there is no unit 3 without a unit 2.
    """
    units = [1]
    if _probe_zone(port, 21):
        units.append(2)
        if _probe_zone(port, 31):
            units.append(3)
    return tuple(units)


def validate_monoprice_endpoint(
    port_url: str,
    baud_candidates: tuple[int, ...] = SUPPORTED_BAUD_RATES,
) -> ValidationResult:
    """Verify a Monoprice amplifier on one submitted endpoint, then close it.

    The validator sends only the documented wake and Zone 11 query commands.
    It never changes the amplifier's configured baud rate.
    """
    port: serialx.BaseSerial | None = None
    try:
        port = serialx.serial_for_url(
            port_url,
            baudrate=POWER_ON_BAUD_RATE,
            stopbits=serialx.StopBits.ONE,
            byte_size=8,
            parity=serialx.Parity.NONE,
            read_timeout=VALIDATION_TIMEOUT,
            write_timeout=VALIDATION_TIMEOUT,
        )
        port.open()
    except (serialx.SerialException, PermissionError, OSError) as err:
        if port is not None and not port.closed:
            port.close()
        raise CannotOpenPort(port_url) from err

    try:
        for baud in baud_candidates:
            port.baudrate = baud
            port.reset_input_buffer()
            port.reset_output_buffer()

            port.write(b"\r\n")
            port.flush()
            sleep(0.05)
            port.reset_input_buffer()

            port.write(b"?11\r")
            port.flush()
            try:
                status = _read_zone_status(port)
            except TimeoutError:
                continue
            if status is not None and status.zone == 11:
                detected_units = _detect_expansion_units(port)
                return ValidationResult(
                    detected_baud=baud, detected_units=detected_units
                )

        raise NotMonopriceDevice(port_url)
    except TimeoutError as err:
        raise NotMonopriceDevice(port_url) from err
    except (serialx.SerialException, PermissionError, OSError) as err:
        raise CannotOpenPort(port_url) from err
    finally:
        if not port.closed:
            port.close()


def _serial_alias(real_path: str, alias_root: str) -> str | None:
    """Return the first deterministic symlink alias for a real device path."""
    if not os.path.isdir(alias_root):
        return None
    for entry in sorted(os.scandir(alias_root), key=lambda item: item.name):
        if entry.is_symlink() and os.path.realpath(entry.path) == real_path:
            return entry.path
    return None


def canonicalize_endpoint(port_url: str) -> str:
    """Return a stable endpoint without corrupting COM ports or serial URLs."""
    value = port_url.strip()
    if _COM_PORT.fullmatch(value):
        return value.upper()
    if "://" in value or not value.startswith("/dev/"):
        return value
    if value.startswith(("/dev/serial/by-id/", "/dev/serial/by-path/")):
        return value

    real_path = os.path.realpath(value)
    return (
        _serial_alias(real_path, "/dev/serial/by-id")
        or _serial_alias(real_path, "/dev/serial/by-path")
        or value
    )


def endpoint_identity(
    canonical_port: str,
    *,
    vid: str | None = None,
    pid: str | None = None,
    serial_number: str | None = None,
    interface_num: int | None = None,
) -> EndpointIdentity:
    """Build a non-secret stable unique ID from adapter metadata or endpoint."""
    if serial_number and vid and pid:
        material = ":".join(
            (
                "usb",
                vid.lower(),
                pid.lower(),
                serial_number,
                str(interface_num) if interface_num is not None else "0",
            )
        )
        kind = "usb_serial"
    else:
        normalized = (
            canonical_port.upper()
            if _COM_PORT.fullmatch(canonical_port)
            else canonical_port
        )
        material = f"endpoint:{normalized}"
        kind = "canonical_endpoint"

    digest = hashlib.sha256(material.encode()).hexdigest()
    return EndpointIdentity(key=f"monoprice:{digest}", kind=kind)
