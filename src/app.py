import os
import logging
import json
import time
import asyncio
import ssl
import certifi
import base64
from threading import Lock
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from deepgram import DeepgramClient, DeepgramClientOptions

# =============================================
# Configuration and Initialization
# =============================================

# Configure SSL
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.verify_mode = ssl.CERT_REQUIRED
os.environ['SSL_CERT_FILE'] = certifi.where()

# Load environment variables
load_dotenv()

# Validate required environment variables
required_env_vars = ['DEEPGRAM_API_KEY', 'FIREBASE_DATABASE_URL', 'SECRET_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize Firebase
try:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': os.getenv('FIREBASE_DATABASE_URL')
    })
except Exception as e:
    raise RuntimeError(f"Firebase initialization failed: {str(e)}")

# Initialize Deepgram (v3)
try:
    deepgram = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'))
    print("✅ Deepgram v3 initialized successfully")
except Exception as e:
    raise RuntimeError(f"Deepgram initialization failed: {str(e)}")

# Threading lock for audio processing
audio_lock = Lock()

# =============================================
# Helper Functions
# =============================================

def is_valid_base64(s):
    try:
        # Add padding if necessary
        padding = len(s) % 4
        if padding:
            s += '=' * (4 - padding)
        
        # Try decoding
        base64.b64decode(s)
        return True
    except Exception as e:
        print(f"Base64 validation failed: {str(e)}")
        return False

def sanitize_discussion_id(discussion_id):
    """Validates that a discussion ID is safe to use in database paths"""
    if not discussion_id:
        return False
    # Allow alphanumeric characters, hyphens, and underscores
    return all(c.isalnum() or c in '-_' for c in discussion_id)

# =============================================
# Routes
# =============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "firebase": True,
            "deepgram": True
        }
    })

