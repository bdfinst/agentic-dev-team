import json
def handle(raw):
    msg = json.loads(raw)
    coll.find(msg)
