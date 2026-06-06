import json, re
names = model.feature_names_in_
sanitized = [sanitize(n) for n in names]
out = json.dumps({n: 0 for n in sanitized})
