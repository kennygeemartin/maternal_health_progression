"""Local operator command; public registration never grants administrator privileges."""
from getpass import getpass
from sqlalchemy import select
from .database import Base, engine, SessionLocal, User
from .main import password_hash

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    email = input("Administrator email: ").strip().lower()
    name = input("Name: ").strip()
    password = getpass("Password (at least 10 characters): ")
    if len(password) < 10 or "@" not in email or not name:
        raise SystemExit("Invalid administrator details")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("Email already registered; no account was changed")
        db.add(User(email=email, name=name, password_hash=password_hash(password), role="admin"))
        db.commit()
    print("Administrator created")
