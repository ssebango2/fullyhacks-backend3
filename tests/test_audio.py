import os
import base64
import json
import requests
import time
import traceback
import sys
from socketio import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Debug configuration
DEBUG = True  # Set to False to reduce console output

def debug_print(*args):
    """Print debug messages when DEBUG is True"""
    if DEBUG:
        print(*args)

# Server details
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:8080')

# Initialize Socket.IO client
sio = Client(reconnection=True, reconnection_attempts=5, reconnection_delay=1)
socket_connected = False

# Global event tracking
received_events = {
    'transcript_update': [],
    'summary': None,
    'notes_update': None,
    'error': None
}

# Reset the event tracking
def reset_events():
    received_events['transcript_update'] = []
    received_events['summary'] = None
    received_events['notes_update'] = None
    received_events['error'] = None

# Socket.IO event handlers
@sio.event
def connect():
    global socket_connected
    socket_connected = True
    debug_print("Socket.IO connected!")

@sio.event
def disconnect():
    global socket_connected
    socket_connected = False
    debug_print("Socket.IO disconnected!")

@sio.event
def connection_status(data):
    debug_print(f"Connection status: {data}")

@sio.event
def error(data):
    debug_print(f"ERROR: {data.get('message', 'Unknown error')}")
    received_events['error'] = data

@sio.event
def transcript_update(data):
    print("\n=== Transcript Update ===")
    received_events['transcript_update'].append(data)
    
    if isinstance(data, dict):
        if 'segments' in data:
            for segment in data['segments']:
                print(f"Speaker {segment.get('speaker', '?')}: {segment.get('text', '')}")
        elif 'text' in data:
            print(f"New text: {data['text']}")
        elif 'transcript' in data:
            # Handle receiving full transcript history
            for key, segment in data['transcript'].items():
                if isinstance(segment, dict) and 'text' in segment:
                    print(f"{key}: {segment['text']}")
    print("=========================")

@sio.event
def transcript_history(data):
    if isinstance(data, dict) and 'transcript' in data:
        print("\n=== Transcript History ===")
        for key, segment in data['transcript'].items():
            if 'text' in segment:
                print(f"{key}: {segment['text']}")
        print("==========================")

@sio.event
def summary(data):
    received_events['summary'] = data
    print("\n=== SUMMARY RECEIVED ===")
    print(data.get('summary', 'No summary content'))
    print("=======================")

@sio.event
def notes_update(data):
    received_events['notes_update'] = data
    print("\n=== NOTES RECEIVED ===")
    print(f"Point: {data.get('point', 'No point')}")
    print("Solutions:")
    for sol in data.get('solutions', []):
        print(f"- {sol}")
    print("=====================")

@sio.event
def user_joined(data):
    debug_print(f"User joined: {data}")

@sio.event
def processing_status(data):
    debug_print(f"Processing status: {data.get('status', '?')} - {data.get('message', 'No message')}")

def validate_file_path(file_path):
    """Check if the file exists"""
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return False
    return True

