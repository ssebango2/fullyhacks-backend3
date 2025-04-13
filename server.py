from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
import websocket
import threading
import json
import re
import os
import time
import numpy as np
from collections import deque
from textblob import TextBlob
from cerebras.cloud.sdk import Cerebras  # Import Cerebras SDK

# Initialize Flask app and SocketIO once
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ----------------- Configuration -----------------

# Deepgram API token
DEEPGRAM_API_KEY = '2c58905362fad7e1e6c13ba67357d31902a23409'

# Cerebras API Key (replace with your own)
CEREBRAS_API_KEY = "csk-49jf3vxhyjfhjyvj5n62nxdt6mhv48k2rrhh65ww5vc4nmtk"  # Replace with your actual key

# Initialize Cerebras client
cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# Default Cerebras model
DEFAULT_MODEL = "llama-4-scout-17b-16e-instruct"  # Replace with your preferred model

# WebSocket URL for Deepgram
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1"

# Wake word
WAKE_WORD = "harmon"

# ----------------- Data Structures -----------------

# Store WebSocket connections
client_connections = {}

# Store conversation history
conversation_histories = {}

# ----------------- Sentiment Analysis -----------------

def analyze_sentiment_textblob(text):
    """
    Analyze sentiment using TextBlob (simple but effective for basic use)
    Returns: 
        - polarity: float between -1 (negative) and 1 (positive)
        - subjectivity: float between 0 (objective) and 1 (subjective)
    """
    analysis = TextBlob(text)
    
    # Get the polarity score (-1 to 1)
    polarity = analysis.sentiment.polarity
    
    # Get the subjectivity score (0 to 1)
    subjectivity = analysis.sentiment.subjectivity
    
    # Classify sentiment category
    if polarity > 0.3:
        sentiment = "positive"
    elif polarity < -0.3:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    
    # Determine if intervention might be needed (high subjectivity + negative polarity)
    intervention_needed = subjectivity > 0.7 and polarity < -0.3
    
    return {
        "text": text,
        "polarity": polarity,
        "subjectivity": subjectivity,
        "sentiment": sentiment,
        "intervention_needed": intervention_needed
    }

# Process Deepgram transcription with sentiment
def process_transcription_with_sentiment(transcription):
    """Process Deepgram transcription and add sentiment analysis"""
    # Extract the text from Deepgram response
    if 'results' in transcription and 'channels' in transcription['results']:
        if transcription['results']['channels'][0]['alternatives'][0]['transcript']:
            text = transcription['results']['channels'][0]['alternatives'][0]['transcript']
            
            # Analyze sentiment
            sentiment_results = analyze_sentiment_textblob(text)
            
            # Add sentiment analysis to the transcription result
            transcription['sentiment'] = sentiment_results
            
    return transcription

# ----------------- Command Processing -----------------

class CommandProcessor:
    """
    Process commands after wake word "Harmon" is detected
    """
    def __init__(self):
        # Define command patterns
        self.command_patterns = {
            'summarize': r'(?:summarize|summary|recap)(.*)',
            'translate': r'(?:translate|say\s+in)(.*?)(to|into)\s+(\w+)(.*)',
            'advice': r'(?:give|provide|offer)?\s*(?:advice|suggestion|help|guidance)(.*)',
            'analyze': r'(?:analyze|check|evaluate)\s+(?:sentiment|tone|mood|emotion)(.*)',
            'start': r'(?:start|begin|record)\s+(?:session|recording|transcript)(.*)',
            'stop': r'(?:stop|end|finish|pause)\s+(?:session|recording|transcript)(.*)',
            'save': r'(?:save|store)\s+(?:this|current|session|recording|transcript)(.*)',
        }
        
    def process_command(self, text):
        """
        Process a command detected after wake word
        Returns: command_type, parameters, original_text
        """
        command_type = None
        parameters = {}
        
        # Find what type of command was issued
        for cmd_type, pattern in self.command_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                command_type = cmd_type
                
                # Extract parameters based on command type
                if cmd_type == 'translate':
                    parameters['content'] = match.group(1).strip()
                    parameters['target_language'] = match.group(3).strip()
                elif cmd_type in ['summarize', 'advice', 'analyze']:
                    # For commands that operate on the conversation
                    content = match.group(1).strip()
                    if content:
                        parameters['context'] = content
                    else:
                        parameters['context'] = 'current_conversation'
                
                break
        
        # If no command pattern is matched, treat it as a general question
        if not command_type and WAKE_WORD in text.lower():
            command_type = 'general_question'
            # Remove "Harmon" and clean up the text
            clean_text = re.sub(r'(?i)' + WAKE_WORD + r'\s*', '', text).strip()
            parameters['query'] = clean_text
            
        response = {
            'command_type': command_type,
            'parameters': parameters,
            'original_text': text
        }
        
        return response

