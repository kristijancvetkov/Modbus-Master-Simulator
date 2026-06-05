import struct
from enum import Enum
from typing import Iterable, List, Sequence, Tuple


class DataType(str, Enum):
    INT16 = "INT16"
    UINT16 = "UINT16"
    INT32 = "INT32"
    UINT32 = "UINT32"
    FLOAT32 = "FLOAT32"
    BOOL = "BOOL"


TYPE_LENGTHS = {
    DataType.INT16.value: 1,
    DataType.UINT16.value: 1,
    DataType.INT32.value: 2,
    DataType.UINT32.value: 2,
    DataType.FLOAT32.value: 2,
    DataType.BOOL.value: 1,
}


def required_registers(data_type: str, requested_length: int = 1) -> int:
    if data_type == DataType.BOOL.value:
        return 1
    return max(TYPE_LENGTHS.get(data_type, 1), int(requested_length or 1))


def decode_registers(registers: Sequence[int], data_type: str):
    if not registers:
        return None

    data_type = data_type.upper()
    if data_type == DataType.BOOL.value:
        return bool(registers[0])
    if data_type == DataType.INT16.value:
        value = registers[0] & 0xFFFF
        return value - 0x10000 if value & 0x8000 else value
    if data_type == DataType.UINT16.value:
        return registers[0] & 0xFFFF

    if len(registers) < 2:
        return None

    raw = ((registers[0] & 0xFFFF) << 16) | (registers[1] & 0xFFFF)
    if data_type == DataType.INT32.value:
        return raw - 0x100000000 if raw & 0x80000000 else raw
    if data_type == DataType.UINT32.value:
        return raw
    if data_type == DataType.FLOAT32.value:
        return struct.unpack(">f", raw.to_bytes(4, byteorder="big"))[0]
    return registers[0]


def encode_value(value: str, data_type: str) -> Tuple[List[int], bool]:
    data_type = data_type.upper()
    if data_type == DataType.BOOL.value:
        return [], str(value).strip().lower() in {"1", "true", "on", "yes"}

    if data_type == DataType.FLOAT32.value:
        packed = struct.pack(">f", float(value))
        raw = int.from_bytes(packed, byteorder="big")
        return [(raw >> 16) & 0xFFFF, raw & 0xFFFF], False

    number = int(str(value).strip(), 0)
    if data_type == DataType.INT16.value:
        number &= 0xFFFF
        return [number], False
    if data_type == DataType.UINT16.value:
        if not 0 <= number <= 0xFFFF:
            raise ValueError("UINT16 value must be 0..65535")
        return [number], False
    if data_type == DataType.INT32.value:
        number &= 0xFFFFFFFF
        return [(number >> 16) & 0xFFFF, number & 0xFFFF], False
    if data_type == DataType.UINT32.value:
        if not 0 <= number <= 0xFFFFFFFF:
            raise ValueError("UINT32 value must be 0..4294967295")
        return [(number >> 16) & 0xFFFF, number & 0xFFFF], False

    raise ValueError(f"Unsupported data type: {data_type}")


def registers_to_hex(registers: Iterable[int]) -> str:
    return " ".join(f"{value & 0xFFFF:04X}" for value in registers)


def value_to_bin(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    width = 16 if -0x8000 <= number <= 0xFFFF else 32
    return format(number & ((1 << width) - 1), f"0{width}b")