def audio_file_to_base64(file_path):
    """Convert audio file to base64"""
    try:
        with open(file_path, "rb") as audio_file:
            return base64.b64encode(audio_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Base64 conversion error: {str(e)}")
        traceback.print_exc()
        return None

def create_discussion():
    """Create a new discussion thread"""
    try:
        debug_print("Creating new discussion...")
        response = requests.post(
            f"{SERVER_URL}/api/discussions",
            json={"title": f"Test Discussion {time.time()}"},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error creating discussion: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

def send_audio_to_server(discussion_id, audio_base64):
    """Send audio data to server"""
    try:
        debug_print("Sending audio to server...")
        response = requests.post(
            f"{SERVER_URL}/api/audio",
            json={
                "discussion_id": discussion_id,
                "audio": audio_base64
            },
            timeout=20
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error sending audio: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

def get_transcript(discussion_id):
    """Retrieve transcript from server"""
    try:
        debug_print("Fetching transcript...")
        response = requests.get(
            f"{SERVER_URL}/api/discussions/{discussion_id}/transcript",
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting transcript: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

def connect_socket(discussion_id=None):
    """Connect to Socket.IO server and optionally join a discussion"""
    global socket_connected
    
    # Disconnect first if already connected
    if sio.connected:
        sio.disconnect()
        time.sleep(1)
    
    # Connect to server
    try:
        debug_print(f"Connecting to Socket.IO at {SERVER_URL}...")
        
        # Try multiple transports if needed
        try:
            sio.connect(SERVER_URL, transports=['websocket'], wait_timeout=10)
        except Exception as e:
            print(f"Websocket transport failed, trying polling: {e}")
            sio.connect(SERVER_URL, wait_timeout=10)
        
        # Wait for connection
        timeout = 10
        start_time = time.time()
        while not socket_connected and time.time() - start_time < timeout:
            time.sleep(0.2)
        
        if not socket_connected:
            print("Socket.IO connection timed out")
            return False
            
        # Join discussion if ID provided
        if discussion_id:
            debug_print(f"Joining discussion {discussion_id}...")
            sio.emit('join_discussion', {'discussion_id': discussion_id})
            time.sleep(2)  # Increased delay to process join
            
        return True
    except Exception as e:
        print(f"Socket.IO connection error: {str(e)}")
        traceback.print_exc()
        return False

def test_basic_audio(audio_file_path):
    """Test audio processing with a pre-recorded audio file"""
    reset_events()  # Reset event tracking
    
    try:
        # Create discussion
        response = create_discussion()
        if "error" in response:
            print(f"Discussion creation failed: {response['error']}")
            return False
            
        discussion_id = response.get("discussion_id")
        print(f"\nDiscussion ID: {discussion_id}")
        
        # Connect Socket.IO and join discussion
        if not connect_socket(discussion_id):
            print("Socket.IO connection failed")
            return False
        
        # Validate audio file
        if not validate_file_path(audio_file_path):
            print(f"Audio file not found: {audio_file_path}")
            return False
            
        # Convert audio to base64
        audio_base64 = audio_file_to_base64(audio_file_path)
        if not audio_base64:
            print("Base64 conversion failed")
            return False
            
        # Send audio to server
        print("\nSending audio to server...")
        response = send_audio_to_server(discussion_id, audio_base64)
        if "error" in response:
            print(f"Send audio failed: {response['error']}")
            return False
            
        # Wait for transcript updates
        print("\nProcessing... (waiting for transcription)")
        timeout = 30  # Increased timeout to 30 seconds
        start_time = time.time()
        
        while not received_events['transcript_update'] and time.time() - start_time < timeout:
            print(".", end='', flush=True)
            time.sleep(1)
            
            # Check for errors
            if received_events['error']:
                print(f"\nError received: {received_events['error'].get('message', 'Unknown error')}")
                return False
        
        print("\n")
        
        # Check if we got any transcript updates
        if not received_events['transcript_update']:
            print("No transcript updates received before timeout")
            return False
            
        # Get final transcript from server
        transcript = get_transcript(discussion_id)
        if "error" in transcript:
            print(f"Error getting final transcript: {transcript['error']}")
            return False
        
        # Display final transcript
        print("\n=== Final Transcript ===")
        if isinstance(transcript, dict) and transcript:
            for key, value in transcript.items():
                if isinstance(value, dict) and 'text' in value:
                    print(f"{key}: {value.get('text', 'No text')}")
        else:
            print("No transcript data available")
        print("=======================")
        
        # Clean up
        if sio.connected:
            sio.disconnect()
            
        return bool(transcript)
        
    except Exception as e:
        print(f"Unexpected error in test_basic_audio: {str(e)}")
        traceback.print_exc()
        if sio.connected:
            sio.disconnect()
        return False

def test_wake_word(initial_audio_file, command_audio_file):
    """Test wake word functionality with pre-recorded audio files"""
    reset_events()  # Reset event tracking
    
    try:
        # Create discussion
        print("\n=== Starting Wake Word Test ===")
        response = create_discussion()
        if "error" in response:
            print(f"Discussion creation failed: {response['error']}")
            return False
            
        discussion_id = response.get("discussion_id")
        print(f"Discussion ID: {discussion_id}")
        
        # Connect Socket.IO and join discussion
        if not connect_socket(discussion_id):
            print("Socket.IO connection failed")
            return False
            
        # Step 1: Send initial audio
        print("\nSending initial audio...")
        if not validate_file_path(initial_audio_file):
            print(f"Initial audio file not found: {initial_audio_file}")
            return False
            
        audio_base64 = audio_file_to_base64(initial_audio_file)
        if not audio_base64:
            print("Base64 conversion of initial audio failed")
            return False
            
        response = send_audio_to_server(discussion_id, audio_base64)
        if "error" in response:
            print(f"Send initial audio failed: {response['error']}")
            return False
            
        # Wait for initial transcription
        print("Waiting for initial transcription...")
        timeout = 20  # Increased timeout to 20 seconds
        start_time = time.time()
        
        while not received_events['transcript_update'] and time.time() - start_time < timeout:
            print(".", end='', flush=True)
            time.sleep(0.5)
            
            # Check for errors
            if received_events['error']:
                print(f"\nError received: {received_events['error'].get('message', 'Unknown error')}")
                return False
                
        print("\n")
        
        if not received_events['transcript_update']:
            print("No transcript updates received for initial audio before timeout")
            return False
            
        # Step 2: Send command audio (with wake word)
        print("\nSending command audio with wake word...")
        if not validate_file_path(command_audio_file):
            print(f"Command audio file not found: {command_audio_file}")
            return False
            
        # Reset events to track only command responses
        reset_events()
        
        audio_base64 = audio_file_to_base64(command_audio_file)
        if not audio_base64:
            print("Base64 conversion of command audio failed")
            return False
            
        response = send_audio_to_server(discussion_id, audio_base64)
        if "error" in response:
            print(f"Send command audio failed: {response['error']}")
            return False
            
        # Wait for responses (summary or notes)
        print("\nWaiting for wake word command responses (45 seconds max)...")
        start_time = time.time()
        timeout = 45  # Increased timeout
        
        while time.time() - start_time < timeout:
            # Check if we've received either summary or notes update
            if received_events['summary'] is not None or received_events['notes_update'] is not None:
                break
                
            # Check for errors
            if received_events['error']:
                print(f"\nError received: {received_events['error'].get('message', 'Unknown error')}")
                return False
                
            print(".", end="", flush=True)
            time.sleep(1)
            
        print("\n")
        
        # Check results
        got_summary = received_events['summary'] is not None
        got_notes = received_events['notes_update'] is not None
        
        if not (got_summary or got_notes):
            print("❌ No summary or notes received before timeout")
            
            # Check if we at least got transcript updates
            if received_events['transcript_update']:
                print("Partial transcript received:")
                for update in received_events['transcript_update']:
                    if isinstance(update, dict) and 'text' in update:
                        print(f"- {update['text']}")
            else:
                print("No transcript updates received either")
                
            return False
            
        # Report success
        print("\n=== Test Results ===")
        if got_summary:
            print("✅ Summary functionality working")
        if got_notes:
            print("✅ Notes functionality working")
            
        # Clean up
        if sio.connected:
            sio.disconnect()
            
        return True
        
    except Exception as e:
        print(f"Unexpected error in test_wake_word: {str(e)}")
        traceback.print_exc()
        if sio.connected:
            sio.disconnect()
        return False

def join_existing_discussion(discussion_id):
    """Join an existing discussion and listen for updates"""
    reset_events()  # Reset event tracking
    
    print(f"\n=== Joining Existing Discussion {discussion_id} ===")
    
    # Connect to Socket.IO and join discussion
    if not connect_socket(discussion_id):
        print("Socket.IO connection failed")
        return False
        
    print("Successfully joined discussion. Listening for updates...")
    print("Press Ctrl+C to exit")
    
    try:
        # Keep listening until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping listener...")
    finally:
        # Clean up
        if sio.connected:
            sio.disconnect()
            
    return True

def find_audio_file(filename, possible_dirs):
    """Try to find an audio file in various directories"""
    for directory in possible_dirs:
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            return path
    return None

if __name__ == "__main__":
    DEFAULT_AUDIO_DIR = os.path.join(os.path.expanduser("~"), "test_audio_files")
    
    # Try to find audio files in common locations
    possible_dirs = [
        DEFAULT_AUDIO_DIR,
        os.path.join(os.path.expanduser("~"), "fullyhacks/tests/prerecorded_files"),
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "audio_files"),
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "test_audio"),
        "audio_files",
        "test_audio",
        "test_files"
    ]
    
    # Check server health first
    try:
        print(f"Checking server health at {SERVER_URL}...")
        response = requests.get(f"{SERVER_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is healthy")
        else:
            print(f"❌ Server returned status code {response.status_code}")
            print("Please ensure the server is running before running tests")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Server connection failed: {str(e)}")
        print("Please ensure the server is running before running tests")
        sys.exit(1)

    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        # Join existing discussion
        if command == "join" and len(sys.argv) >= 3:
            discussion_id = sys.argv[2]
            join_existing_discussion(discussion_id)
            sys.exit(0)
            
        # Basic audio test with provided file
        elif command == "test" and len(sys.argv) >= 3:
            audio_path = sys.argv[2]
            if not os.path.exists(audio_path):
                print(f"Audio file not found: {audio_path}")
                sys.exit(1)
            
            print(f"Running basic audio test with: {audio_path}")
            result = test_basic_audio(audio_path)
            
            if result:
                print("\n✅ Basic audio test PASSED")
                sys.exit(0)
            else:
                print("\n❌ Basic audio test FAILED")
                sys.exit(1)
                
        # Wake word test with provided files
        elif command == "wake" and len(sys.argv) >= 4:
            initial_audio = sys.argv[2]
            command_audio = sys.argv[3]
            
            if not os.path.exists(initial_audio):
                print(f"Initial audio file not found: {initial_audio}")
                sys.exit(1)
                
            if not os.path.exists(command_audio):
                print(f"Command audio file not found: {command_audio}")
                sys.exit(1)
                
            print(f"Running wake word test with:")
            print(f"Initial audio: {initial_audio}")
            print(f"Command audio: {command_audio}")
            
            result = test_wake_word(initial_audio, command_audio)
            
            if result:
                print("\n✅ Wake word test PASSED")
                sys.exit(0)
            else:
                print("\n❌ Wake word test FAILED")
                sys.exit(1)
    
    # If no valid command provided, show usage
    print("Audio Testing Utility")
    print("=====================")
    print("\nUsage:")
    print("  python test_audio.py test <audio_file_path>")
    print("  python test_audio.py wake <initial_audio_path> <command_audio_path>")
    print("  python test_audio.py join <discussion_id>")
    print("\nExamples:")
    print("  python test_audio.py test ./audio_files/test_sample.wav")
    print("  python test_audio.py wake ./audio_files/normal_speech.wav ./audio_files/wake_command.wav")
    print("  python test_audio.py join -M1234567890")
    
    # Try to locate sample audio files
    print("\nLooking for audio files in common locations...")
    found_files = []
    
    for directory in possible_dirs:
        if os.path.exists(directory):
            audio_files = [f for f in os.listdir(directory) if f.endswith(('.wav', '.mp3', '.ogg'))]
            if audio_files:
                print(f"Found {len(audio_files)} audio file(s) in {directory}:")
                for audio_file in audio_files[:5]:  # Show up to 5 files
                    found_files.append(os.path.join(directory, audio_file))
                    print(f"  - {audio_file}")
                if len(audio_files) > 5:
                    print(f"  - ... and {len(audio_files) - 5} more")
                    
    if found_files:
        print("\nYou can run a test with one of these files:")
        print(f"  python test_audio.py test {found_files[0]}")
    else:
        print("\nNo audio files found in common directories.")
        print("Please specify the path to an audio file when running the test.")