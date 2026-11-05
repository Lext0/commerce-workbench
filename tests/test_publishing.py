import base64
import io
from PIL import Image


def test_publish_requires_price_and_image_and_withdraws(client):
    product = client.post('/api/products', json={'name': '杯子', 'model': 'P-1'}).json()
    path = f"/api/products/{product['id']}/listing"
    assert client.get(path).json()['status'] == 'unpublished'
    assert client.post(path, json={}).status_code == 422
    product = client.put(f"/api/products/{product['id']}", json={'name': '杯子', 'model': 'P-1', 'price_cents': 100, 'revision': product['revision']}).json()
    assert client.post(path, json={}).status_code == 422
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2)).save(buffer, 'PNG')
    image = base64.b64encode(buffer.getvalue()).decode()
    assert client.put(f"/api/products/{product['id']}/image", json={'content': image}).status_code == 200
    result = client.post(path, json={})
    assert result.status_code == 200
    assert result.json()['snapshot']['price_cents'] == 100
    assert client.get(path).json()['status'] == 'published'
    assert client.request('DELETE', path, json={}).json()['status'] == 'withdrawn'
    assert client.request('DELETE', path, json={}).json()['status'] == 'withdrawn'
    assert client.post(path, json={}).json()['status'] == 'published'
