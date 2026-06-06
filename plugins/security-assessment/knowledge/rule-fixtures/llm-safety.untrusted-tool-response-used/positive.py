result = tool_call.execute()
client.messages.create(model="m", messages=[system, result])
