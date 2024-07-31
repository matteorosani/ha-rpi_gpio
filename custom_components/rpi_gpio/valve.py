"""Allows to configure a valve using RPi GPIO."""
from __future__ import annotations
from time import sleep
from typing import Any

import voluptuous as vol

from homeassistant.components.valve import (
    PLATFORM_SCHEMA, 
    STATE_OPEN,
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature
)
from homeassistant.const import (
    CONF_NAME,
    CONF_PORT,
    CONF_UNIQUE_ID,
    DEVICE_DEFAULT_NAME,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.reload import setup_reload_service
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.restore_state import RestoreEntity

from . import DOMAIN, PLATFORMS, setup_output, write_output

CONF_VALVES = "valves"
CONF_RED_WIRE_PORT = "red_wire_port"
CONF_BLACK_WIRE_PORT = "black_wire_port"

_SWITCH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_PORT): cv.positive_int,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
        {
            vol.Required(CONF_VALVES): vol.All(
                cv.ensure_list, [_SWITCH_SCHEMA]
            ),
            vol.Required(CONF_RED_WIRE_PORT): vol.positive_int,
            vol.Required(CONF_BLACK_WIRE_PORT): vol.positive_int,
        }
    )


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Raspberry PI GPIO devices."""
    setup_reload_service(hass, DOMAIN, PLATFORMS)

    valves = []

    valves_conf = config.get(CONF_VALVES)

    setup_output(valves_conf[CONF_RED_WIRE_PORT])
    setup_output(valves_conf[CONF_BLACK_WIRE_PORT])

    for valve in valves_conf:
        valves.append(
            PersistentRPiGPIOValve(
                valve[CONF_NAME],
                valve[CONF_PORT],
                valves_conf[CONF_RED_WIRE_PORT],
                valves_conf[CONF_BLACK_WIRE_PORT],
                valve.get(CONF_UNIQUE_ID)
            )
        )

    add_entities(valves, True)


class RPiGPIOValve(ValveEntity):
    """Representation of a Raspberry Pi GPIO."""

    def __init__(self, name, port, red_wire_port, black_wire_port, unique_id=None, skip_reset=False):
        """Initialize the pin."""
        self._attr_name = name or DEVICE_DEFAULT_NAME
        self._attr_unique_id = unique_id
        self._attr_should_poll = False
        self._attr_assumed_state = True
        self._attr_reports_position = False
        self._attr_device_class = ValveDeviceClass.WATER
        self._attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        self._port = port
        self._red_wire_port = red_wire_port
        self._black_wire_port = black_wire_port
        self._state = False
        setup_output(self._port)
        if not skip_reset:
            write_output(self._red_wire_port, 1)
            write_output(self._black_wire_port, 0)
            sleep(0.5)
            write_output(self._port, 1)
    
    def _pulse(self):
        write_output(self._port, 0)
        sleep(0.1)
        write_output(self._port, 1)

    @property
    def is_closed(self) -> bool | None:
        """Return true if the valve is closed."""
        return not self._state

    async def async_open_valve(self, **kwargs: Any) -> None:
        """Open the valve."""
        write_output(self._red_wire_port, 0)
        write_output(self._black_wire_port, 1)
        sleep(0.5)
        self._pulse()
        self._state = False
        self.async_write_ha_state()

    async def async_close_valve(self, **kwargs: Any) -> None:
        """Close the valve."""
        write_output(self._red_wire_port, 1)
        write_output(self._black_wire_port, 0)
        sleep(0.5)
        self._pulse()
        self._state = True
        self.async_write_ha_state()


class PersistentRPiGPIOValve(RPiGPIOValve, RestoreEntity):
    """Representation of a persistent Raspberry Pi GPIO."""

    def __init__(self, name, port, red_wire_port, black_wire_port, unique_id=None):
        """Initialize the pin."""
        super().__init__(name, port, red_wire_port, black_wire_port, unique_id, True)

    async def async_added_to_hass(self) -> None:
        """Call when the switch is added to hass."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state:
            return
        self._state = False if state.state == STATE_OPEN else True
        if self._state:
            await self.async_close_valve()
        else:
            await self.async_open_valve()