import base64
import io

from PIL import Image


def test_image_upload_read_replace_delete_and_validation(client):
    product = client.post('/api/products', json={'name': '杯子', 'model': 'C-1'}).json()
    path = f"/api/products/{product['id']}/image"
    assert client.get(path).status_code == 404
    buffer = io.BytesIO()
    Image.new('RGB', (3, 2), 'red').save(buffer, format='PNG')
    image = buffer.getvalue()
    assert client.put(path, json={'content': base64.b64encode(image).decode()}).status_code == 200
    response = client.get(path)
    assert response.content == image
    assert response.headers['content-type'] == 'image/png'
    assert client.put(path, json={'content': base64.b64encode(b'bad').decode()}).status_code == 422
    assert client.get(path).content == image
    assert client.request('DELETE', path, json={}).status_code == 200
    assert client.get(path).status_code == 404
    assert client.put('/api/products/99999/image', json={'content': base64.b64encode(image).decode()}).status_code == 404
