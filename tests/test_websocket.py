import pytest
from unittest.mock import MagicMock, patch
from app import app, socketio, client_connections

@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    with app.test_client() as client:
        yield client

def test_connect_disconnect():
    """Test client connection and disconnection"""
    mock_ws = MagicMock()
    
    with patch('websocket.WebSocketApp', return_value=mock_ws):
        # Simulate client connection
        socketio_test_client = socketio.test_client(app)
        assert socketio_test_client.is_connected()
        
        # Verify Deepgram connection was initiated
        sid = socketio_test_client.sid
        assert sid in client_connections
        
        # Simulate client disconnection
        socketio_test_client.disconnect()
        assert sid not in client_connections

def test_audio_handling():
    """Test audio data forwarding"""
    mock_ws = MagicMock()
    
    with patch('websocket.WebSocketApp', return_value=mock_ws):
        socketio_test_client = socketio.test_client(app)
        sid = socketio_test_client.sid
        
        # Send test audio
        test_audio = b'\x00\x01\x02\x03'  # Mock audio data
        socketio_test_client.emit('audio', test_audio)
        
        # Verify audio was forwarded
        mock_ws.send.assert_called_once_with(test_audio, opcode=websocket.ABNF.OPCODE_BINARY)

def test_error_handling():
    """Test error scenarios"""
    # Test invalid audio format
    socketio_test_client = socketio.test_client(app)
    socketio_test_client.emit('audio', 'not-bytes-data')
    
    # Should receive error message
    received = socketio_test_client.get_received()
    assert any(msg['name'] == 'error' for msg in received)