# Integration with the wake word detection system
def handle_transcription(transcription_data):
    """
    Handles transcriptions from Deepgram and detects wake word + commands
    To be integrated with your WebSocket handler
    """
    # Parse the transcription data
    if isinstance(transcription_data, str):
        transcription = json.loads(transcription_data)
    else:
        transcription = transcription_data
    
    # Extract text from transcription
    text = ""
    if 'results' in transcription and 'channels' in transcription['results']:
        if transcription['results']['channels'][0]['alternatives'][0]['transcript']:
            text = transcription['results']['channels'][0]['alternatives'][0]['transcript'].lower()
    
    # Check for wake word
    if WAKE_WORD in text:
        # Process as command
        processor = CommandProcessor()
        command_result = processor.process_command(text)
        
        # Execute the command
        if command_result['command_type']:
            # Execute different actions based on command type
            return {
                'type': 'command',
                'command_data': command_result,
                'original_transcription': transcription
            }
    
    # If not a command or no wake word, just return the transcription
    return {
        'type': 'transcription',
        'transcription': transcription
    }

# ----------------- Cerebras AI Integration -----------------

class AIResponseGenerator:
    """
    Generate responses using Cerebras AI's SDK based on commands and conversation context
    """
    def __init__(self):
        self.model = DEFAULT_MODEL
    
    def generate_response(self, command_type, parameters, conversation_history=None):
        """
        Generate an appropriate response based on the command type and parameters
        """
        if not conversation_history:
            conversation_history = []
        
        prompt = self._build_prompt(command_type, parameters, conversation_history)
        
        try:
            # Call Cerebras API using the SDK
            messages = [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]}
            ]
            
            response = cerebras_client.chat.completions.create(
                messages=messages,
                model=self.model
            )
            
            # Extract the response text
            response_text = response.choices[0].message.content
            
            return {
                "success": True,
                "response": response_text,
                "command_type": command_type,
                "parameters": parameters
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command_type": command_type
            }
    
    def _build_prompt(self, command_type, parameters, conversation_history):
        """
        Build appropriate prompts based on the command type
        """
        system_prompt = "You are Harmon, an AI assistant designed to help mediate and improve conversations."
        user_prompt = ""
        
        # Format conversation history
        conversation_text = "\n".join([f"Person {i%2 + 1}: {msg}" for i, msg in enumerate(conversation_history)])
        
        if command_type == "summarize":
            system_prompt += " You provide concise, accurate summaries of conversations."
            user_prompt = f"Summarize the following conversation:\n\n{conversation_text}"
            
        elif command_type == "advice":
            system_prompt += " You provide thoughtful advice on how to improve communication and resolve conflicts."
            user_prompt = f"Based on this conversation, provide advice on how to improve communication:\n\n{conversation_text}"
            
        elif command_type == "analyze":
            system_prompt += " You analyze the sentiment and emotional tone of conversations to identify potential issues."
            user_prompt = f"Analyze the sentiment and emotional dynamics of this conversation:\n\n{conversation_text}"
            
        elif command_type == "general_question":
            system_prompt += " You answer questions helpfully and accurately."
            user_prompt = parameters.get("query", "")
            
        # Add more command types as needed
            
        return {
            "system": system_prompt,
            "user": user_prompt
        }

# Integration with the command processor
def process_and_respond(command_data, conversation_history=None):
    """
    Process a command and generate an AI response
    To be used after command detection
    """
    if not conversation_history:
        conversation_history = []
        
    command_type = command_data.get('command_type')
    parameters = command_data.get('parameters', {})
    
    if not command_type:
        return {
            "success": False,
            "error": "No command type specified"
        }
    
    generator = AIResponseGenerator()
    response = generator.generate_response(command_type, parameters, conversation_history)
    
    return response

# ----------------- Translation Service -----------------

