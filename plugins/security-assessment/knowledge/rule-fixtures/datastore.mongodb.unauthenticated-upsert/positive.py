def save(request):
    coll.update_one(request.json, {"$set": {"x": 1}}, upsert=True)
