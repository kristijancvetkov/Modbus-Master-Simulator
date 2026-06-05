from typing import List, Tuple

from serial.tools import list_ports


def list_serial_ports() -> List[Tuple[str, str]]:
    ports = []
    for port in list_ports.comports():
        label = f"{port.device} - {port.description}" if port.description else port.device
        ports.append((port.device, label))
    return ports
