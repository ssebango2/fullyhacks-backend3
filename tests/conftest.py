import pytest
from src import app as flask_app
from unittest.mock import Mock

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()

@pytest.fixture
def mock_deepgram():
    mock = Mock()
    mock.transcribe.return_value = {"transcript": "test text"}
    return mock