def test_discount(client):
    assert client.post('/price', json={'total': 100, 'tier': 'gold'}).json()['total'] == 90
