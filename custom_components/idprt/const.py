"""Constants for the iDPRT label printer integration."""

DOMAIN = "idprt"

CONF_LABEL_WIDTH = "label_width_mm"
CONF_LABEL_HEIGHT = "label_height_mm"
CONF_GAP = "gap_mm"
CONF_DENSITY = "density"
CONF_SPEED = "speed"
CONF_DIRECTION = "direction"
CONF_X_OFFSET = "x_offset_mm"
CONF_Y_OFFSET = "y_offset_mm"
CONF_INVERT = "invert_bitmap"
CONF_WRITE_CHAR = "write_characteristic"
CONF_DPI = "dpi"

DEFAULTS = {
    CONF_LABEL_WIDTH: 50.0,   # same 50 x 30 mm stock the Niimbot used
    CONF_LABEL_HEIGHT: 30.0,
    CONF_GAP: 2.0,
    CONF_DENSITY: 8,          # TSPL 0-15
    CONF_SPEED: 4,            # TSPL inches/sec
    CONF_DIRECTION: 1,
    CONF_X_OFFSET: 0.0,
    CONF_Y_OFFSET: 0.0,
    CONF_INVERT: False,
    CONF_WRITE_CHAR: "",
    CONF_DPI: 203,            # SP320 print head
}

# The Niimbot layouts in this house were drawn on a 591 x 354 canvas
# (50 x 30 mm at 300 dpi). Payloads keep that coordinate system and are
# scaled to the SP320's 203 dpi head at print time.
DEFAULT_CANVAS_W = 591
DEFAULT_CANVAS_H = 354

# (service, write characteristic) pairs used by common BLE thermal printers,
# tried in order before falling back to "first writable characteristic".
KNOWN_WRITE_PAIRS = [
    ("000018f0-0000-1000-8000-00805f9b34fb", "00002af1-0000-1000-8000-00805f9b34fb"),
    ("0000ff00-0000-1000-8000-00805f9b34fb", "0000ff02-0000-1000-8000-00805f9b34fb"),
    ("49535343-fe7d-4ae5-8fa9-9fafd205e455", "49535343-8841-43f4-a8d4-ecbe34729bb3"),
    ("0000fee7-0000-1000-8000-00805f9b34fb", "0000fec7-0000-1000-8000-00805f9b34fb"),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe1-0000-1000-8000-00805f9b34fb"),
]

# Standard GATT services that never carry print data.
IGNORED_SERVICES = {
    "00001800-0000-1000-8000-00805f9b34fb",
    "00001801-0000-1000-8000-00805f9b34fb",
    "0000180a-0000-1000-8000-00805f9b34fb",
    "0000180f-0000-1000-8000-00805f9b34fb",
}

EVENT_PRINTED = "idprt_printed"
