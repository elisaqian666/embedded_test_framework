"""Hardware test configuration. The password is resolved at load time."""
DEVICE_NAME = "linux-board"
METADATA = {"address": "192.168.1.103", "username": "root", "platform": "Linux"}
LOGGING = {"level": "info", "levels": {"engine": "debug", "dut": "info", "host": "warning"}}
SSH = {"host": "192.168.1.103", "port": 22, "username": "root", "password": "${DUT_SSH_PASSWORD}", "timeout": 10}

# Set an unused protocol to None. Only configured engines are constructed.
SERIAL = None  # {"port": "COM3", "baudrate": 115200, "timeout": 3}
ADB = None     # {"executable": "C:/Android/adb.exe", "device": "board-1", "timeout": 10}
FTP = None     # {"host": "192.168.1.103", "port": 21, "remote_path": "/image.bin", "local_path": "downloads/image.bin"}
