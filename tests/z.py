from gtts import gTTS

# Install if needed: pip install gtts

# Create directory if it doesn't exist
import os
os.makedirs("~/test_audio_files", exist_ok=True)

# Normal speech without wake word
tts = gTTS("This is a test of the transcription system. We are discussing the implementation of our project.", lang='en')
tts.save("~/test_audio_files/normal_speech.mp3")

# Speech with summarize command
tts = gTTS("We need to implement the user interface and connect it to the backend. Harmon, summarize the last few points.", lang='en')
tts.save("~/test_audio_files/wake_word_summary.mp3")

# Speech with note command
tts = gTTS("The notification system should be completed by tomorrow morning. Harmon, record the last point into the notes.", lang='en')
tts.save("~/test_audio_files/wake_word_notes.mp3")