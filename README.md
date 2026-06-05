# Modbus Master Simulator

A Python desktop Modbus master simulator with a PyQt5 dark interface, inspired by Modbus Poll.

## Features

- Modbus RTU serial and Modbus TCP/IP connection modes
- Serial COM port discovery and refresh
- Configurable baudrate, parity, stop bits, data bits, slave ID, and timeout
- Register scanner for FC01, FC02, FC03, and FC04
- Live register table with aliases, datatypes, raw hex display, global/per-row auto polling, write dialog, and context menu
- Bottom log console with TX/RX hex, status, log filtering, clear, and save
- Session save/load as JSON plus autosave/restore of the last session
- Human-readable handling for common Modbus exception codes

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Notes

- Addresses are entered as zero-based Modbus protocol addresses. If your device manual uses 40001-style notation, address 40001 is usually entered as `0` with FC03.
- FC01 and FC02 read bits. FC03 and FC04 read 16-bit registers. FC02 and FC04 are read-only function codes.
- RTU uses CRC16 at the end of each serial frame. The log uses pymodbus packet tracing for actual TX/RX bytes when available, with protocol-correct fallback formatting for decoded responses.
- FLOAT32, INT32, and UINT32 use two registers in big-endian word order.

## Project Structure

```text
modbus_master/
├── main.py
├── ui/
│   ├── main_window.py
│   ├── connection_panel.py
│   ├── register_table.py
│   ├── scanner_panel.py
│   └── log_panel.py
└── core/
    ├── modbus_client.py
    ├── data_types.py
    ├── port_scanner.py
    └── session.py
```
