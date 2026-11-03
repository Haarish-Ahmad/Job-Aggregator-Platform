import os
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash
from db import engine
from models import Students
from config import get_settings

settings = get_settings()
email = settings.admin_email.strip().lower()
ADMIN_PASSWORD = settings.admin_password
password=ADMIN_PASSWORD
if len(password) < 8:
    raise SystemExit("ADMIN_PASSWORD must be at least 8 characters")

with Session(engine) as db:
    user = db.scalars(select(Students).where(Students.email == email)).first()
    if user:
        user.role = "admin"          
        print(f"promoted {email} to admin")
    else:
        db.add(Students(
            name=os.getenv("ADMIN_NAME", "Admin"),
            branch="N/A",            
            grad_year=2026,
            email=email,
            password_hash=generate_password_hash(password),
            role="admin",
        ))
        print(f"created admin {email}")
    db.commit()