@app.route('/api/discussions', methods=['GET'])
def get_discussions():
    try:
        discussions_ref = db.reference('discussions')
        discussions = discussions_ref.get()
        return jsonify(discussions or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discussions', methods=['POST'])
def create_discussion():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        title = data.get('title', f'Discussion {time.time()}')
        
        new_discussion_ref = db.reference('discussions').push()
        discussion_id = new_discussion_ref.key
        
        new_discussion_ref.set({
            'title': title,
            'created': time.time(),
            'transcript': {},
            'notes': {}
        })
        
        return jsonify({
            'status': 'success',
            'discussion_id': discussion_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discussions/<discussion_id>/transcript', methods=['GET'])
def get_transcript(discussion_id):
    if not sanitize_discussion_id(discussion_id):
        print(f"Invalid discussion ID requested: {discussion_id}")
        return jsonify({"error": "Invalid discussion ID"}), 400
        
    try:
        transcript_ref = db.reference(f'discussions/{discussion_id}/transcript')
        transcript = transcript_ref.get()
        return jsonify(transcript or {})
    except Exception as e:
        print(f"Error fetching transcript for {discussion_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/discussions/<discussion_id>/notes', methods=['GET'])
def get_notes(discussion_id):
    if not sanitize_discussion_id(discussion_id):
        return jsonify({"error": "Invalid discussion ID"}), 400
        
    try:
        notes_ref = db.reference(f'discussions/{discussion_id}/notes')
        notes = notes_ref.get()
        return jsonify(notes or {})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/audio', methods=['POST'])
def process_audio():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        discussion_id = data.get('discussion_id')
        audio_base64 = data.get('audio')
        
        if not discussion_id or not audio_base64:
            return jsonify({'error': 'Missing discussion_id or audio data'}), 400
            
        if not is_valid_base64(audio_base64):
            return jsonify({'error': 'Invalid audio data'}), 400
            
        socketio.start_background_task(
            process_audio_data, discussion_id, audio_base64
        )
        
        return jsonify({'status': 'processing'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =============================================
# Socket.IO Events
# =============================================

@socketio.on('connect')
def handle_connect():
    print('Client connected:', request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected:', request.sid)

@socketio.on('join_discussion')
def handle_join(data):
    try:
        discussion_id = data.get('discussion_id')
        if not discussion_id or not sanitize_discussion_id(discussion_id):
            emit('error', {'message': 'Invalid discussion ID'})
            return
            
        join_room(discussion_id)
        print(f'Client {request.sid} joined discussion {discussion_id}')
        
        emit('user_joined', {
            'message': 'New user joined',
            'user_id': request.sid
        }, room=discussion_id)
        
        transcript_ref = db.reference(f'discussions/{discussion_id}/transcript')
        transcript = transcript_ref.get() or {}
        emit('transcript_update', {'transcript': transcript})
    except Exception as e:
        emit('error', {'message': str(e)})

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    try:
        discussion_id = data.get('discussion_id')
        audio_base64 = data.get('audio')
        
        if not discussion_id or not audio_base64:
            emit('error', {'message': 'Missing discussion_id or audio data'})
            return
            
        if not is_valid_base64(audio_base64):
            emit('error', {'message': 'Invalid audio data'})
            return
            
        socketio.start_background_task(
            process_audio_data, discussion_id, audio_base64
        )
    except Exception as e:
        emit('error', {'message': str(e)})

# =============================================
# Audio Processing (Updated for Deepgram v3)
# =============================================

async def transcribe_audio(audio_base64):
    try:
        source = {'buffer': base64.b64decode(audio_base64), 'mimetype': 'audio/wav'}
        response = await deepgram.listen.prerecorded.v(
            "1",  # API version
            source,
            {
                'smart_format': True,
                'model': 'nova',
                'language': 'en-US',
                'diarize': True
            }
        )
        return response
    except Exception as e:
        print(f"Deepgram error: {str(e)}")
        return None

def process_audio_data(discussion_id, audio_base64):
    with audio_lock:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(transcribe_audio(audio_base64))
            
            if not response:
                print("No response from Deepgram")
                return
                
            # Debug: print response structure
            print(f"Deepgram response structure: {json.dumps(response, indent=2)[:500]}...")
            
            # Extract transcript from Deepgram v3 response structure
            if 'results' in response and 'channels' in response['results']:
                channel = response['results']['channels'][0]
                if 'alternatives' in channel and len(channel['alternatives']) > 0:
                    transcript = channel['alternatives'][0].get('transcript', '')
                else:
                    print("No alternatives found in response")
                    return
            else:
                print("Unexpected response structure from Deepgram")
                return
            
            if transcript:
                # Store in Firebase
                segment_ref = db.reference(f'discussions/{discussion_id}/transcript').push()
                segment_data = {
                    'text': transcript,
                    'timestamp': time.time()
                }
                segment_ref.set(segment_data)
                
                # Emit to clients
                print(f"Emitting transcript: {transcript}")
                socketio.emit('transcript_update', segment_data, room=discussion_id)
                
                # Check for wake words
                lower_transcript = transcript.lower()
                if "aitool" in lower_transcript or "harmon" in lower_transcript:
                    process_command(discussion_id, transcript)
                    
        except Exception as e:
            print(f"Audio processing error: {str(e)}")
            socketio.emit('error', {'message': str(e)}, room=discussion_id)

# =============================================
# Command Processing
# =============================================

def process_command(discussion_id, transcript):
    try:
        # Extract command by finding everything after the wake word
        lower_transcript = transcript.lower()
        
        if "aitool" in lower_transcript:
            command = lower_transcript.split('aitool')[-1].strip()
        elif "harmon" in lower_transcript:
            command = lower_transcript.split('harmon')[-1].strip()
        else:
            return
        
        print(f"Processing command: '{command}'")
        
        if "summarize" in command:
            summarize_recent_transcript(discussion_id)
        elif "note" in command:
            record_to_notes(discussion_id)
    except Exception as e:
        print(f"Command processing error: {str(e)}")

def summarize_recent_transcript(discussion_id):
    try:
        transcript_ref = db.reference(f'discussions/{discussion_id}/transcript')
        recent = transcript_ref.order_by_child('timestamp').limit_to_last(5).get() or {}
        
        # Collect text from recent entries
        text_entries = [item.get('text', '') for item in recent.values() if 'text' in item]
        summary = "Summary: " + " ".join(text_entries)
        
        print(f"Emitting summary: {summary}")
        
        socketio.emit('summary', {
            'summary': summary,
            'timestamp': time.time()
        }, room=discussion_id)
    except Exception as e:
        print(f"Summary error: {str(e)}")
        socketio.emit('error', {'message': str(e)}, room=discussion_id)

def record_to_notes(discussion_id):
    try:
        transcript_ref = db.reference(f'discussions/{discussion_id}/transcript')
        last_entry = transcript_ref.order_by_child('timestamp').limit_to_last(1).get()
        
        if last_entry and len(last_entry) > 0:
            last_text = list(last_entry.values())[0].get('text', '')
            note_data = {
                'point': last_text,
                'solutions': ["Suggested solution 1", "Suggested solution 2"],
                'timestamp': time.time()
            }
            
            # Store in Firebase
            notes_ref = db.reference(f'discussions/{discussion_id}/notes').push()
            notes_ref.set(note_data)
            
            print(f"Emitting note: {last_text}")
            
            # Emit to clients
            socketio.emit('notes_update', note_data, room=discussion_id)
    except Exception as e:
        print(f"Notes error: {str(e)}")
        socketio.emit('error', {'message': str(e)}, room=discussion_id)

# =============================================
# Main Application
# =============================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    if not (0 < port < 65536):
        port = 8080
        
    socketio.run(app, 
                debug=True, 
                host='0.0.0.0', 
                port=port,
                allow_unsafe_werkzeug=True)