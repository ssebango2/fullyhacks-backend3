# tests/__init__.py
import pytest
from src import app as flask_app

# Fixture for Flask test client
@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

# Fixture for mock Deepgram client
@pytest.fixture
def mock_dg(monkeypatch):
    mock = Mock()
    monkeypatch.setattr('src.dg_client', mock)
    return mock