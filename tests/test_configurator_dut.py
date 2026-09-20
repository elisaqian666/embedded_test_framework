from embedded_framework.configurator.configurator_dut import load_mapping


def test_mapping_expands_environment_for_each_device(monkeypatch) -> None:
    monkeypatch.setenv("TEST_HOST_A", "192.168.1.10")
    monkeypatch.setenv("TEST_HOST_B", "192.168.1.11")
    config = load_mapping(
        {
            "devices": {
                "a": {"connections": {"http": {"protocol": "http", "options": {"base_url": "http://${TEST_HOST_A}"}}}},
                "b": {"connections": {"http": {"protocol": "http", "options": {"base_url": "http://${TEST_HOST_B}"}}}},
            }
        }
    )

    assert config.devices["a"].connections["http"].options["base_url"] == "http://192.168.1.10"
    assert config.devices["b"].connections["http"].options["base_url"] == "http://192.168.1.11"
