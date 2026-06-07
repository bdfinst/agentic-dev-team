import json
def handle(raw):
    msg = json.loads(raw)
    schema.validate(msg)
    coll.find(msg)
