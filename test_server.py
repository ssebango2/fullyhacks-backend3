import pytest
import json
from server import app, analyze_sentiment_textblob, CommandProcessor

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_sentiment_analysis():
    # Test the sentiment analysis function directly
    result = analyze_sentiment_textblob("I am very happy today")
    assert result['sentiment'] == 'positive'
    assert result['polarity'] > 0
    
    result = analyze_sentiment_textblob("I am very sad today")
    assert result['sentiment'] == 'negative'
    assert result['polarity'] < 0

def test_command_processor():
    processor = CommandProcessor()
    
    # Test summarize command
    result = processor.process_command("harmon summarize this conversation")
    assert result['command_type'] == 'summarize'
    
    # Test translate command
    result = processor.process_command("harmon translate hello to spanish")
    assert result['command_type'] == 'translate'
    assert result['parameters']['content'] == 'hello'
    assert result['parameters']['target_language'] == 'spanish'

def test_sentiment_endpoint(client):
    response = client.post('/api/analyze_sentiment', 
                         json={'text': 'I am happy'})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['sentiment'] == 'positive'