"""Application tracker: jobs a student saved, and where each application stands.

Every query is scoped to the logged-in student, so nobody can see or change another student's records.
A new application always starts as 'saved'. Only the student moves it on: nothing is inferred from
opening the apply link.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from db import get_db
from deps import get_current_user
from models import Application, Job, Students
from schemas import ApplicationCreate, ApplicationOut, ApplicationUpdate

router = APIRouter(prefix="/me/applications", tags=["applications"])


def _own(db: Session, user: Students, application_id: int) -> Application:
    application = db.scalars(
        select(Application).where(Application.id == application_id, Application.student_id == user.id)
    ).first()
    if not application:
        # Same answer for "doesn't exist" and "belongs to someone else".
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.get("", response_model=list[ApplicationOut])
def list_applications(user: Students = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Application)
        .where(Application.student_id == user.id)
        .options(joinedload(Application.job).joinedload(Job.company))
        .order_by(func.coalesce(Application.applied_on, Application.saved_on).desc(), Application.id.desc())
    ).all()


@router.post("", response_model=ApplicationOut, status_code=201)
def save_job(data: ApplicationCreate, user: Students = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Job, data.job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    exists = db.scalars(
        select(Application.id).where(Application.student_id == user.id, Application.job_id == data.job_id)
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="This job is already in your applications")
    application = Application(student_id=user.id, job_id=data.job_id, status="saved")
    db.add(application)
    try:
        db.commit()
    except IntegrityError:  # a second request for the same job won the race
        db.rollback()
        raise HTTPException(status_code=409, detail="This job is already in your applications") from None
    db.refresh(application)
    return application


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(application_id: int, data: ApplicationUpdate,
                       user: Students = Depends(get_current_user), db: Session = Depends(get_db)):
    application = _own(db, user, application_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("status") is None:
        changes.pop("status", None)  # the status can be changed, never cleared
    # First move past 'saved': suggest today as the application date; the student can edit it.
    if changes.get("status", "saved") != "saved" and application.applied_on is None and "applied_on" not in changes:
        changes["applied_on"] = date.today()
    for field, value in changes.items():
        setattr(application, field, value)
    db.commit()
    db.refresh(application)
    return application


@router.delete("/{application_id}", status_code=204)
def remove_application(application_id: int, user: Students = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, application_id))
    db.commit()
    return Response(status_code=204)
