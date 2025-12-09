from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, unique=True)
    name = Column(String, index=True)
    avatar = Column(String, nullable=True)
    last_sync = Column(DateTime, nullable=True, default=datetime.now)
    total_msgs = Column(Integer, default=0)
    loaded_msgs = Column(Integer, default=0)
    progress = Column(Integer, default=0)
    status = Column(String, default='pending') # completed, pending, error
    
    notes = relationship("Note", back_populates="account")

class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    link = Column(String)
    cover = Column(String, nullable=True)
    create_time = Column(DateTime, default=datetime.now)
    publish_time = Column(DateTime, nullable=True)
    read_count = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey('accounts.id'))
    
    account = relationship("Account", back_populates="notes")

# Database setup
# Use absolute path or relative to execution context. 
# Here we use a file in the same directory as this script usually, but for safety in dev:
SQLALCHEMY_DATABASE_URL = "sqlite:///./xhs_data.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

