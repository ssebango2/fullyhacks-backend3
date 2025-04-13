def test_home_route(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Welcome" in response.data

def test_transcribe_route(client, mock_deepgram):
    with patch('src.dg_client', mock_deepgram):
        response = client.post('/transcribe', data={'audio': 'test.wav'})
        assert response.json == {"transcript": "test text"}