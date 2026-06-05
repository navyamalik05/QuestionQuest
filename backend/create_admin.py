#!/usr/bin/env python3

from database import SessionLocal, AdminUser, Base, engine
from passlib.context import CryptContext

# Make sure all tables exist
Base.metadata.create_all(engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

print("=== Create Admin User ===\n")
name     = input("Admin name:     ").strip()
email    = input("Admin email:    ").strip().lower()
password = input("Admin password: ").strip()

if not all([name, email, password]):
    print("❌ All fields are required.")
    exit(1)

if len(password) < 8:
    print("❌ Password must be at least 8 characters.")
    exit(1)

db = SessionLocal()

existing = db.query(AdminUser).filter(AdminUser.email == email).first()
if existing:
    print(f"❌ An admin with email '{email}' already exists.")
    db.close()
    exit(1)

admin = AdminUser(
    name=name,
    email=email,
    password_hash=pwd_context.hash(password),
    is_active=True
)
db.add(admin)
db.commit()
print(f"\n✅ Admin '{name}' ({email}) created successfully!")
print("   You can now log in to the Admin Portal.")
db.close()