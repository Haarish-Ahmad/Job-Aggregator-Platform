import smtplib
from datetime import datetime
from email.message import EmailMessage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from matching import compute_matches, save_matches
from models import Match, Students
from config import get_settings

def send_email(recipient:str,body:str,subject:str):
    settings = get_settings()
    msg=EmailMessage()
    msg['From']=settings.mail_from
    msg['To']=recipient
    msg['Subject']=subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        if settings.smtp_starttls:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)

def run_alerts(db)->int:
    settings = get_settings()
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

        fresh={j.id:(j,s) for j,s in results if s is not None and s>=settings.alert_min_score}
        if not fresh:
            continue    
        rows=db.scalars(
            select(Match).where(Match.student_id==st.id,Match.notified_at.is_(None),Match.job_id.in_(list(fresh)))).all()
        rows=sorted(rows,key=lambda m:-m.score)[:max(0, settings.alert_max_jobs_per_email)]
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
