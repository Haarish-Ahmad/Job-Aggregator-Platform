# Job Aggregator Platform - Backend

FastAPI + SQLAlchemy + PostgreSQL backend for the Job Aggregator Platform. Students register, jobs are ingested (by the scraper), and each student gets a ranked list of matching jobs.

## Run locally

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

## API endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | /health | none | Health check |
| POST | /auth/register | none | Create a student account |
| POST | /auth/login | none | Log in, sets a session cookie |
| POST | /auth/logout | login | Clear the session |
| GET | /me | login | Current student profile |
| PATCH | /me/update | login | Update branch, cgpa, grad_year, skills, resume_link |
| GET | /me/matches | login | Eligible jobs ranked by skill match; optional `min_score` |
| POST | /company | login | Create a company |
| GET | /companies | login | List companies |
| POST | /internal/jobs | admin | Bulk ingest jobs, deduplicated by content hash |
| GET | /jobs | login | List jobs; filters `q`, `company_id`, `job_type`, `active_only`, `limit`, `offset` |
| GET | /jobs/{job_id} | login | Single job |

## Matching rules

A job is shown to a student only if all of these hold:

- The deadline has not passed.
- The student's CGPA is at least the job's `min_cgpa` (when set).
- The student's branch is in `allowed_branches` (when set).
- The student's `grad_year` is in `allowed_grads` (when set).

The score is the percentage of the job's required skills that the student has. A job with no required skills scores 100. This is rule-based matching, not machine learning.

## API test cases

