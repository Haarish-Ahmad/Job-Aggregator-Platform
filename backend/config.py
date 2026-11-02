import os

COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true"
INGEST_TOKEN=os.getenv("INGEST_TOKEN","")
ADMIN_EMAIL=os.getenv("ADMIN_EMAIL","admin@placement.in")
ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD","SNUC@12345")
SMTP_HOST=os.getenv("SMTP_HOST","localhost")
SMTP_PORT=os.getenv("SMTP_PORT",int(1025))
SMTP_FROM=os.getenv("SMTP_FROM",ADMIN_EMAIL)
ALERT_MIN_SCORE=float(os.getenv("ALERT_MIN_SCORE","60"))
ALERT_PER_EMAIL=float(os.getenv("ALERT_PER_EMAIL","5"))
ALERT_LOCK_ID="434434"
SECRET_KEY=os.getenv("SECRET_KEY","dev-secret-change-me")
RESUME_DIR=os.getenv("RESUME_DIR", "resumes")
CORS_ORIGINS=[origin.strip() for origin in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",") if origin.strip()]