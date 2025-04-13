import pytest
import firebase_admin
from firebase_admin import credentials, db
from uuid import uuid4

@pytest.fixture(scope="module")
def firebase_app():
    cred = credentials.Certificate('serviceAccountKey.json')
    app = firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://fullyhacks-1ebc3-default-rtdb.firebaseio.com'
    })
    yield app
    firebase_admin.delete_app(app)

def test_firebase_connection(firebase_app):
    """Test basic Firebase connection and operations"""
    test_path = f"test/{uuid4().hex}"
    ref = db.reference(test_path)
    
    # Test write
    test_data = {'message': 'Hello from HarmonAI!', 'timestamp': int(time.time())}
    ref.set(test_data)
    
    # Test read
    result = ref.get()
    assert result == test_data
    
    # Test cleanup
    db.reference(test_path).delete()
    assert db.reference(test_path).get() is None
