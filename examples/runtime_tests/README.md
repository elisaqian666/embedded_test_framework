# Offline runtime example

This directory demonstrates a multi-device runtime with consumer-owned device features and a simulated laboratory helper. It does not connect to hardware.

```powershell
python -m pip install -e ".[test]"
python -m pytest examples/runtime_tests --device-config examples/runtime_tests/devices.json
```

`conftest.py` registers extensions from `product_adapters.py`. `devices.json` binds two memory devices, logging/performance features, and network workflows. Feature contracts are imported from `embedded_test_framework.dut.device_features`, helper contracts from `embedded_test_framework.helpers`, and evidence utilities from `embedded_test_framework.helpers.evidence`.

Copy the directory to a separate test repository after installing the SDK. Product commands and parsing belong in the consumer extensions; the generic framework does not hardcode product behavior.
