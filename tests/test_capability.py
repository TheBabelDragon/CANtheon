"""Capability discovery."""

from cantheon.schema import SchemaRegistry


def test_discover_nodes():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "temp.v1",
        "schema_version": "1.0",
        "node_id": "temp_sensor_01",
        "node_name": "Temp Sensor",
        "capabilities": ["temperature"],
        "messages": [{
            "message_id": 0x100,
            "name": "TemperatureStatus",
            "signals": [{
                "signal_id": "temperature",
                "name": "Temperature",
                "start_bit": 0,
                "bit_length": 16,
                "unit": "°C",
                "min_value": -40.0,
                "max_value": 125.0,
            }],
        }],
    })
    caps = reg.discover()
    assert len(caps) == 1
    nc = caps[0]
    assert nc.node_id == "temp_sensor_01"
    assert nc.node_name == "Temp Sensor"
    assert nc.schema_id == "temp.v1"
    assert nc.schema_version == "1.0"
    assert "temperature" in nc.capabilities
    assert len(nc.messages) == 1
    assert nc.messages[0].message_id == 0x100
    assert nc.messages[0].signals[0].signal_id == "temperature"
    assert nc.messages[0].signals[0].unit == "°C"


def test_node_capabilities():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "s1",
        "schema_version": "1.0",
        "node_id": "n1",
        "messages": [{
            "message_id": 1,
            "name": "M",
            "signals": [{"signal_id": "s", "name": "S", "start_bit": 0, "bit_length": 8}],
        }],
    })
    nc = reg.node_capabilities("n1")
    assert nc is not None
    assert nc.node_id == "n1"
    assert reg.node_capabilities("missing") is None


def test_capability_to_dict():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "s1",
        "schema_version": "1.0",
        "node_id": "n1",
        "capabilities": ["cap_a"],
        "messages": [{
            "message_id": 1,
            "name": "M",
            "is_heartbeat": True,
            "signals": [{"signal_id": "s", "name": "S", "start_bit": 0, "bit_length": 8}],
        }],
    })
    d = reg.discover()[0].to_dict()
    assert d["node_id"] == "n1"
    assert d["schema_id"] == "s1"
    assert d["messages"][0]["is_heartbeat"] is True
