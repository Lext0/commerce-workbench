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


def test_batch_partial_failure_retry_and_duplicate_protection(client):
    a = client.post('/api/products', json={'name':'甲', 'model':'A', 'price_cents':100}).json()
    b = client.post('/api/products', json={'name':'乙', 'model':'B', 'price_cents':200}).json()
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, 'PNG')
    payload = {'content': base64.b64encode(image.getvalue()).decode()}
    client.put(f"/api/products/{a['id']}/image", json=payload)
    for p in (a, b):
        client.post('/api/distribution/queue', json={'product_id':p['id']})
    result = client.post('/api/distribution/batches', json={'request_id':'test_batch_1234567890'}).json()
    assert [x['status'] for x in result['items']] == ['success', 'failed']
    assert client.get(f"/api/distribution/batches/{result['id']}").json() == result
    original = client.get(f"/api/products/{a['id']}/listing").json()
    client.put(f"/api/products/{b['id']}/image", json=payload)
    result = client.post(f"/api/distribution/batches/{result['id']}/retry", json={}).json()
    assert [x['status'] for x in result['items']] == ['success', 'success']
    assert client.get(f"/api/products/{a['id']}/listing").json() == original
    replay = client.post('/api/distribution/batches', json={'request_id':'test_batch_1234567890'}).json()
    assert replay['id'] == result['id']
    next_batch = client.post('/api/distribution/batches', json={'request_id':'test_batch_9876543210'}).json()
    assert [x['status'] for x in next_batch['items']] == ['skipped', 'skipped']


def test_quote_decimal_rounding_and_boundaries(client):
    data = {'cost':'70','shipping':'7','exchange':'7','fee':'5','profit':'20'}
    assert client.post('/api/distribution/quote', json=data).json() == {'usd':'14.67'}
    data['profit'] = '95'
    assert client.post('/api/distribution/quote', json=data).status_code == 422
    data['profit'] = 'NaN'
    assert client.post('/api/distribution/quote', json=data).status_code == 422
