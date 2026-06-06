import onnx
model = onnx.load(p)
sanitized = sanitize(model.metadata_props)
label = f"meta {sanitized}"
