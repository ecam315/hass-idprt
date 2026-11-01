"""Test-print button."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import IdprtConfigEntry
from .const import DEFAULT_CANVAS_H, DEFAULT_CANVAS_W
from .entity import IdprtEntity


async def async_setup_entry(hass: HomeAssistant, entry: IdprtConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([IdprtTestPrint(entry.runtime_data)])


class IdprtTestPrint(IdprtEntity, ButtonEntity):
    _attr_translation_key = "test_print"

    def __init__(self, printer) -> None:
        super().__init__(printer, "test_print")

    async def async_press(self) -> None:
        now = dt_util.now().strftime("%b %d %Y  %I:%M %p")
        payload = [
            {"type": "rectangle", "x_start": 0, "x_end": DEFAULT_CANVAS_W, "y_start": 12,
             "y_end": 52, "fill": "black"},
            {"type": "text", "value": "Keepsake Farms", "x": 8, "y": 19, "size": 26, "color": "white"},
            {"type": "icon", "value": "printer-check", "x": 8, "y": 70, "size": 70},
            {"type": "text", "value": "Test print OK", "x": 90, "y": 88, "size": 48},
            {"type": "text", "value": now, "x": 8, "y": 180, "size": 32},
            {"type": "rectangle", "x_start": 2, "x_end": DEFAULT_CANVAS_W - 3, "y_start": 2,
             "y_end": DEFAULT_CANVAS_H - 3, "outline": "black", "width": 3},
        ]
        await self.printer.async_print_payload(payload, DEFAULT_CANVAS_W, DEFAULT_CANVAS_H)
