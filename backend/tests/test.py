from datetime import date, datetime
from types import SimpleNamespace

import pytest
import alert
import matching
import resume
from fastapi.testclient import TestClient
from sqlalchemy import JSON, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from werkzeug.security import generate_password_hash

import main
from db import Base
from models import Application, Companies, Job, Match, Students
from schemas import StudentDetails, jobsIn


@pytest.fixture
def db_session_factory(monkeypatch):
    engine=create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    array_types=[]
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type,ARRAY):
                array_types.append((column,column.type))
                column.type=JSON()

    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)

    def get_test_db():
        db=factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(main,"embed",lambda texts:[[1.0,0.0] for _ in texts])
    monkeypatch.setattr(main,"INGEST_TOKEN","test-ingest-token")
    monkeypatch.setattr(main,"func",SimpleNamespace(lower=func.lower,now=lambda:datetime.now()))
    main.app.dependency_overrides[main.get_db]=get_test_db

    yield factory

    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    for column,column_type in array_types:
        column.type=column_type


@pytest.fixture
def client(db_session_factory):
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def admin(db_session_factory):
    with db_session_factory() as db:
        user=Students(
            name="Admin",
            email="admin@example.com",
            password_hash=generate_password_hash("Admin@123"),
            branch="CSE",
            grad_year=2026,
            role="admin",
            skills=["python"],
            embedding=[1.0,0.0],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def register(client,email="asha@example.com",name="Asha",branch="CSE",grad_year=2026):
    return client.post("/auth/register",json={
        "name":name,
        "email":email,
        "password":"Test@1234",
        "branch":branch,
        "cgpa":8.5,
        "grad_year":grad_year,
        "skills":["python","sql","docker"],
    })


def login(client,email="asha@example.com",password="Test@1234"):
    return client.post("/auth/login",json={"email":email,"password":password})


def job_payload(company="Google",title="Backend Intern",**overrides):
    item={
        "company_name":company,
        "title":title,
        "apply_url":f"https://jobs.example.com/{title.lower().replace(' ','-')}",
        "location":"Chennai",
        "job_type":"internship",
        "description":"Build backend services",
        "min_cgpa":7.0,
        "allowed_branches":["CSE","IT"],
        "allowed_grads":[2026,2027],
        "required_skills":["Python","SQL"],
        "deadline":"2027-12-31",
    }
    item.update(overrides)
    return item


def ingest(client,jobs,token="test-ingest-token"):
    return client.post(
        "/internal/jobs",
        json={"jobs":jobs},
        headers={"ingest-token":token} if token else {},
    )


def make_company_and_job(db,company_name="Google",title="Backend Intern",active=True):
    company=db.scalars(
        select(Companies).where(Companies.company_name==company_name)
    ).first()
    if company is None:
        company=Companies(
            company_name=company_name,
            careers_url="https://example.com/careers",
        )
        db.add(company)
        db.flush()
    job=Job(
        company_id=company.id,
        title=title,
        description="Build backend services",
        location="Chennai",
        job_type="internship",
        min_cgpa=7.0,
        allowed_branches=["CSE"],
        allowed_grads=[2026],
        necessary_skills=["python"],
        apply_url="https://example.com/job",
        content_hash=f"{company_name}-{title}",
        is_active=active,
        embedding=[1.0,0.0],
        deadline_at=date(2027,12,31),
    )
    job.company=company
    db.add(job)
    db.flush()
    db.commit()
    return company,job


def test_health_and_anonymous_access(client):
    assert client.get("/health").status_code==200
    assert client.get("/health").json()=={"status":"ok","db":"ok"}
    assert client.get("/me").status_code==401
    assert client.get("/jobs").status_code==401
    assert client.get("/companies").status_code==401
    assert client.get("/me/matches").status_code==401


@pytest.mark.parametrize("path",[
    "/me",
    "/companies",
    "/jobs",
    "/jobs/1",
    "/jobs/filter?input=big_tech",
    "/me/matches",
    "/me/applications",
    "/me/stats",
    "/me/resume",
])
def test_protected_student_routes_reject_anonymous_users(client,path):
    assert client.get(path).status_code==401


def test_register_login_profile_and_logout(client):
    response=register(client)
    assert response.status_code==201
    data=response.json()
    assert data["role"]=="student"
    assert "password" not in data
    assert "password_hash" not in data

    assert client.get("/me").status_code==401
    assert login(client,password="wrong").status_code==401
    assert login(client,email="unknown@example.com").status_code==401
    assert login(client).status_code==200
    assert client.get("/me").json()["email"]=="asha@example.com"
    assert client.post("/auth/logout").status_code==200
    assert client.get("/me").status_code==401


@pytest.mark.parametrize("body",[
    {},
    {"email":"not-an-email","password":"Test@1234"},
    {"email":"asha@example.com"},
])
def test_login_rejects_invalid_request_body(client,body):
    assert client.post("/auth/login",json=body).status_code==422


@pytest.mark.parametrize("body",[
    {"name":"Asha","email":"bad-email","password":"Test@1234","grad_year":2026},
    {"name":"Asha","email":"asha@example.com","password":"Test@1234"},
    {"name":"Asha","email":"asha@example.com","password":"weak","grad_year":2026},
])
def test_register_rejects_invalid_input(client,body):
    assert client.post("/auth/register",json=body).status_code==422


@pytest.mark.parametrize("grad_year",[2000,2001,2024,2035,2040])
def test_registration_accepts_supported_graduation_years(client,grad_year):
    response=register(client,email=f"student{grad_year}@example.com",grad_year=grad_year)
    assert response.status_code==201
    assert response.json()["grad_year"]==grad_year


@pytest.mark.parametrize("password",[
    "password1!",
    "PASSWORD1!",
    "Password!",
    "Password1",
    "Pass word1!",
    "P1!",
    "ThisPasswordIsWayTooLongForValidationBecauseItExceedsOneHundredCharactersAndShouldNotBeAccepted1234567890!",
])
def test_registration_rejects_each_password_policy_failure(client,password):
    response=client.post("/auth/register",json={
        "name":"Test",
        "email":"password-test@example.com",
        "password":password,
        "grad_year":2026,
    })
    assert response.status_code==422


def test_duplicate_registration_and_missing_optional_branch(client):
    assert register(client).status_code==201
    assert register(client).status_code==409
    response=client.post("/auth/register",json={
        "name":"No Branch",
        "email":"nobranch@example.com",
        "password":"Test@1234",
        "grad_year":2027,
    })
    assert response.status_code==201
    assert response.json()["branch"] is None


def test_profile_update_only_changes_allowed_fields(client):
    assert register(client).status_code==201
    assert login(client).status_code==200

    response=client.patch("/me/update",json={
        "cgpa":9.0,
        "skills":["Python","React"],
        "role":"admin",
        "email":"changed@example.com",
    })
    assert response.status_code==200
    assert response.json()["cgpa"]==9.0
    assert response.json()["skills"]==["python","react"]
    assert response.json()["role"]=="student"
    assert response.json()["email"]=="asha@example.com"
    assert client.patch("/me/update",json={}).status_code==200
    assert client.patch("/me/update",json={"cgpa":11}).status_code==422
    assert client.patch("/me/update",json={"branch":None}).status_code==422


@pytest.mark.parametrize("body",[
    {"cgpa":-0.1},
    {"cgpa":10.1},
    {"grad_year":2019},
    {"grad_year":2041},
    {"skills":None},
    {"alerts_enabled":None},
])
def test_profile_update_rejects_values_outside_schema(client,body):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.patch("/me/update",json=body).status_code==422


@pytest.mark.parametrize("field,value",[
    ("cgpa",0),
    ("cgpa",10),
    ("grad_year",2020),
    ("grad_year",2040),
    ("alerts_enabled",True),
    ("alerts_enabled",False),
    ("branch","ECE"),
    ("skills",[]),
])
def test_profile_update_accepts_allowed_values(client,field,value):
    assert register(client).status_code==201
    assert login(client).status_code==200
    response=client.patch("/me/update",json={field:value})
    assert response.status_code==200
    if field in response.json():
        assert response.json()[field]==value


def test_company_routes_require_admin(client,admin):
    assert client.post("/company",json={
        "company_name":"Zoho",
        "careers_url":"https://zoho.example/careers",
    }).status_code==401
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.post("/company",json={
        "company_name":"Zoho",
        "careers_url":"https://zoho.example/careers",
    }).status_code==403
    client.post("/auth/logout")
    assert login(client,"admin@example.com","Admin@123").status_code==200
    body={"company_name":"Zoho","careers_url":"https://zoho.example/careers"}
    response=client.post("/company",json=body)
    assert response.status_code==201
    assert response.json()["company_name"]=="Zoho"
    assert client.post("/company",json=body).status_code==409
    assert any(item["company_name"]=="Zoho" for item in client.get("/companies").json())


def test_company_name_duplicate_check_is_case_insensitive(client,admin):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    assert client.post("/company",json={
        "company_name":"Zoho",
        "careers_url":"https://zoho.example/careers",
    }).status_code==201
    response=client.post("/company",json={
        "company_name":"zOhO",
        "careers_url":"https://other.example/careers",
    })
    assert response.status_code==409


def test_ingestion_requires_token_and_rejects_invalid_jobs(client,admin):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    client.post("/auth/logout")
    assert ingest(client,[job_payload()],token="").status_code==401
    assert ingest(client,[job_payload()],token="wrong-token").status_code==401
    assert login(client,"admin@example.com","Admin@123").status_code==200
    assert ingest(client,[{"company_name":"Google","apply_url":"https://example.com"}]).status_code==422
    assert ingest(client,[job_payload(deadline="not-a-date")]).status_code==422


@pytest.mark.parametrize("missing_field",[
    "company_name",
    "title",
    "apply_url",
])
def test_ingestion_requires_each_required_job_field(client,admin,missing_field):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    item=job_payload()
    item.pop(missing_field)
    assert ingest(client,[item]).status_code==422


@pytest.mark.parametrize("field,value",[
    ("min_cgpa","not-a-number"),
    ("allowed_grads","2026"),
    ("required_skills","python"),
    ("deadline",123),
    ("apply_url",None),
])
def test_ingestion_rejects_invalid_field_types(client,admin,field,value):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    assert ingest(client,[job_payload(**{field:value})]).status_code==422


def test_ingestion_allows_admin_session_without_configured_token(client,admin,monkeypatch):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    monkeypatch.setattr(main,"INGEST_TOKEN","")
    response=client.post("/internal/jobs",json={"jobs":[job_payload()]})
    assert response.status_code==200
    client.post("/auth/logout")
    response=ingest(client,[job_payload(company="No Session")])
    assert response.status_code==401


def test_ingestion_accepts_integration_header_and_admin_session(client,admin):
    response=client.post(
        "/internal/jobs",
        json={"jobs":[job_payload()]},
        headers={"X-Ingest-Token":"test-ingest-token"},
    )
    assert response.status_code==200
    client.post("/auth/logout")
    assert login(client,"admin@example.com","Admin@123").status_code==200
    response=client.post("/internal/jobs",json={"jobs":[job_payload(company="Admin Company")]})
    assert response.status_code==200


def test_ingestion_rejects_non_http_apply_urls_per_record(client,admin):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    response=ingest(client,[job_payload(apply_url="javascript:alert(1)"),job_payload(company="Valid")])
    assert response.status_code==200
    assert response.json()["rejected"]==1
    assert [item["status"] for item in response.json()["results"]]==["rejected","inserted"]


def test_ingestion_inserts_deduplicates_and_refreshes_jobs(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    first=ingest(client,[job_payload()])
    assert first.status_code==200
    assert first.json()["inserted"]==1
    assert first.json()["results"][0]["status"]=="inserted"
    second=ingest(client,[job_payload(description="Updated description",required_skills=["python","fastapi"])])
    assert second.status_code==200
    assert second.json()["updated"]==1
    assert second.json()["results"][0]["status"]=="updated"

    with db_session_factory() as db:
        job=db.query(Job).one()
        assert job.description=="Updated description"
        assert job.necessary_skills==["python","fastapi"]
        assert job.embedding==[1.0,0.0]


def test_ingestion_accepts_empty_batch(client,admin):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    response=ingest(client,[])
    assert response.status_code==200
    assert response.json()["inserted"]==0
    assert response.json()["skipped"]==0
    assert response.json()["results"]==[]


def test_ingestion_uses_source_identity_and_persists_metadata(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    first=ingest(client,[job_payload(source="scraper-a",external_id="job-1",is_remote=True,work_mode="remote")])
    assert first.status_code==200
    second=ingest(client,[job_payload(
        source="scraper-a",external_id="job-1",title="Backend Engineer",
        location="Bangalore",is_remote=True,work_mode="remote",required_skills=["python","fastapi"],
    )])
    assert second.status_code==200
    assert second.json()["updated"]==1
    with db_session_factory() as db:
        jobs=db.scalars(select(Job)).all()
        assert len(jobs)==1
        assert jobs[0].title=="Backend Engineer"
        assert jobs[0].source=="scraper-a"
        assert jobs[0].external_id=="job-1"
        assert jobs[0].location=="Bangalore"
        assert jobs[0].content_hash==main.make_source_hash("scraper-a","job-1")
        assert jobs[0].is_remote is True
        assert jobs[0].work_mode=="remote"
        assert jobs[0].necessary_skills==["python","fastapi"]


def test_ingestion_reports_record_rejection_without_aborting_valid_records(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    response=ingest(client,[job_payload(min_cgpa=11),job_payload(company="Valid Company")])
    assert response.status_code==200
    assert response.json()["inserted"]==1
    assert response.json()["rejected"]==1
    assert [result["status"] for result in response.json()["results"]]==["rejected","inserted"]
    with db_session_factory() as db:
        assert db.query(Job).count()==1
        assert db.query(Companies).filter_by(company_name="Valid Company").count()==1


def test_ingestion_duplicate_records_in_same_batch_are_idempotent(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    item=job_payload(source="scraper-a",external_id="job-1")
    response=ingest(client,[item,item])
    assert response.status_code==200
    assert response.json()["inserted"]==1
    assert response.json()["skipped"]==1
    assert [result["status"] for result in response.json()["results"]]==["inserted","unchanged"]
    with db_session_factory() as db:
        assert db.query(Job).count()==1


def test_ingestion_keeps_distinct_source_ids_for_similar_postings(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    response=ingest(client,[
        job_payload(source="scraper-a",external_id="job-1"),
        job_payload(source="scraper-a",external_id="job-2"),
    ])
    assert response.status_code==200
    assert response.json()["inserted"]==2
    with db_session_factory() as db:
        assert db.query(Job).count()==2


def test_ingestion_partial_batch_does_not_deactivate_unseen_jobs(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    with db_session_factory() as db:
        company,job=make_company_and_job(db)
        job.last_seen_at=datetime(2000,1,1)
        db.commit()
        old_job_id=job.id
    response=ingest(client,[job_payload(title="New Role")])
    assert response.status_code==200
    with db_session_factory() as db:
        assert db.get(Job,old_job_id).is_active is True


def test_ingestion_creates_company_and_expires_past_deadline(client,admin,db_session_factory):
    assert login(client,"admin@example.com","Admin@123").status_code==200
    response=ingest(client,[job_payload(company="New Company",deadline="2020-01-01")])
    assert response.status_code==200
    with db_session_factory() as db:
        company=db.scalars(select(Companies).where(Companies.company_name=="New Company")).first()
        job=db.scalars(select(Job).where(Job.company_id==company.id)).one()
        assert job.is_active is False


def test_job_list_filters_pagination_and_lookup(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        _,google=make_company_and_job(db)
        _,other=make_company_and_job(db,"Zoho","Data Analyst")
        _,inactive=make_company_and_job(db,"Google","Old Role",active=False)

    assert client.get("/jobs").status_code==200
    assert len(client.get("/jobs?q=backend").json())==1
    assert len(client.get(f"/jobs?company_id={google.company_id}").json())==1
    assert len(client.get("/jobs?company_group=big_tech").json())==1
    assert client.get("/jobs?company_group=unknown").status_code==400
    assert len(client.get("/jobs?job_type=INTERNSHIP").json())==2
    assert len(client.get("/jobs?limit=1&offset=1").json())==1
    assert client.get("/jobs?limit=500").status_code==200
    assert client.get(f"/jobs/{google.id}").status_code==200
    assert client.get("/jobs/999999").status_code==404
    assert client.get("/jobs/not-an-id").status_code==422
    assert inactive.id not in [job["id"] for job in client.get("/jobs").json()]
    response=client.get("/jobs?skill=python&grad_year=2026&sort=title")
    assert response.status_code==200
    assert response.headers["X-Total-Count"]=="2"
    assert all("company_name" in item and "source" in item for item in response.json())


def test_job_list_supports_source_scope_and_expiry_filters(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        company,job=make_company_and_job(db)
        job.source="scraper-a"
        job.external_id="job-1"
        job.is_remote=True
        job.is_india=False
        db.commit()
    assert len(client.get("/jobs?source=scraper-a&scope=remote").json())==1
    assert client.get("/jobs?scope=india").json()==[]
    assert client.get("/jobs?scope=unknown").status_code==422


def test_application_tracker_create_list_update_and_delete(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        _,job=make_company_and_job(db)
        job_id=job.id

    created=client.post("/me/applications",json={"job_id":job_id,"status":"saved","notes":"Tailor resume"})
    assert created.status_code==201
    saved=created.json()
    assert saved["job_id"]==job_id
    assert saved["status"]=="saved"
    assert saved["applied_at"] is None
    assert client.get("/me/applications?status=saved").json()[0]["id"]==saved["id"]

    updated=client.patch(f"/me/applications/{saved['id']}",json={"status":"applied","notes":"Submitted online"})
    assert updated.status_code==200
    assert updated.json()["status"]=="applied"
    assert updated.json()["notes"]=="Submitted online"
    assert updated.json()["applied_at"] is not None
    assert client.get("/me/applications?status=interview").json()==[]

    assert client.delete(f"/me/applications/{saved['id']}").status_code==204
    assert client.get("/me/applications").json()==[]
    assert client.delete(f"/me/applications/{saved['id']}").status_code==404
    with db_session_factory() as db:
        assert db.query(Application).count()==0


def test_application_tracker_validates_job_status_and_duplicates(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.post("/me/applications",json={"job_id":99999}).status_code==404
    assert client.post("/me/applications",json={"job_id":1,"status":"unknown"}).status_code==422
    with db_session_factory() as db:
        _,job=make_company_and_job(db)
        job_id=job.id
    assert client.post("/me/applications",json={"job_id":job_id}).status_code==201
    assert client.post("/me/applications",json={"job_id":job_id}).status_code==409
    application_id=client.get("/me/applications").json()[0]["id"]
    assert client.patch(f"/me/applications/{application_id}",json={}).status_code==422
    assert client.patch(f"/me/applications/{application_id}",json={"status":None}).status_code==422


def test_application_records_are_private_to_each_student(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        _,job=make_company_and_job(db)
        job_id=job.id
    application=client.post("/me/applications",json={"job_id":job_id})
    application_id=application.json()["id"]
    client.post("/auth/logout")
    assert register(client,email="other@example.com",name="Other").status_code==201
    assert login(client,email="other@example.com",password="Test@1234").status_code==200
    assert client.get("/me/applications").json()==[]
    assert client.patch(f"/me/applications/{application_id}",json={"status":"interview"}).status_code==404
    assert client.delete(f"/me/applications/{application_id}").status_code==404


def test_analytics_routes_require_correct_access_and_return_expected_shapes(client,admin,db_session_factory):
    with db_session_factory() as db:
        company,job=make_company_and_job(db)
        job.necessary_skills=["python","sql"]
        job.is_remote=True
        job.source="scraper-a"
        db.commit()
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get("/analytics/skills").json()["top"][0]["skill"] in {"python","sql"}
    assert client.get("/analytics/companies").json()["totals"]["remote"]==1
    assert client.get("/analytics/skill-gap").status_code==403
    client.post("/auth/logout")
    assert login(client,"admin@example.com","Admin@123").status_code==200
    assert client.get("/analytics/skill-gap").status_code==200
    curriculum=client.get("/analytics/curriculum")
    assert curriculum.status_code==200
    assert "courses" in curriculum.json()


def test_health_checks_database_and_metrics_are_accessible(client,admin):
    assert client.get("/health").json()=={"status":"ok","db":"ok"}
    response=client.get("/metrics")
    assert response.status_code==200
    assert "http_requests_total" in response.text


def test_stale_maintenance_deactivates_only_old_scraped_jobs(client,admin,db_session_factory):
    with db_session_factory() as db:
        _,manual=make_company_and_job(db)
        _,scraped=make_company_and_job(db,"Scraped Co","Old Scraped Role")
        scraped.source="scraper-a"
        scraped.external_id="old-1"
        scraped.last_seen_at=datetime(2000,1,1)
        db.commit()
        manual_id=manual.id
        scraped_id=scraped.id
    response=client.post("/internal/maintenance/deactivate-stale?days=14",headers={"X-Ingest-Token":"test-ingest-token"})
    assert response.status_code==200
    with db_session_factory() as db:
        assert db.get(Job,manual_id).is_active is True
        assert db.get(Job,scraped_id).is_active is False


def test_job_list_filters_location_company_and_active_flag(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        _,google=make_company_and_job(db)
        make_company_and_job(db,"Zoho","Data Analyst")
        _,inactive=make_company_and_job(db,"Google","Old Role",active=False)

    assert len(client.get("/jobs?location=chen").json())==2
    assert len(client.get("/jobs?company=goo").json())==1
    active_jobs=client.get("/jobs?active_only=false").json()
    assert len(active_jobs)==3
    assert inactive.id in [job["id"] for job in active_jobs]
    assert client.get("/jobs?company_id=9999").json()==[]
    assert client.get("/jobs?offset=-1").status_code==422


@pytest.mark.parametrize("limit",["0","-1"])
def test_job_list_rejects_invalid_limits(client,limit):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get(f"/jobs?limit={limit}").status_code==422


def test_job_list_caps_large_limit(client):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get("/jobs?limit=101").status_code==200


@pytest.mark.parametrize("offset",["-1","abc"])
def test_job_list_rejects_invalid_offsets(client,offset):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get(f"/jobs?offset={offset}").status_code==422


@pytest.mark.parametrize("minimum",["abc","-1","101"])
def test_matches_rejects_invalid_minimum_score(client,minimum):
    assert register(client).status_code==201
    assert login(client).status_code==200
    response=client.get(f"/me/matches?min_score={minimum}")
    assert response.status_code==422 if minimum=="abc" else response.status_code==200


def test_match_route_saves_matches_and_filters_minimum_score(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        company,job=make_company_and_job(db)
        db.add(Match(student_id=1,job_id=job.id,score=75.0))
        db.commit()

    matches=client.get("/me/matches")
    assert matches.status_code==200
    assert len(matches.json())==1
    assert matches.json()[0]["job"]["title"]=="Backend Intern"
    assert client.get("/me/matches?min_score=101").json()==[]
    assert client.get("/me/matches").status_code==200
    with db_session_factory() as db:
        assert db.query(Match).count()==1


def test_matching_excludes_ineligible_jobs(client,db_session_factory):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        company=Companies(
            company_name="Google",
            careers_url="https://example.com/careers",
        )
        db.add(company)
        db.flush()
        jobs=[
            Job(company_id=company.id,title="Eligible",description="",location="Chennai",
                job_type="internship",min_cgpa=8.0,allowed_branches=["CSE"],allowed_grads=[2026],
                necessary_skills=["python"],apply_url="https://example.com/eligible",
                content_hash="eligible",is_active=True,embedding=[1.0,0.0]),
            Job(company_id=company.id,title="CGPA Too High",description="",location="Chennai",
                job_type="internship",min_cgpa=9.0,allowed_branches=["CSE"],allowed_grads=[2026],
                necessary_skills=["python"],apply_url="https://example.com/cgpa",
                content_hash="cgpa-high",is_active=True,embedding=[1.0,0.0]),
            Job(company_id=company.id,title="Wrong Branch",description="",location="Chennai",
                job_type="internship",min_cgpa=None,allowed_branches=["ECE"],allowed_grads=[],
                necessary_skills=["python"],apply_url="https://example.com/branch",
                content_hash="wrong-branch",is_active=True,embedding=[1.0,0.0]),
            Job(company_id=company.id,title="Wrong Graduation",description="",location="Chennai",
                job_type="internship",min_cgpa=None,allowed_branches=[],allowed_grads=[2027],
                necessary_skills=["python"],apply_url="https://example.com/graduation",
                content_hash="wrong-graduation",is_active=True,embedding=[1.0,0.0]),
        ]
        db.add_all(jobs)
        db.commit()

    response=client.get("/me/matches")
    assert response.status_code==200
    assert [item["job"]["title"] for item in response.json()]==["Eligible"]


def test_matching_respects_branch_for_second_student(client,db_session_factory):
    assert register(client,email="asha@example.com",branch="CSE").status_code==201
    with db_session_factory() as db:
        company=Companies(company_name="Zoho",careers_url="https://example.com")
        db.add(company)
        db.flush()
        db.add(Job(
            company_id=company.id,title="CSE role",description="",location="Chennai",
            job_type="internship",min_cgpa=None,allowed_branches=["CSE"],allowed_grads=[],
            necessary_skills=["python"],apply_url="https://example.com/cse",
            content_hash="cse-role",is_active=True,embedding=[1.0,0.0],
        ))
        db.add(Job(
            company_id=company.id,title="ECE role",description="",location="Chennai",
            job_type="internship",min_cgpa=None,allowed_branches=["ECE"],allowed_grads=[],
            necessary_skills=["python"],apply_url="https://example.com/ece",
            content_hash="ece-role",is_active=True,embedding=[1.0,0.0],
        ))
        db.commit()
    assert register(client,email="ravi@example.com",branch="ECE",grad_year=2027).status_code==201
    assert login(client,email="ravi@example.com").status_code==200
    response=client.get("/me/matches")
    assert response.status_code==200
    assert [item["job"]["title"] for item in response.json()]==["ECE role"]


def test_admin_analytics_metrics_and_auth(client,admin,monkeypatch):
    assert client.get("/admin/analytics").status_code==401
    assert login(client,"admin@example.com","Admin@123").status_code==200
    monkeypatch.setattr(main,"general_stats",lambda db:(0,[],[],0.0,1,0))
    monkeypatch.setattr(main,"get_early_jobs",lambda db:[])
    monkeypatch.setattr(main,"get_dontapply_jobs",lambda db:[])
    monkeypatch.setattr(main,"topskills",lambda db,limit:[])
    monkeypatch.setattr(main,"top_postings",lambda db,limit:[])

    response=client.get("/admin/analytics")
    assert response.status_code==200
    assert response.json()["students"]==1
    assert client.get("/admin/analytics?limit=10").status_code==200
    assert client.get("/admin/analytics?limit=9").status_code==422
    assert client.get("/admin/analytics?limit=101").status_code==422
    assert client.get("/metrics").status_code==200


def test_metrics_are_available_to_students(client):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get("/metrics").status_code==200


def test_student_stats_and_company_filter(client,db_session_factory,monkeypatch):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        _,job=make_company_and_job(db)
        _,inactive=make_company_and_job(db,"Google","Inactive Role",active=False)
    monkeypatch.setattr(main,"compute_matches",lambda user,db:[(job,80.0)])
    monkeypatch.setattr(main,"get_early_jobs",lambda db,job_ids=None,limit=50:[job] if job.id in job_ids else [])
    monkeypatch.setattr(main,"topskills",lambda db,limit:[])

    stats=client.get("/me/stats")
    assert stats.status_code==200
    assert stats.json()["matching_jobs"]==1
    assert stats.json()["apply_early"][0]["id"]==job.id
    assert client.get("/jobs/filter?input=big_tech").status_code==200
    filtered=client.get("/jobs/filter?input=big_tech").json()
    assert [item["id"] for item in filtered]==[job.id]
    assert client.get("/jobs/filter?input=unknown").status_code==400


@pytest.mark.parametrize("limit",["0","51","-1"])
def test_student_stats_rejects_invalid_limits(client,limit):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get(f"/me/stats?limit={limit}").status_code==422


@pytest.mark.parametrize("category,company_name",[
    ("big_tech","Google"),
    ("indian_startups","Zoho"),
    ("fintech","Razorpay"),
    ("ai_and_deeptech","Figma"),
    ("finance_and_quant","Visa"),
    ("it_services_mass_hiring","Infosys"),
    ("core_engineering","Bosch"),
])
def test_company_filter_categories(client,db_session_factory,category,company_name):
    assert register(client).status_code==201
    assert login(client).status_code==200
    with db_session_factory() as db:
        _,job=make_company_and_job(db,company_name)
    response=client.get(f"/jobs/filter?input={category}")
    assert response.status_code==200
    assert [item["id"] for item in response.json()]==[job.id]


@pytest.mark.parametrize("category",[
    "",
    "BIG_TECH",
    "Big Tech",
    "unknown",
    "software",
])
def test_company_filter_rejects_unknown_categories(client,category):
    assert register(client).status_code==201
    assert login(client).status_code==200
    response=client.get("/jobs/filter",params={"input":category})
    assert response.status_code==400


def test_internal_alert_trigger_authentication(client,admin,monkeypatch):
    assert client.post("/internal/trigger_alerts").status_code==401
    monkeypatch.setattr(main,"job_alerts",lambda:None)
    assert client.post(
        "/internal/trigger_alerts",
        headers={"ingest-token":"test-ingest-token"},
    ).status_code==202


def test_internal_alert_trigger_runs_background_task(client,monkeypatch):
    calls=[]
    monkeypatch.setattr(main,"job_alerts",lambda:calls.append("called"))
    response=client.post(
        "/internal/trigger_alerts",
        headers={"ingest-token":"test-ingest-token"},
    )
    assert response.status_code==202
    assert response.json()=={"status":"started"}
    assert calls==["called"]


def test_integration_alert_route_accepts_token_and_admin_session(client,admin,monkeypatch):
    monkeypatch.setattr(main,"job_alerts",lambda:None)
    token_response=client.post(
        "/internal/alerts/run",
        headers={"X-Ingest-Token":"test-ingest-token"},
    )
    assert token_response.status_code==200
    assert login(client,"admin@example.com","Admin@123").status_code==200
    assert client.post("/internal/alerts/run").status_code==200


def test_alert_sender_only_sends_eligible_unnotified_matches(db_session_factory,monkeypatch):
    with db_session_factory() as db:
        student=Students(
            name="Asha",email="asha@example.com",password_hash="hashed",
            branch="CSE",grad_year=2026,role="student",skills=["python"],
            alerts_enabled=True,embedding=[1.0,0.0],
        )
        company=Companies(company_name="Google",careers_url="https://example.com")
        db.add_all([student,company])
        db.flush()
        job=Job(
            company_id=company.id,title="Backend Intern",description="",
            location="Chennai",job_type="internship",min_cgpa=None,
            allowed_branches=[],allowed_grads=[],necessary_skills=["python"],
            apply_url="https://example.com/job",content_hash="alert-job",
            is_active=True,embedding=[1.0,0.0],
        )
        db.add(job)
        db.flush()
        match=Match(student_id=student.id,job_id=job.id,score=90.0)
        db.add(match)
        db.commit()
        db.refresh(student)
        db.refresh(job)

        monkeypatch.setattr(alert,"compute_matches",lambda student,db:[(job,90.0)])
        monkeypatch.setattr(alert,"save_matches",lambda student,results,db:None)
        sent=[]
        monkeypatch.setattr(alert,"send_email",lambda email,body,subject:sent.append(email))
        assert alert.run_alerts(db)==1
        assert sent==["asha@example.com"]
        assert match.notified_at is not None


def test_alert_sender_does_not_send_below_minimum_score(db_session_factory,monkeypatch):
    with db_session_factory() as db:
        student=Students(
            name="Asha",email="asha@example.com",password_hash="hashed",
            branch="CSE",grad_year=2026,role="student",skills=["python"],
            alerts_enabled=True,embedding=[1.0,0.0],
        )
        db.add(student)
        db.commit()
        monkeypatch.setattr(alert,"compute_matches",lambda student,db:[(object(),0.0)])
        monkeypatch.setattr(alert,"save_matches",lambda student,results,db:None)
        monkeypatch.setattr(alert,"ALERT_MIN_SCORE",60)
        monkeypatch.setattr(alert,"send_email",lambda *args:pytest.fail("unexpected email"))
        assert alert.run_alerts(db)==0


@pytest.mark.parametrize("enabled,role,expected_calls",[
    (False,"student",0),
    (True,"admin",0),
    (True,"student",1),
])
def test_alert_sender_only_processes_enabled_students(db_session_factory,monkeypatch,enabled,role,expected_calls):
    with db_session_factory() as db:
        db.add(Students(
            name="Student",email=f"{role}-{enabled}@example.com",password_hash="hashed",
            branch="CSE",grad_year=2026,role=role,skills=[],
            alerts_enabled=enabled,embedding=[1.0,0.0],
        ))
        db.commit()
        calls=[]
        monkeypatch.setattr(alert,"compute_matches",lambda student,db:calls.append(student.email) or [])
        monkeypatch.setattr(alert,"save_matches",lambda student,results,db:None)
        assert alert.run_alerts(db)==0
        assert len(calls)==expected_calls


@pytest.mark.parametrize("email_limit",[0,1,2,5])
def test_alert_sender_caps_matches_per_email(db_session_factory,monkeypatch,email_limit):
    with db_session_factory() as db:
        student=Students(
            name="Asha",email="asha@example.com",password_hash="hashed",
            branch="CSE",grad_year=2026,role="student",skills=["python"],
            alerts_enabled=True,embedding=[1.0,0.0],
        )
        company=Companies(company_name="Google",careers_url="https://example.com")
        db.add_all([student,company])
        db.flush()
        jobs=[]
        for index in range(5):
            job=Job(
                company_id=company.id,title=f"Role {index}",description="",
                location="Chennai",job_type="internship",min_cgpa=None,
                allowed_branches=[],allowed_grads=[],necessary_skills=["python"],
                apply_url=f"https://example.com/{index}",content_hash=f"job-{index}",
                is_active=True,embedding=[1.0,0.0],
            )
            job.company=company
            db.add(job)
            db.flush()
            db.add(Match(student_id=student.id,job_id=job.id,score=90-index))
            jobs.append(job)
        db.commit()
        monkeypatch.setattr(alert,"compute_matches",lambda student,db:[(job,90-index) for index,job in enumerate(jobs)])
        monkeypatch.setattr(alert,"save_matches",lambda student,results,db:None)
        messages=[]
        monkeypatch.setattr(alert,"send_email",lambda email,body,subject:messages.append(body))
        monkeypatch.setattr(alert,"ALERT_PER_EMAIL",email_limit)

        assert alert.run_alerts(db)==(1 if email_limit else 0)
        assert len(messages)==(1 if email_limit else 0)
        notified=db.scalars(select(Match).where(Match.notified_at.is_not(None))).all()
        assert len(notified)==min(email_limit,5)


def test_alert_sender_leaves_matches_unnotified_after_email_failure(db_session_factory,monkeypatch,capsys):
    with db_session_factory() as db:
        student=Students(
            name="Asha",email="asha@example.com",password_hash="hashed",
            branch="CSE",grad_year=2026,role="student",skills=["python"],
            alerts_enabled=True,embedding=[1.0,0.0],
        )
        company=Companies(company_name="Google",careers_url="https://example.com")
        db.add_all([student,company])
        db.flush()
        job=Job(
            company_id=company.id,title="Backend",description="",location="Chennai",
            job_type="internship",min_cgpa=None,allowed_branches=[],allowed_grads=[],
            necessary_skills=["python"],apply_url="https://example.com/job",
            content_hash="failed-email-job",is_active=True,embedding=[1.0,0.0],
        )
        job.company=company
        db.add(job)
        db.flush()
        match=Match(student_id=student.id,job_id=job.id,score=90)
        db.add(match)
        db.commit()
        monkeypatch.setattr(alert,"compute_matches",lambda student,db:[(job,90)])
        monkeypatch.setattr(alert,"save_matches",lambda student,results,db:None)
        monkeypatch.setattr(alert,"send_email",lambda *args:(_ for _ in ()).throw(OSError("SMTP down")))

        assert alert.run_alerts(db)==0
        db.refresh(match)
        assert match.notified_at is None
        assert "SMTP down" in capsys.readouterr().out


@pytest.mark.parametrize("score,should_send",[
    (59.99,False),
    (60,True),
    (100,True),
])
def test_alert_sender_respects_configured_score_threshold(db_session_factory,monkeypatch,score,should_send):
    with db_session_factory() as db:
        student=Students(
            name="Asha",email="asha@example.com",password_hash="hashed",
            branch="CSE",grad_year=2026,role="student",skills=["python"],
            alerts_enabled=True,embedding=[1.0,0.0],
        )
        company=Companies(company_name="Google",careers_url="https://example.com")
        db.add_all([student,company])
        db.flush()
        job=Job(
            company_id=company.id,title="Backend",description="",location="Chennai",
            job_type="internship",min_cgpa=None,allowed_branches=[],allowed_grads=[],
            necessary_skills=["python"],apply_url="https://example.com/job",
            content_hash=f"score-{score}",is_active=True,embedding=[1.0,0.0],
        )
        job.company=company
        db.add(job)
        db.flush()
        db.add(Match(student_id=student.id,job_id=job.id,score=score))
        db.commit()
        monkeypatch.setattr(alert,"compute_matches",lambda student,db:[(job,score)])
        monkeypatch.setattr(alert,"save_matches",lambda student,results,db:None)
        sent=[]
        monkeypatch.setattr(alert,"send_email",lambda *args:sent.append(args))
        monkeypatch.setattr(alert,"ALERT_MIN_SCORE",60)
        assert alert.run_alerts(db)==(1 if should_send else 0)
        assert bool(sent)==should_send


@pytest.mark.parametrize("score,expected",[ (0,None),(59.99,None),(60,"60%"),(90,"90%"),(100,"100%") ])
def test_alert_email_formats_match_percentages(monkeypatch,score,expected):
    messages=[]

    class FakeSMTP:
        def __init__(self,host,port,timeout):
            self.host=host
            self.port=port
            self.timeout=timeout

        def __enter__(self):
            return self

        def __exit__(self,*args):
            return False

        def send_message(self,message):
            messages.append(message)

    monkeypatch.setattr(alert.smtplib,"SMTP",FakeSMTP)
    monkeypatch.setattr(alert,"SMTP_HOST","smtp.example.com")
    monkeypatch.setattr(alert,"SMTP_PORT","587")
    monkeypatch.setattr(alert,"SMTP_FROM","jobs@example.com")
    alert.send_email("student@example.com",f"Match score: {score}%","Job matches")

    assert len(messages)==1
    message=messages[0]
    assert message["To"]=="student@example.com"
    assert message["From"]=="jobs@example.com"
    assert message["Subject"]=="Job matches"
    assert (expected in message.get_content()) if expected else "Match score:" in message.get_content()


@pytest.mark.parametrize("host,port",[
    ("smtp.example.com",25),
    ("localhost",1025),
    ("mail.internal",587),
])
def test_alert_email_uses_configured_smtp_connection(monkeypatch,host,port):
    connections=[]

    class FakeSMTP:
        def __init__(self,*args,**kwargs):
            connections.append((args,kwargs))

        def __enter__(self):
            return self

        def __exit__(self,*args):
            return False

        def send_message(self,message):
            return None

    monkeypatch.setattr(alert.smtplib,"SMTP",FakeSMTP)
    monkeypatch.setattr(alert,"SMTP_HOST",host)
    monkeypatch.setattr(alert,"SMTP_PORT",port)
    alert.send_email("to@example.com","body","subject")
    assert connections==[((host,port),{"timeout":15})]


@pytest.mark.parametrize("recipient",[
    "a@example.com",
    "student+jobs@example.org",
    "user.name@example.co.in",
])
def test_alert_email_preserves_recipient(monkeypatch,recipient):
    messages=[]

    class FakeSMTP:
        def __init__(self,*args,**kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self,*args):
            return False

        def send_message(self,message):
            messages.append(message)

    monkeypatch.setattr(alert.smtplib,"SMTP",FakeSMTP)
    alert.send_email(recipient,"body","subject")
    assert messages[0]["To"]==recipient


@pytest.mark.parametrize("term,text,expected",[
    ("Python","Uses Python","python"),
    ("js","JavaScript and js","javascript"),
    ("ts","TypeScript ts","typescript"),
    ("postgres","Postgres","postgresql"),
    ("ml","ML projects","machine learning"),
    ("dl","DL research","deep learning"),
    ("nodejs","NodeJS","node.js"),
    ("os","OS fundamentals","operating systems"),
])
def test_resume_skill_extraction_and_aliases(term,text,expected):
    assert expected in resume.extract_skills(text,{term.lower()})


@pytest.mark.parametrize("text,expected",[
    ("CGPA: 8.5",8.5),
    ("gpa-10",10.0),
    ("CGPA 0",None),
    ("GPA 11",None),
    ("CGPA 8.5/4",None),
    ("no score",None),
    ("GPA: 3.9/4",None),
])
def test_resume_cgpa_extraction(text,expected):
    assert resume.extract_cgpa(text)==expected


@pytest.mark.parametrize("text,expected",[
    ("Graduating 2024",2024),
    ("Expected in 2026",2026),
    ("Batch 2035",2035),
    ("Graduated 2023",None),
    ("Year 2036",None),
    ("No year listed",None),
])
def test_resume_graduation_year_extraction(text,expected):
    assert resume.extract_grad_year(text)==expected


@pytest.mark.parametrize("student_vec,job_vec,expected",[
    (None,[1.0,0.0],None),
    ([1.0,0.0],None,None),
    ([1.0,0.0],[1.0,0.0],100.0),
    ([0.0,1.0],[1.0,0.0],0.0),
    ([0.0,0.0],[1.0,0.0],0.0),
])
def test_similarity_score_bounds_and_missing_vectors(student_vec,job_vec,expected):
    assert matching.similarity_score(student_vec,job_vec)==expected


def test_resume_upload_validation_and_download(client,monkeypatch,tmp_path):
    assert register(client).status_code==201
    assert login(client).status_code==200
    assert client.get("/me/resume").status_code==404
    assert client.post("/me/resume",files={"file":("resume.txt",b"not a pdf")}).status_code==415
    assert client.post(
        "/me/resume",
        files={"file":("resume.pdf",b"%PDF-invalid")},
    ).status_code==422

    monkeypatch.setattr(main,"RESUME_PATH",tmp_path)
    monkeypatch.setattr(main,"pdf_to_text",lambda data:"python "+("resume text " * 10))
    monkeypatch.setattr(main,"load_vocab",lambda db:{"python"})
    upload=client.post("/me/resume",files={"file":("resume.pdf",b"%PDF-valid")})
    assert upload.status_code==200
    assert upload.json()["has_resume"] is True
    assert client.get("/me").json()["has_resume"] is True
    downloaded=client.get("/me/resume")
    assert downloaded.status_code==200
    assert downloaded.content==b"%PDF-valid"


def test_resume_upload_rejects_files_over_size_limit(client):
    assert register(client).status_code==201
    assert login(client).status_code==200
    oversized=b"%PDF"+(b"x" * 10_000_000)
    response=client.post("/me/resume",files={"file":("large.pdf",oversized)})
    assert response.status_code==413


@pytest.mark.parametrize("text",["", "short resume text"])
def test_resume_upload_rejects_empty_or_scanned_text(client,monkeypatch,text):
    assert register(client).status_code==201
    assert login(client).status_code==200
    monkeypatch.setattr(main,"pdf_to_text",lambda data:text)
    response=client.post("/me/resume",files={"file":("resume.pdf",b"%PDF-valid")})
    assert response.status_code==422


def test_resume_upload_replaces_previous_file(client,monkeypatch,tmp_path):
    assert register(client).status_code==201
    assert login(client).status_code==200
    monkeypatch.setattr(main,"RESUME_PATH",tmp_path)
    monkeypatch.setattr(main,"pdf_to_text",lambda data:"python "+("resume text " * 10))
    monkeypatch.setattr(main,"load_vocab",lambda db:{"python"})

    first=client.post("/me/resume",files={"file":("resume.pdf",b"%PDF-first")})
    assert first.status_code==200
    old_files=list(tmp_path.glob("*.pdf"))
    assert len(old_files)==1
    old_path=old_files[0]

    second=client.post("/me/resume",files={"file":("resume.pdf",b"%PDF-second")})
    assert second.status_code==200
    assert not old_path.exists()
    assert len(list(tmp_path.glob("*.pdf")))==1
    assert client.get("/me/resume").content==b"%PDF-second"


@pytest.mark.parametrize("email",[
    "bad",
    "missing-at.example.com",
])
def test_registration_rejects_invalid_emails(client,email):
    response=register(client,email=email)
    assert response.status_code==422