def test_copy_draft_is_based_on_saved_facts_and_does_not_write(client):
    product = client.post('/api/products', json={'name': '杯子', 'model': 'A-1', 'category': '日用', 'description': '白色'}).json()
    path = f"/api/products/{product['id']}"
    draft = client.post(path + '/copy-draft', json={})
    assert draft.status_code == 200
    assert draft.json()['description'] == '杯子\n型号：A-1\n分类：日用\n\n白色'
    assert client.get(path).json() == product
    assert client.post('/api/products/99999/copy-draft', json={}).status_code == 404