class TranslationService:
    """
    Service to handle translation of text between languages
    """
    def __init__(self):
        # Common language codes lookup
        self.language_codes = {
            'english': 'en',
            'spanish': 'es',
            'french': 'fr',
            'german': 'de',
            'italian': 'it',
            'portuguese': 'pt',
            'russian': 'ru',
            'japanese': 'ja',
            'korean': 'ko',
            'chinese': 'zh-cn',
            'arabic': 'ar',
            'hindi': 'hi'
            # Add more as needed
        }
    
    def translate_text(self, text, target_language):
        """
        Translate text to the target language using Cerebras
        """
        # Convert language name to code if needed
        target_code = self._get_language_code(target_language)
        
        return translate_with_cerebras(text, target_language)
    
    def _get_language_code(self, language):
        """Convert language name to code if needed"""
        # If it's already a language code (2 chars), return as is
        if len(language) <= 3 and language.isalpha():
            return language.lower()
            
        # Check if we have this language in our lookup
        language = language.lower()
        if language in self.language_codes:
            return self.language_codes[language]
            
        # If we can't find it, return as is
        return language

# Cerebras translation helper
def translate_with_cerebras(text, target_language):
    """Use Cerebras to translate text"""
    system_prompt = f"You are a professional translator. Translate the following text to {target_language}. Provide only the translation, no explanations."
    
    try:
        # Create messages for translation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
        
        # Call Cerebras API
        response = cerebras_client.chat.completions.create(
            messages=messages,
            model=DEFAULT_MODEL,  # Using default model for translation
            temperature=0.3  # Lower temperature for more accurate translations
        )
        
        # Extract the translated text
        translated_text = response.choices[0].message.content
        
        return {
            'success': True,
            'original_text': text,
            'translated_text': translated_text,
            'target_language': target_language
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'original_text': text,
            'target_language': target_language
        }

# Handler for translation commands
def handle_translation_command(command_data):
    """Handle translation commands from the command processor"""
    parameters = command_data.get('parameters', {})
    content = parameters.get('content', '')
    target_language = parameters.get('target_language', '')
    
    if not content or not target_language:
        return {
            'success': False,
            'error': 'Missing content or target language'
        }
    
    translator = TranslationService()
    result = translator.translate_text(content, target_language)
    
    return result

# ----------------- Emotion Detection -----------------

class EmotionDetector:
    """
    Detect emotions and determine when interventions are needed
    """
    def __init__(self, window_size=5):
        # Configure thresholds for intervention
        self.negative_threshold = -0.4  # Polarity below this triggers concern
        self.intensity_threshold = 0.7  # Subjectivity/magnitude above this triggers concern
        self.escalation_threshold = -0.15  # Trend slope below this indicates escalation
        
        # Use a sliding window to track conversation trends
        self.window_size = window_size
        self.polarity_window = deque(maxlen=window_size)
        self.intensity_window = deque(maxlen=window_size)
        
        # Track intervention state
        self.intervention_active = False
        self.last_intervention_index = -10  # Avoid immediate repeated interventions
    
    def analyze_emotion(self, sentiment_data, conversation_index):
        """
        Analyze emotions and determine if intervention is needed
        """
        # Extract metrics from sentiment analysis
        polarity = sentiment_data.get('polarity', 0)
        
        # Handle different sentiment APIs (TextBlob vs Google)
        if 'subjectivity' in sentiment_data:
            intensity = sentiment_data['subjectivity']
        elif 'magnitude' in sentiment_data:
            intensity = sentiment_data['magnitude']
        else:
            intensity = 0.5  # Default value
        
        # Add to sliding windows
        self.polarity_window.append(polarity)
        self.intensity_window.append(intensity)
        
        # Calculate additional metrics
        avg_polarity = np.mean(self.polarity_window) if self.polarity_window else polarity
        avg_intensity = np.mean(self.intensity_window) if self.intensity_window else intensity
        
        # Determine trend (if we have enough data points)
        trend_slope = 0
        if len(self.polarity_window) >= 3:
            # Simple linear regression to determine trend
            x = np.arange(len(self.polarity_window))
            y = np.array(self.polarity_window)
            trend_slope = np.polyfit(x, y, 1)[0]  # Slope of the best-fit line
        
        # Determine emotion category
        emotion = self._categorize_emotion(polarity, intensity)
        
        # Check intervention criteria
        needs_intervention = self._check_intervention_needed(
            polarity, intensity, avg_polarity, avg_intensity, 
            trend_slope, conversation_index
        )
        
        # Create result
        result = {
            'emotion': emotion,
            'metrics': {
                'polarity': polarity,
                'intensity': intensity,
                'avg_polarity': avg_polarity,
                'avg_intensity': avg_intensity,
                'trend_slope': trend_slope
            },
            'needs_intervention': needs_intervention,
            'intervention_type': self._get_intervention_type(emotion, needs_intervention)
        }
        
        # Update intervention state
        if needs_intervention:
            self.intervention_active = True
            self.last_intervention_index = conversation_index
        
        return result
    
    def _categorize_emotion(self, polarity, intensity):
        """Categorize emotion based on polarity and intensity"""
        if polarity < -0.5 and intensity > 0.6:
            return "angry"
        elif polarity < -0.3 and intensity > 0.5:
            return "frustrated"
        elif polarity < -0.2:
            return "negative"
        elif polarity > 0.5 and intensity > 0.6:
            return "excited"
        elif polarity > 0.3:
            return "positive"
        else:
            return "neutral"
    
    def _check_intervention_needed(self, polarity, intensity, avg_polarity, 
                                  avg_intensity, trend_slope, conversation_index):
        """Determine if an intervention is needed based on emotion metrics"""
        # Avoid repeated interventions
        if conversation_index - self.last_intervention_index < 5:
            return False
            
        # Check various intervention criteria
        if polarity < self.negative_threshold and intensity > self.intensity_threshold:
            # Strong negative emotion
            return True
            
        if avg_polarity < self.negative_threshold and trend_slope < self.escalation_threshold:
            # Escalating negative trend
            return True
            
        if self.intervention_active and avg_polarity > 0.1:
            # Conversation has improved, deactivate intervention
            self.intervention_active = False
            
        return False
    
    def _get_intervention_type(self, emotion, needs_intervention):
        """Determine what type of intervention to suggest"""
        if not needs_intervention:
            return None
            
        if emotion == "angry":
            return "de-escalation"
        elif emotion == "frustrated":
            return "clarification"
        else:
            return "reflection"

