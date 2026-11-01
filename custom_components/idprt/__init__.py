"""iDPRT TSPL label printers (SP320 etc.) over Bluetooth LE."""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_CANVAS_H, DEFAULT_CANVAS_W, DOMAIN, EVENT_PRINTED
from .printer import IdprtPrinter

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.IMAGE]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type IdprtConfigEntry = ConfigEntry[IdprtPrinter]

_TARGET = {
    vol.Optional(CONF_DEVICE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional("entity_id"): cv.comp_entity_ids,
}

PRINT_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required("payload"): vol.Any(cv.string, list),
        vol.Optional("width", default=DEFAULT_CANVAS_W): vol.Coerce(int),
        vol.Optional("height", default=DEFAULT_CANVAS_H): vol.Coerce(int),
        vol.Optional("copies", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
        vol.Optional("rotate", default=0): vol.All(vol.Coerce(int), vol.In([0, 90, 180, 270])),
        # Accepted for drop-in compatibility with niimbot.print; the printer's
        # TSPL density is set in the integration options instead.
        vol.Optional("density"): vol.Coerce(int),
    },
    extra=vol.REMOVE_EXTRA,
)

RAW_SCHEMA = vol.Schema({**_TARGET, vol.Required("tspl"): cv.string})


def _resolve(hass: HomeAssistant, call: ServiceCall) -> IdprtPrinter:
    loaded = {e.entry_id: e.runtime_data for e in hass.config_entries.async_loaded_entries(DOMAIN)}
    if not loaded:
        raise HomeAssistantError("No iDPRT printer is set up")
    dev_ids = call.data.get(CONF_DEVICE_ID)
    if dev_ids:
        reg = dr.async_get(hass)
        for dev_id in [dev_ids] if isinstance(dev_ids, str) else dev_ids:
            dev = reg.async_get(dev_id)
            for entry_id in (dev.config_entries if dev else ()):
                if entry_id in loaded:
                    return loaded[entry_id]
        raise ServiceValidationError(f"Device {dev_ids} is not an iDPRT printer")
    if len(loaded) > 1:
        raise ServiceValidationError("Several iDPRT printers are set up; pass a target device")
    return next(iter(loaded.values()))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def handle_print(call: ServiceCall) -> None:
        printer = _resolve(hass, call)
        payload: Any = call.data["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError as err:
                raise ServiceValidationError(f"payload is not valid JSON: {err}") from err
        try:
            await printer.async_print_payload(
                payload, call.data["width"], call.data["height"],
                call.data["copies"], call.data["rotate"])
        except HomeAssistantError:
            hass.bus.async_fire(EVENT_PRINTED, {"address": printer.address, "success": False,
                                                "error": printer.last_error})
            raise
        hass.bus.async_fire(EVENT_PRINTED, {"address": printer.address, "success": True,
                                            "copies": call.data["copies"]})

    async def handle_raw(call: ServiceCall) -> None:
        await _resolve(hass, call).async_print_raw(call.data["tspl"])

    hass.services.async_register(DOMAIN, "print", handle_print, schema=PRINT_SCHEMA)
    hass.services.async_register(DOMAIN, "print_raw", handle_raw, schema=RAW_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IdprtConfigEntry) -> bool:
    entry.runtime_data = IdprtPrinter(
        hass, entry.data[CONF_ADDRESS].upper(), entry.title, dict(entry.options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    return True


async def _reload_on_options(hass: HomeAssistant, entry: IdprtConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: IdprtConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and (printer := getattr(entry, "runtime_data", None)):
        await printer.async_disconnect()
    return ok
