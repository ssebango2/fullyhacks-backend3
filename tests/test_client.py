import socketio
import time
import json
import base64
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create Socket.IO client
sio = socketio.Client()

# Global variables
discussion_id = None

@sio.event
def connect():
    print('Connected to server')

@sio.event
def disconnect():
    print('Disconnected from server')

@sio.event
def transcript_update(data):
    print("\n=== Transcript Update ===")
    if 'segments' in data:
        for segment in data['segments']:
            print(f"Speaker {segment['speaker']}: {segment['text']}")
    print("=========================\n")

@sio.event
def summary(data):
    print("\n=== Summary ===")
    print(data['summary'])
    print("===============\n")

@sio.event
def notes_update(data):
    print("\n=== Notes Update ===")
    print(f"Point: {data['point']}")
    print("Solutions:")
    for solution in data['solutions']:
        print(f"- {solution}")
    print("===================\n")

@sio.event
def error(data):
    print(f"\nERROR: {data['message']}\n")

def create_discussion(server_url):
    """Create a new discussion on the server"""
    import requests
    try:
        response = requests.post(
            f"{server_url}/api/discussions",
            json={"title": f"Test Discussion {time.time()}"}
        )
        return response.json()
    except Exception as e:
        print(f"Error creating discussion: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    server_url = "http://localhost:5000"
    
    # Create a new discussion
    print("Creating a new discussion...")
    response = create_discussion(server_url)
    
    if "error" in response:
        print("Error creating discussion, exiting.")
        exit(1)
    
    discussion_id = response.get("discussion_id")
    print(f"Discussion created with ID: {discussion_id}")
    
    # Connect to the Socket.IO server
    print("Connecting to Socket.IO server...")
    sio.connect(server_url)
    
    # Join the discussion room
    sio.emit('join_discussion', {'discussion_id': discussion_id})
    
    # Keep the client running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Client stopped by user")
        sio.disconnect()
