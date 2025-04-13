from flask import Flask, request, jsonify
from flask_socketio import SocketIO
import websocket
import threading
import json
# import os - not needed since we're hardcoding the API key

# Initialize Flask app and SocketIO
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # For development, adjust for production

# Deepgram API token
DEEPGRAM_API_KEY = '2c58905362fad7e1e6c13ba67357d31902a23409'

# WebSocket URL for Deepgram
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1"

# Store WebSocket connections
client_connections = {}

# Deepgram WebSocket Connection
def connect_to_deepgram(client_sid):
    def on_message(ws, message):
        # Forward Deepgram response to the client
        socketio.emit('transcription', message, room=client_sid)

    def on_error(ws, error):
        print(f"Deepgram WebSocket error for client {client_sid}: {error}")

    def on_close(ws, close_status_code, close_msg):
        print(f"Deepgram WebSocket closed for client {client_sid}")
        # Remove from connections dictionary when closed
        if client_sid in client_connections:
            del client_connections[client_sid]

    def on_open(ws):
        print(f"Deepgram WebSocket connected for client {client_sid}")
        # Store the connection when it's successfully opened
        client_connections[client_sid] = ws
        
    # Prepare WebSocket connection to Deepgram
    websocket.enableTrace(True)  # Set to False in production
    ws = websocket.WebSocketApp(
        DEEPGRAM_WS_URL,
        header={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.on_open = on_open
    
    # Run the WebSocket connection in a thread
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True  # Thread will exit when main thread exits
    wst.start()

# When a new WebSocket connection is made by the client
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")
    # Start a new thread for Deepgram WebSocket connection
    connect_to_deepgram(request.sid)

# Relay the audio from client to Deepgram WebSocket
@socketio.on('audio')
def handle_audio(audio_data):
    client_sid = request.sid
    print(f"Audio received from client {client_sid}")
    
    # Send the received audio to client's Deepgram WebSocket if it exists
    if client_sid in client_connections:
        try:
            client_connections[client_sid].send(audio_data, opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            print(f"Error sending audio to Deepgram: {e}")
    else:
        print(f"No Deepgram connection for client {client_sid}")

# Disconnect client
@socketio.on('disconnect')
def handle_disconnect():
    client_sid = request.sid
    print(f"Client disconnected: {client_sid}")
    
    # Close the Deepgram connection if it exists
    if client_sid in client_connections:
        try:
            client_connections[client_sid].close()
        except:
            pass
        del client_connections[client_sid]

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
