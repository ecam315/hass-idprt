"""Config flow: pick the printer from Bluetooth discovery or enter its MAC."""
from __future__ import annotations

import re

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak, async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_DENSITY, CONF_DIRECTION, CONF_GAP, CONF_INVERT, CONF_LABEL_HEIGHT,
    CONF_LABEL_WIDTH, CONF_SPEED, CONF_WRITE_CHAR, CONF_X_OFFSET, CONF_Y_OFFSET,
    DEFAULTS, DOMAIN, KNOWN_WRITE_PAIRS,
)

MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
PRINTER_SERVICES = {svc for svc, _ in KNOWN_WRITE_PAIRS}
MANUAL = "manual"


def _looks_like_printer(info: BluetoothServiceInfoBleak) -> bool:
    name = (info.name or "").upper()
    if any(k in name for k in ("SP320", "IDPRT", "PRINT", "SP3", "SP4")):
        return True
    return bool(PRINTER_SERVICES & {u.lower() for u in info.service_uuids})


class IdprtConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._found: dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> IdprtOptionsFlow:
        return IdprtOptionsFlow()

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        assert self._discovery
        if user_input is not None:
            return self._create(self._discovery.address, user_input.get(CONF_NAME))
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_NAME, default="iDPRT SP320"): str}),
            description_placeholders={"name": self._discovery.name or "unnamed",
                                      "address": self._discovery.address},
        )

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            choice = user_input[CONF_ADDRESS]
            if choice == MANUAL:
                return await self.async_step_manual()
            await self.async_set_unique_id(choice.upper(), raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create(choice, user_input.get(CONF_NAME))

        configured = self._async_current_ids(include_ignore=False)
        infos = [i for i in async_discovered_service_info(self.hass, connectable=True)
                 if i.address.upper() not in configured]
        likely = [i for i in infos if _looks_like_printer(i)]
        for info in sorted(likely or infos, key=lambda i: -(i.rssi or -127))[:30]:
            self._found[info.address] = f"{info.name or 'unnamed'}  ({info.address}, {info.rssi} dBm)"
        options = {**self._found, MANUAL: "Enter MAC address manually"}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(options),
                vol.Optional(CONF_NAME, default="iDPRT SP320"): str,
            }),
            errors=errors,
        )

    async def async_step_manual(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            addr = user_input[CONF_ADDRESS].strip().upper().replace("-", ":")
            if not MAC_RE.match(addr):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(addr, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self._create(addr, user_input.get(CONF_NAME))
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_NAME, default="iDPRT SP320"): str,
            }),
            errors=errors,
        )

    def _create(self, address: str, name: str | None) -> ConfigFlowResult:
        return self.async_create_entry(
            title=name or "iDPRT SP320", data={CONF_ADDRESS: address.upper()},
            options=dict(DEFAULTS))


class IdprtOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        o = {**DEFAULTS, **self.config_entry.options}
        schema = vol.Schema({
            vol.Required(CONF_LABEL_WIDTH, default=o[CONF_LABEL_WIDTH]): vol.All(vol.Coerce(float), vol.Range(10, 80)),
            vol.Required(CONF_LABEL_HEIGHT, default=o[CONF_LABEL_HEIGHT]): vol.All(vol.Coerce(float), vol.Range(10, 300)),
            vol.Required(CONF_GAP, default=o[CONF_GAP]): vol.All(vol.Coerce(float), vol.Range(0, 10)),
            vol.Required(CONF_DENSITY, default=o[CONF_DENSITY]): vol.All(vol.Coerce(int), vol.Range(0, 15)),
            vol.Required(CONF_SPEED, default=o[CONF_SPEED]): vol.All(vol.Coerce(int), vol.Range(1, 7)),
            vol.Required(CONF_DIRECTION, default=o[CONF_DIRECTION]): vol.In([0, 1]),
            vol.Required(CONF_X_OFFSET, default=o[CONF_X_OFFSET]): vol.All(vol.Coerce(float), vol.Range(-20, 40)),
            vol.Required(CONF_Y_OFFSET, default=o[CONF_Y_OFFSET]): vol.All(vol.Coerce(float), vol.Range(-20, 40)),
            vol.Required(CONF_INVERT, default=o[CONF_INVERT]): bool,
            vol.Optional(CONF_WRITE_CHAR, default=o[CONF_WRITE_CHAR]): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
