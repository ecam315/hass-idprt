"""BLE transport and print pipeline for an iDPRT TSPL printer."""
from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Callable
from typing import Any

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_DENSITY, CONF_DIRECTION, CONF_DPI, CONF_GAP, CONF_INVERT,
    CONF_LABEL_HEIGHT, CONF_LABEL_WIDTH, CONF_SPEED, CONF_WRITE_CHAR,
    CONF_X_OFFSET, CONF_Y_OFFSET, DEFAULTS, IGNORED_SERVICES, KNOWN_WRITE_PAIRS,
)
from .render import render_payload, to_label
from .tspl import build_bitmap_job, mm_to_dots

_LOGGER = logging.getLogger(__name__)

IDLE_DISCONNECT_S = 20      # stay connected briefly so batches print back to back
POST_SEND_SETTLE_S = 0.4
CHUNK_STEPS = [240, 182, 128, 100, 64, 40, 20]


class IdprtPrinter:
    """One printer: owns the BLE connection and serialises jobs."""

    def __init__(self, hass: HomeAssistant, address: str, name: str,
                 options: dict[str, Any]) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.opts = {**DEFAULTS, **(options or {})}
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._char: BleakGATTCharacteristic | None = None
        self._idle_handle: asyncio.TimerHandle | None = None
        self._chunk: int | None = None   # learned max write size
        self.last_png: bytes | None = None
        self.last_error: str | None = None
        self._listeners: list[Callable[[], None]] = []

    # ---- listeners (image entity) ---------------------------------------
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ---- rendering --------------------------------------------------------
    def _dots(self) -> tuple[int, int]:
        dpi = int(self.opts[CONF_DPI])
        return (mm_to_dots(float(self.opts[CONF_LABEL_WIDTH]), dpi),
                mm_to_dots(float(self.opts[CONF_LABEL_HEIGHT]), dpi))

    def build_job(self, payload: Any, width: int, height: int,
                  copies: int = 1, rotate: int = 0) -> tuple[bytes, bytes]:
        """Executor-safe: render payload -> (tspl bytes, preview png)."""
        canvas = render_payload(payload, width, height, rotate)
        dw, dh = self._dots()
        label = to_label(canvas, dw, dh)
        job = build_bitmap_job(
            label,
            width_mm=float(self.opts[CONF_LABEL_WIDTH]),
            height_mm=float(self.opts[CONF_LABEL_HEIGHT]),
            gap_mm=float(self.opts[CONF_GAP]),
            density=int(self.opts[CONF_DENSITY]),
            speed=int(self.opts[CONF_SPEED]),
            direction=int(self.opts[CONF_DIRECTION]),
            x_offset_mm=float(self.opts[CONF_X_OFFSET]),
            y_offset_mm=float(self.opts[CONF_Y_OFFSET]),
            dpi=int(self.opts[CONF_DPI]),
            copies=copies,
            invert=bool(self.opts[CONF_INVERT]),
        )
        buf = io.BytesIO()
        label.convert("L").save(buf, format="PNG")
        return job, buf.getvalue()

    async def async_print_payload(self, payload: Any, width: int, height: int,
                                  copies: int = 1, rotate: int = 0) -> None:
        job, png = await self.hass.async_add_executor_job(
            self.build_job, payload, width, height, copies, rotate)
        await self.async_send(job)
        self.last_png = png
        self._notify()

    async def async_print_raw(self, tspl: str) -> None:
        text = tspl.replace("\r\n", "\n").replace("\n", "\r\n")
        if not text.endswith("\r\n"):
            text += "\r\n"
        await self.async_send(text.encode("utf-8"))

    # ---- BLE --------------------------------------------------------------
    def _pick_char(self, client: BleakClientWithServiceCache) -> BleakGATTCharacteristic:
        override = str(self.opts.get(CONF_WRITE_CHAR) or "").strip().lower()
        services = client.services
        if override:
            char = services.get_characteristic(override)
            if char is None:
                raise HomeAssistantError(f"Write characteristic {override} not found on printer")
            return char
        for svc_uuid, chr_uuid in KNOWN_WRITE_PAIRS:
            svc = services.get_service(svc_uuid)
            if svc and (char := svc.get_characteristic(chr_uuid)):
                return char
        for svc in services:
            if svc.uuid.lower() in IGNORED_SERVICES:
                continue
            for char in svc.characteristics:
                if {"write", "write-without-response"} & set(char.properties):
                    return char
        raise HomeAssistantError("No writable characteristic found on printer")

    async def _ensure_connected(self) -> tuple[BleakClientWithServiceCache, BleakGATTCharacteristic]:
        if self._client and self._client.is_connected and self._char:
            return self._client, self._char
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if device is None:
            raise HomeAssistantError(
                f"{self.name} ({self.address}) is not in range of a connectable Bluetooth "
                "proxy, or it is connected to a phone app")
        client = await establish_connection(
            BleakClientWithServiceCache, device, self.name,
            disconnected_callback=self._on_disconnect, max_attempts=3)
        char = self._pick_char(client)
        if not self._char or self._char.uuid != char.uuid:
            _LOGGER.info("%s: printing via service %s characteristic %s (%s)",
                         self.name, char.service_uuid, char.uuid, ",".join(char.properties))
            for svc in client.services:
                for c in svc.characteristics:
                    _LOGGER.debug("  %s / %s %s", svc.uuid, c.uuid, c.properties)
        self._client, self._char = client, char
        return client, char

    def _on_disconnect(self, _client) -> None:
        self._client = None

    def _schedule_idle_disconnect(self) -> None:
        if self._idle_handle:
            self._idle_handle.cancel()
        self._idle_handle = self.hass.loop.call_later(
            IDLE_DISCONNECT_S,
            lambda: self.hass.async_create_background_task(
                self.async_disconnect(), "idprt idle disconnect"))

    async def async_disconnect(self) -> None:
        async with self._lock:
            client, self._client = self._client, None
            if client and client.is_connected:
                try:
                    await client.disconnect()
                except BleakError:
                    pass

    async def async_send(self, data: bytes) -> None:
        async with self._lock:
            if self._idle_handle:
                self._idle_handle.cancel()
            for attempt in (1, 2):
                try:
                    client, char = await self._ensure_connected()
                    await self._write(client, char, data)
                    self.last_error = None
                    break
                except (BleakError, TimeoutError, EOFError) as err:
                    self._client = None
                    if attempt == 2:
                        self.last_error = str(err)
                        raise HomeAssistantError(f"Print to {self.name} failed: {err}") from err
                    _LOGGER.debug("%s: write failed (%s), reconnecting", self.name, err)
            await asyncio.sleep(POST_SEND_SETTLE_S)
            self._schedule_idle_disconnect()

    async def _write(self, client, char, data: bytes) -> None:
        """Send data in chunks, stepping the chunk size down if the printer
        rejects it (ATT error 13 "Invalid attribute length"). The printer's
        characteristic can be smaller than the negotiated MTU suggests."""
        mtu = int(getattr(client, "mtu_size", 23) or 23)
        start = self._chunk or max(20, min(mtu - 3, CHUNK_STEPS[0]))
        sizes = [start] + [s for s in CHUNK_STEPS if s < start]
        for size in sizes:
            try:
                await self._write_chunks(client, char, data, size)
            except _FirstChunkRejected as err:
                _LOGGER.info("%s: %d-byte writes rejected (%s), trying smaller",
                             self.name, size, err.__cause__)
                continue
            if self._chunk != size:
                _LOGGER.info("%s: using %d-byte writes", self.name, size)
            self._chunk = size
            return
        raise BleakError("printer rejected every write size down to 20 bytes")

    async def _write_chunks(self, client, char, data: bytes, size: int) -> None:
        with_response = "write" in char.properties
        for i in range(0, len(data), size):
            try:
                await client.write_gatt_char(char, data[i:i + size], response=with_response)
            except BleakError as err:
                if i == 0 and _is_length_error(err):
                    raise _FirstChunkRejected from err
                raise
            if not with_response:
                await asyncio.sleep(0.02)   # no ACKs: pace so the proxy/printer keep up


class _FirstChunkRejected(Exception):
    """The very first write was too long; nothing reached the printer."""


def _is_length_error(err: Exception) -> bool:
    text = str(err).lower()
    return "invalid attribute length" in text or "error=13" in text
