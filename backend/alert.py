import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from matching import compute_matches, save_matches
from models import Match, Students
from config import ALERT_MIN_SCORE,ALERT_PER_EMAIL,SMTP_FROM,SMTP_HOST,SMTP_PORT

def send_email(recipient:str,body:str,subject:str):
    msg=EmailMessage()
    msg['From']=SMTP_FROM
    msg['To']=recipient
    msg['Subject']=subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST,int(SMTP_PORT),timeout=15) as s:
        if os.getenv("SMTP_STARTTLS","false").lower()=="true":
            s.starttls()
        smtp_user=os.getenv("SMTP_USER")
        if smtp_user:
            s.login(smtp_user,os.getenv("SMTP_PASSWORD",""))
        s.send_message(msg)

def run_alerts(db)->int:
    students=db.scalars(select(Students).where(Students.role=="student",Students.alerts_enabled.is_(True))).all()
    sent=0
    for st in students:
        email,name=st.email,st.name
        results=compute_matches(st,db)
        save_matches(st,results,db)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

        fresh={j.id:(j,s) for j,s in results if s is not None and s>=ALERT_MIN_SCORE}
        if not fresh:
            continue    
        rows=db.scalars(
            select(Match).where(Match.student_id==st.id,Match.notified_at.is_(None),Match.job_id.in_(list(fresh)))).all()
        rows=sorted(rows,key=lambda m:-m.score)[:max(0,int(ALERT_PER_EMAIL))]
        if not rows:
            continue    
        lines=[]  
        for m in rows:
            job,score=fresh[m.job_id]
            subj=f"{len(rows)} new job matches"
            lines.append(f"- {job.title} at {job.company.company_name} ({score:.0f}% match)\n"
                f"  {job.apply_url or 'no link'}")
        joined="\n".join(lines)
        body=f"Hello {name}, \n\n Here are some of the jobs found today as per your profile:\n \n {joined}"
        try:
            send_email(email,body,subj)
        except Exception as e:
            print(f"send failed for {email}: {e}")
            db.rollback()
            continue 
        now=datetime.now()
        for m in rows:
            m.notified_at=now
        db.commit()
        sent+=1
    return sent    
