def save(request):
    schema.validate(request.json)
    coll.update_one(request.json, {"$set": {"x": 1}}, upsert=True)
