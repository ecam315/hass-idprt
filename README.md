# iDPRT Label Printer for Home Assistant

Prints to iDPRT TSPL label printers (SP320 and similar) over Bluetooth LE, including through ESPHome Bluetooth proxies.

- `idprt.print` takes the same `payload` list as `niimbot.print` (text, multiline, rectangle, line, icon, qrcode), drawn on a canvas (default 591x354) and scaled to the label.
- `idprt.print_raw` sends TSPL commands as-is.
- Entities: **Test print** button, **In range** sensor, **Last label** image.
- Options: label size, gap, darkness, speed, direction, offsets, bitmap inversion, BLE write characteristic override.

Close the HereLabel phone app before printing; the printer accepts one Bluetooth connection at a time.

Fonts: DejaVu Sans Bold (Bitstream Vera license) and Material Design Icons (Apache 2.0 / OFL); licenses in `custom_components/idprt/fonts`.
