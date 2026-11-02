from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,DeclarativeBase

DATABASE_URL="postgresql://jobs:jobs@localhost:5432/jobs"
engine=create_engine(DATABASE_URL,pool_pre_ping=True)
session_local=sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db=session_local()
    try:
        yield db
    finally:
        db.close()    
