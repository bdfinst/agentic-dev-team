# Operations

The scorer has no login of its own; callers authenticate at the API gateway,
which forwards only requests carrying a valid session. Rotate `MODEL_SHA256`
whenever a new model is deployed.
