import os
import argparse
from gtts import gTTS
import time
import random

def generate_wav_with_gtts(text, output_path, lang='en'):
    """
    Generate a WAV file from text using Google Text-to-Speech
    Note: gTTS actually generates MP3, but we'll name it .wav since
    the app.py expects WAV format (Deepgram can usually handle this)
    """
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(output_path)
        print(f"Generated: {output_path}")
        return True
    except Exception as e:
        print(f"Error generating audio: {str(e)}")
        return False

def generate_normal_speech_samples(output_dir):
    """Generate sample files with normal speech content"""
    samples = [
        "This is a test of the audio transcription system.",
        "Welcome to the meeting. Today we'll discuss quarterly results.",
        "The annual revenue increased by fifteen percent compared to last year.",
        "We should consider expanding our operations to international markets.",
        "I think we need to invest more in research and development."
    ]
    
    for i, text in enumerate(samples):
        output_path = os.path.join(output_dir, f"normal_speech_{i+1}.wav")
        generate_wav_with_gtts(text, output_path)
        time.sleep(1)  # Avoid rate limiting

def generate_wake_word_samples(output_dir):
    """Generate sample files with wake word commands"""
    wake_commands = [
        "Aitool summarize the recent conversation.",
        "Harmon summarize what we just discussed.",
        "Aitool make a note of the key points.",
        "Harmon note the decision we just made.",
        "Aitool summarize the meeting highlights."
    ]
    
    for i, text in enumerate(wake_commands):
        output_path = os.path.join(output_dir, f"wake_command_{i+1}.wav")
        generate_wav_with_gtts(text, output_path)
        time.sleep(1)  # Avoid rate limiting

def generate_custom_files(texts, output_dir, prefix="custom"):
    """Generate audio files from custom text inputs"""
    for i, text in enumerate(texts):
        output_path = os.path.join(output_dir, f"{prefix}_{i+1}.wav")
        generate_wav_with_gtts(text, output_path)
        time.sleep(1)  # Avoid rate limiting

def generate_conversation_sample(output_dir):
    """Generate a mock conversation between multiple speakers"""
    conversation = [
        "Let's review the project timeline for the new product launch.",
        "I think we're on track with the development phase.",
        "Marketing needs more time to prepare the campaign materials.",
        "We should consider pushing the launch date by two weeks.",
        "I agree, that would give us enough buffer for unexpected issues.",
        "Aitool summarize our discussion about the project timeline."
    ]
    
    output_path = os.path.join(output_dir, "conversation_sample.wav")
    generate_wav_with_gtts(" ".join(conversation), output_path)

def ensure_directory(directory):
    """Create directory if it doesn't exist"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Created directory: {directory}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate WAV files for testing audio transcription")
    parser.add_argument("--output", "-o", default="./test_audio", 
                        help="Output directory for generated files")
    parser.add_argument("--custom", "-c", nargs="+", 
                        help="Generate custom audio with specified text")
    parser.add_argument("--all", "-a", action="store_true", 
                        help="Generate all sample types")
    parser.add_argument("--normal", "-n", action="store_true", 
                        help="Generate normal speech samples")
    parser.add_argument("--wake", "-w", action="store_true", 
                        help="Generate wake word command samples")
    parser.add_argument("--conversation", "-v", action="store_true", 
                        help="Generate conversation sample")
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    ensure_directory(args.output)
    
    # Check if we need to install dependencies
    try:
        import gtts
    except ImportError:
        print("Installing required dependencies...")
        os.system("pip install gtts")
        print("Dependencies installed.")
    
    # Generate requested audio files
    if args.all or args.normal:
        print("Generating normal speech samples...")
        generate_normal_speech_samples(args.output)
    
    if args.all or args.wake:
        print("Generating wake word command samples...")
        generate_wake_word_samples(args.output)
    
    if args.all or args.conversation:
        print("Generating conversation sample...")
        generate_conversation_sample(args.output)
    
    if args.custom:
        print("Generating custom audio samples...")
        generate_custom_files(args.custom, args.output)
    
    if not (args.all or args.normal or args.wake or args.conversation or args.custom):
        print("No generation options selected. Use --help to see available options.")
        print("Generating default test files...")
        
        # Generate a basic set of test files
        generate_wav_with_gtts("This is a simple test of the audio system.", 
                              os.path.join(args.output, "test_basic.wav"))
        
        generate_wav_with_gtts("Aitool summarize this meeting.", 
                              os.path.join(args.output, "test_wake.wav"))
    
    print("\nDone! Generated audio files in:", args.output)
    print("\nTest your files with:")
    print(f"python test_audio.py test {args.output}/test_basic.wav")
    print(f"python test_audio.py wake {args.output}/test_basic.wav {args.output}/test_wake.wav")