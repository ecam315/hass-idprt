"""'In range' sensor: is the printer advertising to a connectable proxy?"""
from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IdprtConfigEntry
from .entity import IdprtEntity


async def async_setup_entry(hass: HomeAssistant, entry: IdprtConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([IdprtInRange(entry.runtime_data)])


class IdprtInRange(IdprtEntity, BinarySensorEntity):
    _attr_translation_key = "in_range"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, printer) -> None:
        super().__init__(printer, "in_range")

    async def async_added_to_hass(self) -> None:
        addr = self.printer.address
        self._attr_is_on = bluetooth.async_address_present(self.hass, addr, connectable=True)

        @callback
        def _seen(_info, _change) -> None:
            if not self._attr_is_on:
                self._attr_is_on = True
                self.async_write_ha_state()

        @callback
        def _gone(_info) -> None:
            self._attr_is_on = False
            self.async_write_ha_state()

        self.async_on_remove(bluetooth.async_register_callback(
            self.hass, _seen,
            bluetooth.BluetoothCallbackMatcher(address=addr, connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE))
        self.async_on_remove(bluetooth.async_track_unavailable(
            self.hass, _gone, addr, connectable=True))
