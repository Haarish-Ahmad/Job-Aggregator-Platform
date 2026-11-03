"""Auth dependencies shared by main.py and the feature routers."""
import hmac

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from models import Students


def get_current_user(request:Request,db:Session=Depends(get_db)):
    student_id=request.session.get('student_id')
    if not student_id:
        raise HTTPException(status_code=401,detail='Not Logged in')
    student=db.get(Students,student_id)
    if not student:
        request.session.clear()
        raise HTTPException(status_code=401, detail="User not found")
    return student


def require_admin(user:Students=Depends(get_current_user)):
    if user.role!="admin":
        raise HTTPException(status_code=403,detail="Method not allowed")
    return user


def ingest_auth(request:Request,x_ingest_token:str|None=Header(default=None),db:Session=Depends(get_db)):
    """Machine access for the scraper (X-Ingest-Token) or an admin session (as before)."""
    if x_ingest_token is not None:
        expected=get_settings().ingest_token
        # Constant-time compare; an unset INGEST_TOKEN never matches anything.
        if expected and hmac.compare_digest(x_ingest_token.encode(),expected.encode()):
            return "ingest-token"
        raise HTTPException(status_code=401,detail="Invalid ingest token")
    user=get_current_user(request,db)
    if user.role!="admin":
        raise HTTPException(status_code=403,detail="Method not allowed")
    return user
