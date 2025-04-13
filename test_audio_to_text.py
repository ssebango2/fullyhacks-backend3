import pytest
import json
import os
import time
import base64
import wave
import select
import gevent
from gevent import monkey
import numpy as np
from unittest.mock import patch, MagicMock, ANY
import websocket
from flask_socketio import SocketIOTestClient

# Import the server module
import server

# Create a fixture for the Flask app and SocketIO test client
@pytest.fixture
def socketio_client():
    server.app.config['TESTING'] = True
    client = SocketIOTestClient(server.app, server.socketio)
    client.connect()  # Connect the client
    return client

# Create a mock for the Deepgram WebSocket
@pytest.fixture
def mock_websocket():
    with patch('websocket.WebSocketApp') as mock_ws:
        # Configure the mock
        mock_instance = MagicMock()
        mock_ws.return_value = mock_instance
        
        # Mock the run_forever method
        mock_instance.run_forever.return_value = None
        
        yield mock_instance

# Test connection handling
def test_websocket_connection(socketio_client, mock_websocket):
    """Test that a WebSocket connection is established when a client connects."""
    with patch('server.client_connections', {}) as mock_connections:
        # Use a test session ID instead of trying to access socketio_client.sid
        test_sid = "test_session_id"
        
        # Call the connect_to_deepgram function directly
        server.connect_to_deepgram(test_sid)
        
        # Verify WebSocketApp was created with correct parameters
        websocket.WebSocketApp.assert_called_once_with(
            server.DEEPGRAM_WS_URL,
            header={"Authorization": f"Token {server.DEEPGRAM_API_KEY}"},
            on_message=ANY,
            on_error=ANY,
            on_close=ANY
        )
        
        # Verify run_forever was called
        mock_websocket.run_forever.assert_called_once()
        
        # Verify client connection was stored
        assert test_sid in mock_connections

# Test audio processing
def test_audio_processing(socketio_client, mock_websocket):
    """Test sending audio data to the server."""
    with patch('server.client_connections') as mock_connections:
        # Use a test session ID instead of trying to access socketio_client.sid
        test_sid = "test_session_id"
        mock_connections.__getitem__.return_value = mock_websocket
        mock_connections.__contains__.return_value = True
        
        # Create some dummy audio data
        audio_data = b'dummy_audio_data'
        
        # Instead of using socketio_client.emit, simulate the event handler directly
        server.handle_audio(audio_data, test_sid)
        
        # Verify that send was called with the audio data
        mock_websocket.send.assert_called_once_with(audio_data, opcode=websocket.ABNF.OPCODE_BINARY)

# Test transcription handling
def test_transcription_handling():
    """Test the handling of transcription data from Deepgram."""
    # Create a sample Deepgram response
    sample_response = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "this is a test transcription"
                        }
                    ]
                }
            ]
        }
    }
    
    # Create a mock for the on_message callback
    with patch('server.socketio.emit') as mock_emit:
        # Get the on_message callback
        with patch('websocket.WebSocketApp') as mock_ws:
            client_sid = "test_sid"
            server.connect_to_deepgram(client_sid)
            # Extract the on_message callback
            on_message_callback = mock_ws.call_args[1]['on_message']
            
            # Call the callback with the sample response
            on_message_callback(None, json.dumps(sample_response))
            
            # Verify that the transcription was emitted
            mock_emit.assert_called_with('transcription', ANY, room=client_sid)

