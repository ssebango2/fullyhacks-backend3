from your_module import analyze_sentiment_textblob

def test_sentiment_analysis():
    # Test positive sentiment
    positive = analyze_sentiment_textblob("I love this!")
    assert positive['sentiment'] == 'positive'
    assert positive['polarity'] > 0.3
    
    # Test negative sentiment
    negative = analyze_sentiment_textblob("I hate this!")
    assert negative['sentiment'] == 'negative'
    
    # Test intervention trigger
    intervention = analyze_sentiment_textblob("This is absolutely terrible and I'm furious")
    assert intervention['intervention_needed'] == True