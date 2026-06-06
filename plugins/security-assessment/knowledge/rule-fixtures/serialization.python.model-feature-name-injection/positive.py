import json
names = model.feature_names_in_
out = json.dumps({n: 0 for n in names})