# Test wake word detection
def test_wake_word_detection():
    """Test the detection of the wake word in transcriptions."""
    # Create a sample Deepgram response with wake word
    sample_response = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "hey harmon what is the weather today"
                        }
                    ]
                }
            ]
        }
    }
    
    # Create mocks
    with patch('server.socketio.emit') as mock_emit, \
         patch('server.CommandProcessor.process_command') as mock_process_command:
        
        # Set up the mock for process_command
        mock_process_command.return_value = {
            'command_type': 'general_question',
            'parameters': {'query': 'what is the weather today'},
            'original_text': 'hey harmon what is the weather today'
        }
        
        # Get the on_message callback
        with patch('websocket.WebSocketApp') as mock_ws:
            client_sid = "test_sid"
            server.conversation_histories[client_sid] = []
            server.connect_to_deepgram(client_sid)
            # Extract the on_message callback
            on_message_callback = mock_ws.call_args[1]['on_message']
            
            # Call the callback with the sample response
            on_message_callback(None, json.dumps(sample_response))
            
            # Verify that process_command was called
            mock_process_command.assert_called_once()
            
            # Verify that a command_response was emitted
            assert any('command_response' in call_args[0] for call_args in mock_emit.call_args_list)

# Test sentiment analysis on transcription
def test_sentiment_analysis_on_transcription():
    """Test that sentiment analysis is performed on transcriptions."""
    # Create a sample Deepgram response
    sample_response = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "I am very happy today"
                        }
                    ]
                }
            ]
        }
    }
    
    # Create a mock for analyze_sentiment_textblob
    with patch('server.analyze_sentiment_textblob') as mock_sentiment, \
         patch('server.socketio.emit'):
        
        # Set up the mock for sentiment analysis
        mock_sentiment.return_value = {
            'polarity': 0.8,
            'subjectivity': 0.5,
            'sentiment': 'positive',
            'intervention_needed': False
        }
        
        # Get the on_message callback
        with patch('websocket.WebSocketApp') as mock_ws:
            client_sid = "test_sid"
            server.connect_to_deepgram(client_sid)
            # Extract the on_message callback
            on_message_callback = mock_ws.call_args[1]['on_message']
            
            # Call the callback with the sample response
            on_message_callback(None, json.dumps(sample_response))
            
            # Fix the case sensitivity issue - use lowercase to match how your server processes text
            mock_sentiment.assert_called_with("i am very happy today")

# Test generating a real audio sample for testing
def test_generate_audio_sample():
    """Create a sample audio file for testing purposes."""
    # This isn't a test per se, but helps generate test data
    sample_rate = 16000
    duration = 3  # seconds
    
    # Generate a simple sine wave
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    audio_data = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    
    # Create a WAV file
    output_file = "test_audio_sample.wav"
    with wave.open(output_file, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 2 bytes for int16
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())
    
    # Verify the file was created
    assert os.path.exists(output_file)
    
    # Return the path and also a base64 encoded version for browser testing
    with open(output_file, 'rb') as audio_file:
        audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')
    
    print(f"Audio sample created: {output_file}")
    print(f"Base64 encoded audio (for browser testing):")
    print(audio_base64[:100] + "...")  # Just show a preview
    
    return output_file, audio_base64

# Test reading an audio file and sending it for transcription
def test_send_audio_file(socketio_client, mock_websocket):
    """Test sending a real audio file for transcription."""
    # Skip this test if we don't want to generate audio files
    skip_file_generation = os.environ.get('SKIP_AUDIO_GENERATION', 'false').lower() == 'true'
    if skip_file_generation:
        pytest.skip("Skipping audio file generation")
    
    # Create an audio sample
    audio_file, _ = test_generate_audio_sample()
    
    with patch('server.client_connections') as mock_connections:
        # Use a test session ID instead of trying to access socketio_client.sid
        test_sid = "test_session_id"
        mock_connections.__getitem__.return_value = mock_websocket
        mock_connections.__contains__.return_value = True
        
        # Read the audio file
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
        
        # Instead of using socketio_client.emit, send audio data directly through the handler
        chunk_size = 1024
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            server.handle_audio(chunk, test_sid)
            time.sleep(0.01)  # Small delay to simulate real-time
        
        # Verify that send was called at least once
        assert mock_websocket.send.call_count > 0

