import time
from dataclasses import dataclass
from typing import Any, List, Optional

from pymodbus.client import ModbusSerialClient, ModbusTcpClient


FC_NAMES = {
    1: "Coils",
    2: "Discrete Inputs",
    3: "Holding Registers",
    4: "Input Registers",
}

EXCEPTION_MESSAGES = {
    1: "Illegal function",
    2: "Illegal data address",
    3: "Illegal data value",
    4: "Slave device failure",
}


@dataclass
class ModbusResult:
    ok: bool
    values: List[int]
    tx_hex: str
    rx_hex: str
    status: str
    error: str = ""
    elapsed_ms: float = 0.0


def crc16_modbus(data: bytes) -> int:
    # RTU frames end with a CRC16 so slaves can reject corrupted serial bytes.
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def _call_with_slave(method, *args, slave_id: int, **kwargs):
    try:
        return method(*args, device_id=slave_id, **kwargs)
    except TypeError:
        pass
    try:
        return method(*args, slave=slave_id, **kwargs)
    except TypeError:
        return method(*args, unit=slave_id, **kwargs)


class ModbusClient:
    def __init__(self):
        self.client: Optional[Any] = None
        self.mode = "RTU"
        self.slave_id = 1
        self.connected = False
        self.last_tx_hex = ""
        self.last_rx_hex = ""

    def connect(self, config: dict) -> None:
        self.disconnect()
        self.mode = config.get("mode", "RTU")
        self.slave_id = int(config.get("slave_id", 1))
        timeout_s = max(0.05, int(config.get("timeout_ms", 1000)) / 1000)

        if self.mode == "TCP":
            self.client = ModbusTcpClient(
                host=config.get("tcp_host", "127.0.0.1"),
                port=int(config.get("tcp_port", 502)),
                timeout=timeout_s,
                trace_packet=self._trace_packet,
            )
        else:
            parity_map = {"None": "N", "Even": "E", "Odd": "O", "N": "N", "E": "E", "O": "O"}
            self.client = ModbusSerialClient(
                port=config.get("port", ""),
                baudrate=int(config.get("baudrate", 9600)),
                parity=parity_map.get(config.get("parity", "None"), "N"),
                stopbits=float(config.get("stopbits", 1)),
                bytesize=int(config.get("bytesize", 8)),
                timeout=timeout_s,
                trace_packet=self._trace_packet,
            )

        if not self.client.connect():
            self.client = None
            raise ConnectionError("Unable to connect. Check port/IP settings and whether the device is already in use.")
        self.connected = True

    def disconnect(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.connected = False

    def read(self, function_code: int, address: int, count: int, slave_id: Optional[int] = None) -> ModbusResult:
        if not self.connected or self.client is None:
            return ModbusResult(False, [], "", "", "ERROR", "Not connected")

        slave = int(slave_id or self.slave_id)
        function_code = int(function_code)
        address = int(address)
        count = int(count)
        tx = self._build_read_request(slave, function_code, address, count)
        self._reset_trace()
        started = time.monotonic()

        try:
            if function_code == 1:
                result = _call_with_slave(self.client.read_coils, address, count=count, slave_id=slave)
            elif function_code == 2:
                result = _call_with_slave(self.client.read_discrete_inputs, address, count=count, slave_id=slave)
            elif function_code == 3:
                result = _call_with_slave(self.client.read_holding_registers, address, count=count, slave_id=slave)
            elif function_code == 4:
                result = _call_with_slave(self.client.read_input_registers, address, count=count, slave_id=slave)
            else:
                raise ValueError(f"Unsupported function code: {function_code}")
        except Exception as exc:
            return ModbusResult(False, [], self._tx_hex(tx), self.last_rx_hex, "ERROR", str(exc), self._elapsed(started))

        elapsed = self._elapsed(started)
        if result is None:
            return ModbusResult(False, [], self._tx_hex(tx), self.last_rx_hex, "NO RESPONSE", "No response", elapsed)
        if getattr(result, "isError", lambda: False)():
            code = int(getattr(result, "exception_code", 0) or 0)
            msg = EXCEPTION_MESSAGES.get(code, f"Modbus exception {code}")
            rx = self._build_exception_response(slave, function_code, code)
            return ModbusResult(False, [], self._tx_hex(tx), self._rx_hex(rx), "ERROR", msg, elapsed)

        values = list(getattr(result, "bits", [])) if function_code in (1, 2) else list(getattr(result, "registers", []))
        rx = self._build_read_response(slave, function_code, values, coils=function_code in (1, 2))
        return ModbusResult(True, values[:count], self._tx_hex(tx), self._rx_hex(rx), "OK", elapsed_ms=elapsed)

    def write(self, function_code: int, address: int, values: List[int], coil_value: bool = False, slave_id: Optional[int] = None) -> ModbusResult:
        if not self.connected or self.client is None:
            return ModbusResult(False, [], "", "", "ERROR", "Not connected")

        slave = int(slave_id or self.slave_id)
        self._reset_trace()
        started = time.monotonic()
        try:
            if function_code in (1, 2):
                tx = self._build_write_single_coil(slave, address, coil_value)
                result = _call_with_slave(self.client.write_coil, address, coil_value, slave_id=slave)
                written_values = [1 if coil_value else 0]
            elif len(values) == 1:
                tx = self._build_write_single_register(slave, address, values[0])
                result = _call_with_slave(self.client.write_register, address, values[0], slave_id=slave)
                written_values = [values[0]]
            else:
                tx = self._build_write_multiple_registers(slave, address, values)
                result = _call_with_slave(self.client.write_registers, address, values, slave_id=slave)
                written_values = list(values)
        except Exception as exc:
            return ModbusResult(False, [], self.last_tx_hex, self.last_rx_hex, "ERROR", str(exc), self._elapsed(started))

        elapsed = self._elapsed(started)
        if result is None:
            return ModbusResult(False, [], self._tx_hex(tx), self.last_rx_hex, "NO RESPONSE", "No response", elapsed)
        if getattr(result, "isError", lambda: False)():
            code = int(getattr(result, "exception_code", 0) or 0)
            msg = EXCEPTION_MESSAGES.get(code, f"Modbus exception {code}")
            return ModbusResult(False, [], self._tx_hex(tx), self._rx_hex(self._build_exception_response(slave, 6, code)), "ERROR", msg, elapsed)

        rx = tx if self.mode == "RTU" else self._tcp_hex_like(tx)
        return ModbusResult(True, written_values, self._tx_hex(tx), self._rx_hex(rx), "OK", elapsed_ms=elapsed)

    def _elapsed(self, started: float) -> float:
        return (time.monotonic() - started) * 1000

    def _rtu_or_tcp(self, slave: int, pdu: bytes) -> bytes:
        if self.mode == "TCP":
            # MBAP header: transaction, protocol, length, unit id, then PDU.
            return b"\x00\x01\x00\x00" + (len(pdu) + 1).to_bytes(2, "big") + bytes([slave]) + pdu
        frame = bytes([slave]) + pdu
        crc = crc16_modbus(frame)
        return frame + crc.to_bytes(2, "little")

    def _tcp_hex_like(self, request: bytes) -> bytes:
        return request

    def _reset_trace(self) -> None:
        self.last_tx_hex = ""
        self.last_rx_hex = ""

    def _trace_packet(self, sending: bool, data: bytes) -> bytes:
        if sending:
            self.last_tx_hex = bytes_to_hex(data)
        else:
            self.last_rx_hex = bytes_to_hex(data)
        return data

    def _tx_hex(self, fallback: bytes) -> str:
        return self.last_tx_hex or bytes_to_hex(fallback)

    def _rx_hex(self, fallback: bytes) -> str:
        return self.last_rx_hex or bytes_to_hex(fallback)

    def _build_read_request(self, slave: int, fc: int, address: int, count: int) -> bytes:
        return self._rtu_or_tcp(slave, bytes([fc]) + address.to_bytes(2, "big") + count.to_bytes(2, "big"))

    def _build_read_response(self, slave: int, fc: int, values: List[int], coils: bool) -> bytes:
        if coils:
            packed = bytearray()
            current = 0
            bit = 0
            for value in values:
                if value:
                    current |= 1 << bit
                bit += 1
                if bit == 8:
                    packed.append(current)
                    current = 0
                    bit = 0
            if bit:
                packed.append(current)
            pdu = bytes([fc, len(packed)]) + bytes(packed)
        else:
            body = b"".join((int(value) & 0xFFFF).to_bytes(2, "big") for value in values)
            pdu = bytes([fc, len(body)]) + body
        return self._rtu_or_tcp(slave, pdu)

    def _build_exception_response(self, slave: int, fc: int, code: int) -> bytes:
        return self._rtu_or_tcp(slave, bytes([fc | 0x80, code & 0xFF]))

    def _build_write_single_coil(self, slave: int, address: int, value: bool) -> bytes:
        raw = b"\xFF\x00" if value else b"\x00\x00"
        return self._rtu_or_tcp(slave, b"\x05" + address.to_bytes(2, "big") + raw)

    def _build_write_single_register(self, slave: int, address: int, value: int) -> bytes:
        return self._rtu_or_tcp(slave, b"\x06" + address.to_bytes(2, "big") + (value & 0xFFFF).to_bytes(2, "big"))

    def _build_write_multiple_registers(self, slave: int, address: int, values: List[int]) -> bytes:
        body = b"".join((int(value) & 0xFFFF).to_bytes(2, "big") for value in values)
        pdu = b"\x10" + address.to_bytes(2, "big") + len(values).to_bytes(2, "big") + bytes([len(body)]) + body
        return self._rtu_or_tcp(slave, pdu)
