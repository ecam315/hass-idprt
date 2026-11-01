"""'Last label' image: exactly what was sent to the print head."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import IdprtConfigEntry
from .entity import IdprtEntity


async def async_setup_entry(hass: HomeAssistant, entry: IdprtConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([IdprtLastLabel(hass, entry.runtime_data)])


class IdprtLastLabel(IdprtEntity, ImageEntity):
    _attr_translation_key = "last_label"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, printer) -> None:
        IdprtEntity.__init__(self, printer, "last_label")
        ImageEntity.__init__(self, hass)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _updated() -> None:
            self._attr_image_last_updated = dt_util.utcnow()
            self.async_write_ha_state()

        self.async_on_remove(self.printer.add_listener(_updated))

    async def async_image(self) -> bytes | None:
        return self.printer.last_png
