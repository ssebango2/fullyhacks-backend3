from your_module import EmotionDetector

def test_emotion_detection():
    detector = EmotionDetector(window_size=3)
    
    # Test angry detection
    result = detector.analyze_emotion(
        {'polarity': -0.6, 'subjectivity': 0.8}, 
        conversation_index=0
    )
    assert result['emotion'] == 'angry'
    assert result['needs_intervention'] == True