class InterventionGenerator:
    """
    Generate appropriate interventions based on emotion analysis
    """
    def __init__(self):
        self.intervention_templates = {
            "de-escalation": [
                "I notice the conversation is becoming heated. Perhaps we could take a moment to pause and reflect.",
                "It seems emotions are running high. Would it help to take a step back and approach this differently?",
                "I'm sensing some tension. Let's try to focus on understanding each other's perspectives."
            ],
            "clarification": [
                "There might be a misunderstanding here. Could you clarify what you meant?",
                "It seems like there's some confusion. Can we take a moment to make sure we understand each other?",
                "I think we might be talking past each other. Let's try to clarify what we're each trying to say."
            ],
            "reflection": [
                "Let's take a moment to consider how we're feeling about this conversation.",
                "It might help to reflect on what we're each hoping to achieve in this discussion.",
                "Perhaps we could pause and think about what's most important here."
            ]
        }
    
    def generate_basic_intervention(self, intervention_type, emotion):
        """Generate a simple template-based intervention"""
        if intervention_type not in self.intervention_templates:
            return "Would you like to pause and reflect on this conversation?"
            
        templates = self.intervention_templates[intervention_type]
        return np.random.choice(templates)
    
    def generate_ai_intervention(self, intervention_type, conversation_history):
        """Generate an AI-powered intervention using Cerebras"""
        conversation_text = "\n".join([f"Person {i%2 + 1}: {msg}" for i, msg in enumerate(conversation_history)])
        
        prompts = {
            "de-escalation": "The following conversation is becoming heated. Generate a thoughtful intervention to de-escalate tensions:",
            "clarification": "The following conversation shows signs of misunderstanding. Generate an intervention to help clarify the communication:",
            "reflection": "The following conversation could benefit from reflection. Generate an intervention to help participants reflect on their communication:"
        }
        
        prompt = prompts.get(intervention_type, prompts["reflection"])
        
        try:
            # Create messages for the intervention generation
            messages = [
                {"role": "system", "content": "You are Harmon, a conversation assistant designed to improve communication."},
                {"role": "user", "content": f"{prompt}\n\n{conversation_text}"}
            ]
            
            # Call Cerebras API
            response = cerebras_client.chat.completions.create(
                messages=messages,
                model=DEFAULT_MODEL
            )
            
            # Extract the intervention text
            intervention_text = response.choices[0].message.content
            
            return intervention_text
            
        except Exception as e:
            # Fall back to template-based intervention if AI fails
            return self.generate_basic_intervention(intervention_type, "negative")