# Test emotion detection
def test_emotion_detection():
    """Test the emotion detection and intervention generation."""
    # Create a sample negative sentiment result
    sentiment_data = {
        'polarity': -0.8,
        'subjectivity': 0.9,
        'sentiment': 'negative',
        'intervention_needed': True,
        'text': 'I am very angry about this'
    }
    
    # Create mocks
    with patch('server.EmotionDetector.analyze_emotion') as mock_analyze, \
         patch('server.InterventionGenerator.generate_basic_intervention') as mock_generate, \
         patch('server.socketio.emit') as mock_emit:
        
        # Set up the mocks
        mock_analyze.return_value = {
            'emotion': 'angry',
            'metrics': {
                'polarity': -0.8,
                'intensity': 0.9,
                'avg_polarity': -0.8,
                'avg_intensity': 0.9,
                'trend_slope': 0
            },
            'needs_intervention': True,
            'intervention_type': 'de-escalation'
        }
        
        mock_generate.return_value = "I notice the conversation is becoming heated. Perhaps we could take a moment to pause and reflect."
        
        # Create a sample Deepgram response with negative sentiment
        sample_response = {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "I am very angry about this situation"
                            }
                        ]
                    }
                ]
            }
        }
        
        # Get the on_message callback
        with patch('websocket.WebSocketApp') as mock_ws:
            client_sid = "test_sid"
            server.connect_to_deepgram(client_sid)
            # Extract the on_message callback
            on_message_callback = mock_ws.call_args[1]['on_message']
            
            # Replace the analyze_sentiment_textblob function
            with patch('server.analyze_sentiment_textblob', return_value=sentiment_data):
                # Call the callback with the sample response
                on_message_callback(None, json.dumps(sample_response))
                
                # Verify that an intervention was emitted
                intervention_calls = [call for call in mock_emit.call_args_list if call[0][0] == 'intervention']
                assert len(intervention_calls) > 0

# Integration test for a full transcription flow
def test_transcription_flow(socketio_client):
    """Test the complete flow from audio input to transcription to command handling."""
    # This is more of an integration test that requires mocking
    with patch('websocket.WebSocketApp') as mock_ws, \
         patch('server.client_connections') as mock_connections, \
         patch('server.socketio.emit') as mock_emit, \
         patch('server.translate_with_cerebras') as mock_translate:
        
        # Set up the mocks
        mock_instance = MagicMock()
        mock_ws.return_value = mock_instance
        mock_instance.run_forever.return_value = None
        
        # Use a test session ID instead of trying to access socketio_client.sid
        test_sid = "test_session_id"
        
        # Mock message handler to simulate Deepgram responses
        def simulate_response(*args, **kwargs):
            # Simulate a delay
            time.sleep(0.1)
            
            # Create a sample response with a command
            sample_response = {
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "transcript": "harmon translate hello to spanish"
                                }
                            ]
                        }
                    ]
                }
            }
            
            # Get the on_message callback
            on_message_callback = mock_ws.call_args[1]['on_message']
            
            # Call it with our sample response
            on_message_callback(None, json.dumps(sample_response))
            
            return None
        
        # Set up the client connections mock
        mock_instance.send.side_effect = simulate_response
        mock_connections.__getitem__.return_value = mock_instance
        mock_connections.__contains__.return_value = True
        
        # Set up translation mock
        mock_translate.return_value = {
            'success': True,
            'original_text': 'hello',
            'translated_text': 'hola',
            'target_language': 'spanish'
        }
        
        # Start the connection
        server.connect_to_deepgram(test_sid)
        
        # Send audio data directly through the handler
        server.handle_audio(b'dummy_audio_data', test_sid)
        
        # Wait for processing
        time.sleep(0.5)
        
        # Verify that a command_response was emitted
        command_calls = [call for call in mock_emit.call_args_list if call[0][0] == 'command_response']
        assert len(command_calls) > 0
        
        # Verify the command response was for translation
        for call in command_calls:
            args = call[0]
            if args[0] == 'command_response' and isinstance(args[1], dict):
                assert args[1].get('command_type') == 'translate'
                result = args[1].get('result', {})
                assert result.get('translated_text') == 'hola'

if __name__ == "__main__":
    pytest.main(["-v"])