from fastapi import status


def format_response(code: status, data=[], message: str = ""):
    return {"status": {"code": code, "message": message}, "data": data}