from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,DeclarativeBase
from config import get_settings

DATABASE_URL=get_settings().database_url
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
