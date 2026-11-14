import functools
import os

import jwt
from flask import abort, request

SECRET = os.environ["JWT_SECRET"]


def require_token(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        try:
            jwt.decode(header.removeprefix("Bearer "), SECRET, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            abort(401)
        return view(*args, **kwargs)
    return wrapper