42 manual test cases, run from [Bruno](https://www.usebruno.com/) against a local server. Run the sections in order, because later sections depend on earlier data and on who is logged in.

### Setup

1. Start the API (see above).
2. Start from an empty students table: `DELETE FROM students;`
3. In Bruno, set the method and URL in the request bar. Paste JSON into **Body**, set to **JSON**. Leave Headers empty.
4. Bruno keeps the session cookie between requests, so log in once per user.

### Test data

| Student | Branch | CGPA | Graduating | Skills |
|---|---|---|---|---|
| Asha | CSE | 8.5 (9.0 after TC-12) | 2026 | python, sql, docker |
| Ravi | ECE | 6.5 | 2027 | java |

Both use the password `Test@1234`.

### Summary

| ID | Test | Request | Expected |
|---|---|---|---|
| TC-01 | Server is up | `GET /health` | 200 |
| TC-02 | Profile without login | `GET /me` | 401 |
| TC-03 | Register Asha | `POST /auth/register` | 201 |
| TC-04 | Register Ravi | `POST /auth/register` | 201 |
| TC-05 | Duplicate email | `POST /auth/register` | 409 |
| TC-06 | Invalid email | `POST /auth/register` | 422 |
| TC-07 | Missing grad_year | `POST /auth/register` | 422 |
| TC-08 | Wrong password | `POST /auth/login` | 401 |
| TC-09 | Unknown email | `POST /auth/login` | 401 |
| TC-10 | Login as Asha | `POST /auth/login` | 200 |
| TC-11 | Read own profile | `GET /me` | 200 |
| TC-12 | Update cgpa and skills | `PATCH /me/update` | 200 |
| TC-13 | Empty body | `PATCH /me/update` | 200 |
| TC-14 | Try to set role | `PATCH /me/update` | 200 |
| TC-15 | Try to change email | `PATCH /me/update` | 200 |
| TC-16 | Invalid cgpa | `PATCH /me/update` | 422 |
| TC-17 | Create company | `POST /company` | 201 |
| TC-18 | Duplicate company | `POST /company` | 409 |
| TC-19 | List companies | `GET /companies` | 200 |
| TC-20 | Ingest as student | `POST /internal/jobs` | 403 |
| TC-21 | Ingest six jobs | `POST /internal/jobs` | 200 |
| TC-22 | Ingest same payload again | `POST /internal/jobs` | 200 |
| TC-23 | Missing title | `POST /internal/jobs` | 422 |
| TC-24 | Bad deadline format | `POST /internal/jobs` | 422 |
| TC-25 | All jobs | `GET /jobs` | 200 |
| TC-26 | Search text | `GET /jobs?q=backend` | 200 |
| TC-27 | Filter by company | `GET /jobs?company_id=1` | 200 |
| TC-28 | Filter by type | `GET /jobs?job_type=internship` | 200 |
| TC-29 | Pagination | `GET /jobs?limit=2&offset=2` | 200 |
| TC-30 | Limit above maximum is clamped | `GET /jobs?limit=500` | 200 |
| TC-31 | Job by id | `GET /jobs/1` | 200 |
| TC-32 | Job not found | `GET /jobs/9999` | 404 |
| TC-33 | Invalid id | `GET /jobs/abc` | 422 |
| TC-34 | Asha's matches | `GET /me/matches` | 200 |
| TC-35 | Minimum score filter | `GET /me/matches?min_score=60` | 200 |
| TC-36 | Idempotent save | `GET /me/matches` | 200 |
| TC-37 | Ravi's matches | `GET /me/matches` | 200 |
| TC-38 | Ravi cannot ingest | `POST /internal/jobs` | 403 |
| TC-39 | Logout | `POST /auth/logout` | 200 |
| TC-40 | Profile after logout | `GET /me` | 401 |
| TC-41 | Jobs after logout | `GET /jobs` | 401 |
| TC-42 | Matches after logout | `GET /me/matches` | 401 |

### Health and access

Run before logging in. Confirms the server is up and protected routes reject anonymous requests.

#### TC-01: Server is up

- **Request:** `GET http://localhost:8000/health`
- **Expected status:** 200
- **Expected result:** Returns the health payload.

#### TC-02: Profile without login

- **Request:** `GET http://localhost:8000/me`
- **Before:** Logged out
- **Expected status:** 401
- **Expected result:** Rejected, no student data returned.

### Register

Schema field names must equal model column names, because the route builds Students(**data.model_dump()).

#### TC-03: Register Asha

- **Request:** `POST http://localhost:8000/auth/register`
- **Before:** Empty students table
- **Expected status:** 201
- **Expected result:** Student returned with id and role=student. No password or password_hash in the response.

Body (JSON):

```json
{
  "name": "Asha",
  "email": "asha@snuchennai.edu.in",
  "password": "Test@1234",
  "branch": "CSE",
  "cgpa": 8.5,
  "grad_year": 2026,
  "skills": [
    "python",
    "sql",
    "docker"
  ]
}
```

#### TC-04: Register Ravi

- **Request:** `POST http://localhost:8000/auth/register`
- **Expected status:** 201
- **Expected result:** Second student created.

Body (JSON):

```json
{
  "name": "Ravi",
  "email": "ravi@snuchennai.edu.in",
  "password": "Test@1234",
  "branch": "ECE",
  "cgpa": 6.5,
  "grad_year": 2027,
  "skills": [
    "java"
  ]
}
```

#### TC-05: Duplicate email

- **Request:** `POST http://localhost:8000/auth/register`
- **Before:** TC-03 done
- **Expected status:** 409
- **Expected result:** Rejected, no second row created.

Body (JSON):

```json
{
  "name": "Asha",
  "email": "asha@snuchennai.edu.in",
  "password": "Test@1234",
  "branch": "CSE",
  "cgpa": 8.5,
  "grad_year": 2026,
  "skills": [
    "python",
    "sql",
    "docker"
  ]
}
```

#### TC-06: Invalid email

- **Request:** `POST http://localhost:8000/auth/register`
- **Expected status:** 422
- **Expected result:** Validation error on email.

Body (JSON):

```json
{
  "name": "X",
  "email": "abc",
  "password": "Test@1234",
  "grad_year": 2026
}
```

#### TC-07: Missing grad_year

- **Request:** `POST http://localhost:8000/auth/register`
- **Expected status:** 422
- **Expected result:** grad_year is required.

Body (JSON):

```json
{
  "name": "X",
  "email": "x@snuchennai.edu.in",
  "password": "Test@1234"
}
```

### Login and session

A successful login sets a session cookie. Bruno stores it for later requests in the collection.

#### TC-08: Wrong password

- **Request:** `POST http://localhost:8000/auth/login`
- **Expected status:** 401
- **Expected result:** Rejected, no cookie set.

Body (JSON):

```json
{
  "email": "asha@snuchennai.edu.in",
  "password": "wrong"
}
```

#### TC-09: Unknown email

- **Request:** `POST http://localhost:8000/auth/login`
- **Expected status:** 401
- **Expected result:** Same response as a wrong password, so accounts cannot be enumerated.

Body (JSON):

```json
{
  "email": "nobody@snuchennai.edu.in",
  "password": "x"
}
```

#### TC-10: Login as Asha

- **Request:** `POST http://localhost:8000/auth/login`
- **Expected status:** 200
- **Expected result:** Student returned (response_model StudentOut). Session cookie appears.

Body (JSON):

```json
{
  "email": "asha@snuchennai.edu.in",
  "password": "Test@1234"
}
```

#### TC-11: Read own profile

- **Request:** `GET http://localhost:8000/me`
- **Before:** Logged in as Asha
- **Expected status:** 200
- **Expected result:** Asha's data, with no password fields.

### Update profile

PATCH applies only fields declared in StudentUpdate. Anything else is ignored.

#### TC-12: Update cgpa and skills

- **Request:** `PATCH http://localhost:8000/me/update`
- **Before:** Logged in as Asha
- **Expected status:** 200
- **Expected result:** Only cgpa and skills change. Name, branch, grad_year stay the same.

Body (JSON):

```json
{
  "cgpa": 9.0,
  "skills": [
    "python",
    "sql",
    "docker",
    "react"
  ]
}
```

#### TC-13: Empty body

- **Request:** `PATCH http://localhost:8000/me/update`
- **Expected status:** 200
- **Expected result:** Nothing changes.

Body (JSON):

```json
{}
```

#### TC-14: Try to set role

- **Request:** `PATCH http://localhost:8000/me/update`
- **Before:** Security check
- **Expected status:** 200
- **Expected result:** Role stays student. Verify with GET /me. Add extra="forbid" to StudentUpdate to return 422 instead.

Body (JSON):

```json
{
  "role": "admin"
}
```

#### TC-15: Try to change email

- **Request:** `PATCH http://localhost:8000/me/update`
- **Before:** Security check
- **Expected status:** 200
- **Expected result:** Email stays unchanged. Verify with GET /me.

Body (JSON):

```json
{
  "email": "hacker@x.com"
}
```

#### TC-16: Invalid cgpa

- **Request:** `PATCH http://localhost:8000/me/update`
- **Expected status:** 422
- **Expected result:** Rejected by the ge=0, le=10 rule.

Body (JSON):

```json
{
  "cgpa": 11
}
```

### Companies

#### TC-17: Create company

- **Request:** `POST http://localhost:8000/company`
- **Before:** Logged in
- **Expected status:** 201
- **Expected result:** Company returned with id.

Body (JSON):

```json
{
  "company_name": "Zoho",
  "careers_url": "https://www.zoho.com/careers",
  "description": "Software company"
}
```

#### TC-18: Duplicate company

- **Request:** `POST http://localhost:8000/company`
- **Expected status:** 409
- **Expected result:** Rejected, company_name is unique.

Body (JSON):

```json
{
  "company_name": "Zoho",
  "careers_url": "https://www.zoho.com/careers",
  "description": "Software company"
}
```

#### TC-19: List companies

- **Request:** `GET http://localhost:8000/companies`
- **Expected status:** 200
- **Expected result:** List contains Zoho.

### Job ingestion (admin only)

The scraper will call this route. Make Asha an admin in SQLTools, then log in again so the session picks up the role:  UPDATE students SET role='admin' WHERE email='asha@snuchennai.edu.in';

#### TC-20: Ingest as student

- **Request:** `POST http://localhost:8000/internal/jobs`
- **Before:** Asha is still a student
- **Expected status:** 403
- **Expected result:** Rejected before any insert.

Body (JSON):

```json
{
  "jobs": [
    {
      "company_name": "Zoho",
      "title": "T",
      "apply_url": "https://z.com/0"
    }
  ]
}
```

#### TC-21: Ingest six jobs

- **Request:** `POST http://localhost:8000/internal/jobs`
- **Before:** Asha is admin and logged in again
- **Expected status:** 200
- **Expected result:** inserted 6, skipped 0. Infosys is created automatically.

Body (JSON):

```json
{
  "jobs": [
    {
      "company_name": "Zoho",
      "title": "Backend Intern",
      "apply_url": "https://zoho.com/j/1",
      "location": "Chennai",
      "job_type": "internship",
      "description": "FastAPI work",
      "min_cgpa": 7.0,
      "allowed_branches": [
        "CSE",
        "IT"
      ],
      "allowed_grads": [
        2026,
        2027
      ],
      "required_skills": [
        "python",
        "sql"
      ],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Zoho",
      "title": "High CGPA Role",
      "apply_url": "https://zoho.com/j/2",
      "min_cgpa": 9.5,
      "required_skills": [
        "python"
      ],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Zoho",
      "title": "Expired Role",
      "apply_url": "https://zoho.com/j/3",
      "required_skills": [
        "python"
      ],
      "deadline": "2020-01-01"
    },
    {
      "company_name": "Zoho",
      "title": "ECE Only",
      "apply_url": "https://zoho.com/j/4",
      "allowed_branches": [
        "ECE"
      ],
      "required_skills": [
        "java"
      ],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Infosys",
      "title": "Open Role",
      "apply_url": "https://infosys.com/j/5",
      "required_skills": [],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Infosys",
      "title": "Half Match",
      "apply_url": "https://infosys.com/j/6",
      "required_skills": [
        "python",
        "kubernetes"
      ],
      "deadline": "2026-12-31"
    }
  ]
}
```

#### TC-22: Ingest same payload again

- **Request:** `POST http://localhost:8000/internal/jobs`
- **Expected status:** 200
- **Expected result:** inserted 0, skipped 6. content_hash dedup works.

Body (JSON):

```json
{
  "jobs": [
    {
      "company_name": "Zoho",
      "title": "Backend Intern",
      "apply_url": "https://zoho.com/j/1",
      "location": "Chennai",
      "job_type": "internship",
      "description": "FastAPI work",
      "min_cgpa": 7.0,
      "allowed_branches": [
        "CSE",
        "IT"
      ],
      "allowed_grads": [
        2026,
        2027
      ],
      "required_skills": [
        "python",
        "sql"
      ],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Zoho",
      "title": "High CGPA Role",
      "apply_url": "https://zoho.com/j/2",
      "min_cgpa": 9.5,
      "required_skills": [
        "python"
      ],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Zoho",
      "title": "Expired Role",
      "apply_url": "https://zoho.com/j/3",
      "required_skills": [
        "python"
      ],
      "deadline": "2020-01-01"
    },
    {
      "company_name": "Zoho",
      "title": "ECE Only",
      "apply_url": "https://zoho.com/j/4",
      "allowed_branches": [
        "ECE"
      ],
      "required_skills": [
        "java"
      ],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Infosys",
      "title": "Open Role",
      "apply_url": "https://infosys.com/j/5",
      "required_skills": [],
      "deadline": "2026-12-31"
    },
    {
      "company_name": "Infosys",
      "title": "Half Match",
      "apply_url": "https://infosys.com/j/6",
      "required_skills": [
        "python",
        "kubernetes"
      ],
      "deadline": "2026-12-31"
    }
  ]
}
```

#### TC-23: Missing title

- **Request:** `POST http://localhost:8000/internal/jobs`
- **Expected status:** 422
- **Expected result:** title is required.

Body (JSON):

```json
{
  "jobs": [
    {
      "company_name": "Zoho",
      "apply_url": "https://z.com/9"
    }
  ]
}
```

#### TC-24: Bad deadline format

- **Request:** `POST http://localhost:8000/internal/jobs`
- **Expected status:** 422
- **Expected result:** Date must be YYYY-MM-DD.

Body (JSON):

```json
{
  "jobs": [
    {
      "company_name": "Zoho",
      "title": "X",
      "apply_url": "https://z.com/9",
      "deadline": "31-12-2026"
    }
  ]
}
```

### Job listing

Query parameters go in the Params tab or straight into the URL.

#### TC-25: All jobs

- **Request:** `GET http://localhost:8000/jobs`
- **Before:** Logged in
- **Expected status:** 200
- **Expected result:** Six jobs.

#### TC-26: Search text

- **Request:** `GET http://localhost:8000/jobs?q=backend`
- **Expected status:** 200
- **Expected result:** Only Backend Intern.

#### TC-27: Filter by company

- **Request:** `GET http://localhost:8000/jobs?company_id=1`
- **Expected status:** 200
- **Expected result:** Only Zoho jobs.

#### TC-28: Filter by type

- **Request:** `GET http://localhost:8000/jobs?job_type=internship`
- **Expected status:** 200
- **Expected result:** Only Backend Intern.

#### TC-29: Pagination

- **Request:** `GET http://localhost:8000/jobs?limit=2&offset=2`
- **Expected status:** 200
- **Expected result:** Two jobs, starting at the third.

#### TC-30: Limit above maximum is clamped

- **Request:** `GET http://localhost:8000/jobs?limit=500`
- **Expected status:** 200
- **Expected result:** limit is capped at 100 in code, so at most 100 jobs are returned. No error.

#### TC-31: Job by id

- **Request:** `GET http://localhost:8000/jobs/1`
- **Expected status:** 200
- **Expected result:** The job with id 1.

#### TC-32: Job not found

- **Request:** `GET http://localhost:8000/jobs/9999`
- **Expected status:** 404
- **Expected result:** Not found.

#### TC-33: Invalid id

- **Request:** `GET http://localhost:8000/jobs/abc`
- **Expected status:** 422
- **Expected result:** id must be an integer.

### Matching

Asha now has cgpa 9.0, branch CSE, graduating 2026, skills python, sql, docker, react.

#### TC-34: Asha's matches

- **Request:** `GET http://localhost:8000/me/matches`
- **Before:** Logged in as Asha
- **Expected status:** 200
- **Expected result:** Backend Intern 100.0, Open Role 100.0, Half Match 50.0. Excluded: High CGPA Role (min 9.5), Expired Role (deadline passed), ECE Only (branch). Sorted by score, highest first.

#### TC-35: Minimum score filter

- **Request:** `GET http://localhost:8000/me/matches?min_score=60`
- **Expected status:** 200
- **Expected result:** Half Match is dropped.

#### TC-36: Idempotent save

- **Request:** `GET http://localhost:8000/me/matches`
- **Expected status:** 200
- **Expected result:** Call twice, then run SELECT * FROM matches; There must be no duplicate student_id, job_id rows.

#### TC-37: Ravi's matches

- **Request:** `GET http://localhost:8000/me/matches`
- **Before:** Log in as Ravi first
- **Expected status:** 200
- **Expected result:** Only ECE Only (100.0) and Open Role (100.0). Backend Intern is excluded by branch and cgpa.

#### TC-38: Ravi cannot ingest

- **Request:** `POST http://localhost:8000/internal/jobs`
- **Before:** Logged in as Ravi
- **Expected status:** 403
- **Expected result:** Students cannot use the admin route.

Body (JSON):

```json
{
  "jobs": [
    {
      "company_name": "Zoho",
      "title": "T",
      "apply_url": "https://z.com/0"
    }
  ]
}
```

### Logout

#### TC-39: Logout

- **Request:** `POST http://localhost:8000/auth/logout`
- **Before:** Logged in
- **Expected status:** 200
- **Expected result:** Session cleared.

#### TC-40: Profile after logout

- **Request:** `GET http://localhost:8000/me`
- **Expected status:** 401
- **Expected result:** Status code only.

#### TC-41: Jobs after logout

- **Request:** `GET http://localhost:8000/jobs`
- **Expected status:** 401
- **Expected result:** Status code only.

#### TC-42: Matches after logout

- **Request:** `GET http://localhost:8000/me/matches`
- **Expected status:** 401
- **Expected result:** Status code only.

### Issues found while writing these tests

- Schema field names must match model column names exactly. `Students(**data.model_dump())` raises `TypeError` on any name the model does not have.
- `StudentOut` must not inherit `StudentDetails`. It inherited `password`, which the model does not have, and caused a `ResponseValidationError` after the row was already committed.
- `response_model` must match what the route returns. A route that returns a list needs `list[...]`, for example `response_model=list[MatchOut]`.
- Job eligibility by graduation batch uses `allowed_grads` only. There is no `year_grad` column on jobs.
- The ingest schema uses `company_name`. The scraper payload must use the same name.
- Unknown fields in a PATCH body are ignored, so TC-14 and TC-15 return 200 with no change. Add `extra="forbid"` to `StudentUpdate` to return 422 instead.
- `limit` on `/jobs` is clamped with `min(limit, 100)`. Also guard against zero and negative values: `limit = max(1, min(limit, 100))`.