result = tool_call.execute()
safe = validate_schema(result)
client.messages.create(model="m", messages=[system, safe])
