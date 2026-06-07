import onnx
model = onnx.load(p)
label = f"meta {model.metadata_props}"