# Integrated function to process a message with full pipeline
def process_message_with_sentiment_and_intervention(message, conversation_history=None, conversation_index=0):
    """
    Process a message through the complete emotion analysis pipeline
    """
    if conversation_history is None:
        conversation_history = []
    
    # 1. Analyze sentiment
    sentiment_data = analyze_sentiment_textblob(message)
    
    # 2. Detect emotions and check if intervention needed
    detector = EmotionDetector()
    emotion_result = detector.analyze_emotion(sentiment_data, conversation_index)
    
    # 3. Generate intervention if needed
    if emotion_result['needs_intervention']:
        generator = InterventionGenerator()
        
        # Use AI-generated intervention if we have conversation history
        if conversation_history and len(conversation_history) > 1:
            intervention_text = generator.generate_ai_intervention(
                emotion_result['intervention_type'],
                conversation_history + [message]
            )
        else:
            intervention_text = generator.generate_basic_intervention(
                emotion_result['intervention_type'],
                emotion_result['emotion']
            )
            
        emotion_result['intervention_text'] = intervention_text
    
    # 4. Combine all results
    return {
        'message': message,
        'sentiment': sentiment_data,
        'emotion_analysis': emotion_result
    }

# ----------------- Deepgram WebSocket Connection -----------------

def connect_to_deepgram(client_sid):
    """Connect to Deepgram WebSocket and handle audio/transcription"""
    def on_message(ws, message):
        # Parse the message from Deepgram
        try:
            result = json.loads(message)
            
            # Check if we have transcription results
            if (result.get('results') and 
                result['results'].get('channels') and 
                result['results']['channels'][0].get('alternatives')):
                
                transcript = result['results']['channels'][0]['alternatives'][0].get('transcript', '').lower()
                
                # If transcript is not empty
                if transcript:
                    # Add to conversation history
                    if client_sid in conversation_histories:
                        conversation_histories[client_sid].append(transcript)
                    else:
                        conversation_histories[client_sid] = [transcript]
                    
                    # Get conversation index
                    conversation_index = len(conversation_histories[client_sid]) - 1
                    
                    # Analyze sentiment
                    sentiment_result = analyze_sentiment_textblob(transcript)
                    
                    # Check for emotion intervention
                    detector = EmotionDetector()
                    emotion_result = detector.analyze_emotion(sentiment_result, conversation_index)
                    
                    # Generate intervention if needed
                    if emotion_result['needs_intervention']:
                        generator = InterventionGenerator()
                        intervention_text = generator.generate_basic_intervention(
                            emotion_result['intervention_type'],
                            emotion_result['emotion']
                        )
                        
                        # Send intervention to client
                        socketio.emit('intervention', {
                            'text': intervention_text,
                            'type': emotion_result['intervention_type'],
                            'emotion': emotion_result['emotion']
                        }, room=client_sid)
                    
                    # Check for wake word
                    if WAKE_WORD in transcript:
                        # Process as command
                        processor = CommandProcessor()
                        command_result = processor.process_command(transcript)
                        
                        if command_result['command_type']:
                            # Handle different command types
                            if command_result['command_type'] == 'translate':
                                # Handle translation
                                params = command_result['parameters']
                                translation_result = translate_with_cerebras(
                                    params.get('content', ''), 
                                    params.get('target_language', 'spanish')
                                )
                                
                                socketio.emit('command_response', {
                                    'command_type': 'translate',
                                    'result': translation_result
                                }, room=client_sid)
                                
                            elif command_result['command_type'] in ['summarize', 'advice', 'analyze', 'general_question']:
                                # Generate AI response
                                ai_response = process_and_respond(
                                    command_result,
                                    conversation_histories.get(client_sid, [])
                                )
                                
                                socketio.emit('command_response', {
                                    'command_type': command_result['command_type'],
                                    'result': ai_response
                                }, room=client_sid)
                                
                            elif command_result['command_type'] == 'save':
                                # Save functionality would go here
                                # For now, just acknowledge the command
                                socketio.emit('command_response', {
                                    'command_type': 'save',
                                    'result': {'success': True, 'message': 'Session saved'}
                                }, room=client_sid)
            
            # Add sentiment analysis to the transcription result
            result['sentiment'] = sentiment_result if 'sentiment_result' in locals() else None
            
            # Send the complete transcription result to the client
            socketio.emit('transcription', json.dumps(result), room=client_sid)
            
        except Exception as e:
            print(f"Error processing message: {e}")
            socketio.emit('error', {'message': f"Error processing transcription: {str(e)}"}, room=client_sid)

    def on_error(ws, error):
        print(f"Deepgram WebSocket error for client {client_sid}: {error}")
        socketio.emit('error', {'message': f"Deepgram connection error: {str(error)}"}, room=client_sid)

    def on_close(ws, close_status_code, close_msg):
        print(f"Deepgram WebSocket closed for client {client_sid}")
        if client_sid in client_connections:
            del client_connections[client_sid]

    def on_open(ws):
        print(f"Deepgram WebSocket connected for client {client_sid}")
        client_connections[client_sid] = ws
        socketio.emit('status', {'message': 'Deepgram connected, ready for audio'}, room=client_sid)
        
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
    wst.daemon = True
    wst.start()

