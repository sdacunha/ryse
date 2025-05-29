import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    BluetoothChange,
    async_get_scanner,
    async_ble_device_from_address,
    async_get_bleak_client,
)
from custom_components.ryse.bluetooth import RyseBLEDevice
from custom_components.ryse.cover import SmartShadeCover

_LOGGER = logging.getLogger(__name__)

# Test data
TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"
TEST_RX_UUID = "a72f2801-b0bd-498b-b4cd-4a3901388238"
TEST_TX_UUID = "a72f2802-b0bd-498b-b4cd-4a3901388238"

class MockBLEDevice:
    def __init__(self, address, name="RYSE Test Device"):
        self.address = address
        self.name = name
        self.metadata = {
            "manufacturer_data": {
                0x0409: bytes([0x40, 0x00, 0x00, 0x00, 0x00])  # Pairing mode
            }
        }

class MockBleakClient:
    def __init__(self, address):
        self.address = address
        self.is_connected = False
        self.services = {}
        self._notification_callbacks = {}

    async def connect(self):
        self.is_connected = True
        return True

    async def disconnect(self):
        self.is_connected = False

    async def pair(self):
        return True

    async def start_notify(self, char_uuid, callback):
        self._notification_callbacks[char_uuid] = callback

    async def stop_notify(self, char_uuid):
        if char_uuid in self._notification_callbacks:
            del self._notification_callbacks[char_uuid]

    async def write_gatt_char(self, char_uuid, data):
        # Simulate device response
        if len(data) >= 5 and data[0] == 0xF5 and data[2] == 0x01 and data[3] == 0x03:
            # Position request
            response = bytes([0xF5, 0x03, 0x01, 0x07, 50])  # 50% position
            if char_uuid in self._notification_callbacks:
                await self._notification_callbacks[char_uuid](char_uuid, response)

@pytest.fixture
def mock_scanner():
    """Mock the Bluetooth scanner."""
    with patch("homeassistant.components.bluetooth.async_get_scanner") as mock:
        scanner = MagicMock()
        scanner.discover = AsyncMock(return_value=[MockBLEDevice(TEST_ADDRESS)])
        mock.return_value = scanner
        yield scanner

@pytest.fixture
def mock_ble_device():
    """Mock the BLE device."""
    with patch("homeassistant.components.bluetooth.async_ble_device_from_address") as mock:
        mock.return_value = MockBLEDevice(TEST_ADDRESS)
        yield mock

@pytest.fixture
def mock_bleak_client():
    """Mock the BleakClient."""
    with patch("homeassistant.components.bluetooth.async_get_bleak_client") as mock:
        client = MockBleakClient(TEST_ADDRESS)
        mock.return_value = client
        yield client

@pytest.mark.asyncio
async def test_device_discovery(mock_scanner):
    """Test device discovery."""
    device = RyseBLEDevice(TEST_ADDRESS, TEST_RX_UUID, TEST_TX_UUID)
    result = await device.scan_and_pair()
    assert result is True
    assert device.address == TEST_ADDRESS

@pytest.mark.asyncio
async def test_device_pairing(mock_scanner, mock_ble_device, mock_bleak_client):
    """Test device pairing."""
    device = RyseBLEDevice(TEST_ADDRESS, TEST_RX_UUID, TEST_TX_UUID)
    result = await device.pair()
    assert result is True
    assert device.client.is_connected is True

@pytest.mark.asyncio
async def test_position_updates(mock_scanner, mock_ble_device, mock_bleak_client):
    """Test position updates through notifications."""
    device = RyseBLEDevice(TEST_ADDRESS, TEST_RX_UUID, TEST_TX_UUID)
    await device.pair()
    
    # Test notification handler
    position_received = asyncio.Future()
    
    async def position_callback(position):
        position_received.set_result(position)
    
    device.update_callback = position_callback
    
    # Simulate position notification
    notification_data = bytes([0xF5, 0x03, 0x01, 0x07, 75])  # 75% position
    await device._notification_handler(TEST_RX_UUID, notification_data)
    
    # Wait for callback
    position = await position_received
    assert position == 75

@pytest.mark.asyncio
async def test_advertisement_updates(mock_scanner, mock_ble_device, mock_bleak_client):
    """Test position updates through advertisements."""
    device = RyseBLEDevice(TEST_ADDRESS, TEST_RX_UUID, TEST_TX_UUID)
    await device.pair()
    
    # Test advertisement handler
    position_received = asyncio.Future()
    
    async def position_callback(position):
        position_received.set_result(position)
    
    device.update_callback = position_callback
    
    # Simulate advertisement with position data
    service_info = BluetoothServiceInfo(
        name="RYSE Test Device",
        address=TEST_ADDRESS,
        rssi=-60,
        manufacturer_data={
            0x0409: bytes([0xF5, 0x03, 0x01, 0x07, 25])  # 25% position
        },
        service_data={},
        service_uuids=[],
        source="test",
    )
    
    device._device_update(service_info, BluetoothChange.ADVERTISEMENT)
    
    # Wait for callback
    position = await position_received
    assert position == 25

@pytest.mark.asyncio
async def test_cover_entity(mock_scanner, mock_ble_device, mock_bleak_client):
    """Test the cover entity integration."""
    device = RyseBLEDevice(TEST_ADDRESS, TEST_RX_UUID, TEST_TX_UUID)
    cover = SmartShadeCover(device)
    
    # Test opening
    await cover.async_open_cover()
    assert cover.state == "open"
    
    # Test closing
    await cover.async_close_cover()
    assert cover.state == "closed"
    
    # Test setting position
    await cover.async_set_cover_position(position=50)
    assert cover.current_cover_position == 50 