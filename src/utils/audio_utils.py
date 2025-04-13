import base64
import io
from pydub import AudioSegment

def convert_audio_to_base64(audio_data, format='wav'):
    """Convert audio data to base64 string"""
    return base64.b64encode(audio_data).decode('utf-8')

def base64_to_audio(base64_str):
    """Convert base64 string to audio data"""
    audio_data = base64.b64decode(base64_str)
    return audio_data

def convert_sample_rate(audio_data, target_sample_rate=16000):
    """Convert audio to target sample rate"""
    audio = AudioSegment.from_file(io.BytesIO(audio_data))
    audio = audio.set_frame_rate(target_sample_rate)
    buffer = io.BytesIO()
    audio.export(buffer, format="wav")
    return buffer.getvalue()
