import base64
import io
from PIL import Image


def test_queue_copy_and_csv(client):
    p = client.post('/api/products', json={'name': '杯子', 'model': 'A'}).json()
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, 'PNG')
    client.put(f"/api/products/{p['id']}/image", json={'content': base64.b64encode(image.getvalue()).decode()})
    assert client.post('/api/distribution/queue', json={'product_id': p['id']}).status_code == 200
    assert client.post('/api/distribution/queue', json={'product_id': p['id']}).status_code == 200
    assert len(client.get('/api/distribution/queue').json()) == 1
    assert client.put(f"/api/distribution/queue/{p['id']}", json={'selected': False}).status_code == 200
    assert client.get('/api/distribution/queue').json()[0]['selected'] == 0
    copy = client.post(f"/api/distribution/copy/{p['id']}", json={'model': 'B'})
    assert copy.status_code == 200
    assert client.get(f"/api/products/{copy.json()['product_id']}/image").content == image.getvalue()
    assert client.post(f"/api/distribution/copy/{p['id']}", json={'model': 'Ａ'}).status_code == 409
    content = '商品名称,型号,分类,售价,商品说明\n盘子,C,日用,12.50,说明\n\n重复,C,日用,12,\n坏价格,D,,1.222,\n'
    rows = client.post('/api/distribution/import', json={'text': content}).json()['rows']
    assert [row['status'] for row in rows] == ['imported', 'error', 'error']
    assert client.get(f"/api/products/{rows[0]['product_id']}").json()['price_cents'] == 1250
    assert client.request('DELETE', f"/api/distribution/queue/{p['id']}", json={}).status_code == 200
    assert len(client.get('/api/distribution/queue').json()) == 2


def test_csv_malformed_is_rejected_before_writing(client):
    content = '商品名称,型号,分类,售价,商品说明\n杯,A,,1,\n杯,B,,2,"unterminated'
    assert client.post('/api/distribution/import', json={'text': content}).status_code == 422
    assert client.get('/api/products').json()['total'] == 0
