"""Shared entity base."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .printer import IdprtPrinter


class IdprtEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, printer: IdprtPrinter, key: str) -> None:
        self.printer = printer
        self._attr_unique_id = f"{printer.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, printer.address)},
            connections={(CONNECTION_BLUETOOTH, printer.address)},
            name=printer.name,
            manufacturer="iDPRT",
            model="SP320",
        )