# ----------------- Flask Routes and SocketIO Events -----------------

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/analyze_sentiment', methods=['POST'])
def sentiment_endpoint():
    """API endpoint for sentiment analysis"""
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    result = analyze_sentiment_textblob(text)
    return jsonify(result)

@app.route('/api/process_command', methods=['POST'])
def process_command_endpoint():
    """API endpoint for command processing"""
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    processor = CommandProcessor()
    result = processor.process_command(text)
    
    return jsonify(result)

@app.route('/api/generate_response', methods=['POST'])
def generate_response_endpoint():
    """API endpoint for generating AI responses"""
    data = request.json
    command_type = data.get('command_type')
    parameters = data.get('parameters', {})
    conversation_history = data.get('conversation_history', [])
    
    if not command_type:
        return jsonify({'error': 'No command type provided'}), 400
    
    generator = AIResponseGenerator()
    result = generator.generate_response(command_type, parameters, conversation_history)
    
    return jsonify(result)

@app.route('/api/translate', methods=['POST'])
def translate_endpoint():
    """API endpoint for translation"""
    data = request.json
    text = data.get('text', '')
    target_language = data.get('target_language', 'en')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    result = translate_with_cerebras(text, target_language)
    return jsonify(result)

@app.route('/api/analyze_emotion', methods=['POST'])
def analyze_emotion_endpoint():
    """API endpoint for emotion analysis"""
    data = request.json
    sentiment_data = data.get('sentiment_data', {})
    conversation_index = data.get('conversation_index', 0)
    
    detector = EmotionDetector()
    result = detector.analyze_emotion(sentiment_data, conversation_index)
    
    # Generate intervention if needed
    if result['needs_intervention']:
        generator = InterventionGenerator()
        intervention_text = generator.generate_basic_intervention(
            result['intervention_type'], 
            result['emotion']
        )
        result['intervention_text'] = intervention_text
    
    return jsonify(result)

# ----------------- SocketIO Event Handlers -----------------

@socketio.on('connect')
def handle_connect():
    """Handle new client connection"""
    client_sid = request.sid
    print(f"Client connected: {client_sid}")
    
    # Start a new Deepgram connection for this client
    connect_to_deepgram(client_sid)
    
    # Initialize conversation history
    conversation_histories[client_sid] = []

@socketio.on('audio')
def handle_audio(audio_data):
    """Handle audio data from client and send to Deepgram"""
    client_sid = request.sid
    
    if client_sid in client_connections:
        try:
            # Send the received audio to Deepgram WebSocket
            client_connections[client_sid].send(audio_data, opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            print(f"Error sending audio to Deepgram: {e}")
            socketio.emit('error', {'message': f"Error sending audio: {str(e)}"}, room=client_sid)
    else:
        print(f"No Deepgram connection for client {client_sid}")
        socketio.emit('error', {'message': "Deepgram connection not established"}, room=client_sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    client_sid = request.sid
    print(f"Client disconnected: {client_sid}")
    
    # Close the Deepgram connection
    if client_sid in client_connections:
        try:
            client_connections[client_sid].close()
        except:
            pass
        del client_connections[client_sid]
    
    # Clean up conversation history
    if client_sid in conversation_histories:
        del conversation_histories[client_sid]

# ----------------- Main Entry Point -----------------

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Harmon server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)