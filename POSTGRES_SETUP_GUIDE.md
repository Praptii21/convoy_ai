# PostgreSQL Setup & Connection Guide

This guide walks through setting up PostgreSQL and connecting your backend to it.

## Prerequisites

- PostgreSQL installed (v12 or higher)
- Python 3.8+
- Backend dependencies installed (`pip install -r requirements.txt`)

---

## 1. Install PostgreSQL

### macOS (using Homebrew)
```bash
brew install postgresql
brew services start postgresql
```

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### Windows
Download and run the installer from [postgresql.org](https://www.postgresql.org/download/windows/)
Make note of the password you set for the `postgres` user.

---

## 2. Create Database & User

Open PostgreSQL terminal:

```bash
# macOS/Linux
psql -U postgres

# Windows (use pgAdmin or run psql from PostgreSQL bin folder)
psql -U postgres
```

Once inside PostgreSQL prompt (`postgres=#`), run:

```sql
-- Create the database
CREATE DATABASE smart_convoy_db;

-- Create a user with password
CREATE USER convoy_user WITH PASSWORD 'convoy_pass';

-- Grant privileges to the user
ALTER ROLE convoy_user SET client_encoding TO 'utf8';
ALTER ROLE convoy_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE convoy_user SET default_transaction_deferrable TO on;
ALTER ROLE convoy_user SET default_time_zone TO 'UTC';

-- Grant database privileges
GRANT ALL PRIVILEGES ON DATABASE smart_convoy_db TO convoy_user;

-- Connect to the database
\c smart_convoy_db

-- Grant schema privileges
GRANT ALL PRIVILEGES ON SCHEMA public TO convoy_user;
```

Verify:
```sql
\l                    -- List databases (should see smart_convoy_db)
\du                   -- List users (should see convoy_user)
\c smart_convoy_db    -- Connect to database
\dt                   -- List tables (empty for now)
```

Exit with `\q`.

---

## 3. Configure Backend Environment

Create or update `.env` file in `backend/` folder:

```bash
cd backend
cat > .env << 'EOF'
DATABASE_URL=postgresql://convoy_user:convoy_pass@localhost:5432/smart_convoy_db
OPENWEATHER_KEY=your_key_here
GOOGLE_API_KEY=your_key_here
OSRM_URL=http://router.project-osrm.org/route/v1/driving
CLOSURE_RADIUS_KM=1.0
SAMPLE_DISTANCE_M=500
WEATHER_CACHE_MINUTES=5
EOF
```

Replace:
- `your_key_here` with actual API keys if you have them (optional for dev)
- Username: `convoy_user`
- Password: `convoy_pass`
- Host: `localhost`
- Port: `5432` (default PostgreSQL port)
- Database: `smart_convoy_db`

---

## 4. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

Key packages you'll need:
```bash
pip install sqlalchemy
pip install psycopg2-binary
pip install python-dotenv
```

---

## 5. Test Connection from Python

Create a test script `test_db.py` in `backend/`:

```python
import os
from dotenv import load_dotenv
import psycopg2

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print(f"Connecting to: {DATABASE_URL}")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT 1;")
    result = cursor.fetchone()
    print(f"✓ Connection successful! Result: {result}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"✗ Connection failed: {e}")
```

Run:
```bash
python test_db.py
```

Expected output:
```
Connecting to: postgresql://convoy_user:convoy_pass@localhost:5432/smart_convoy_db
✓ Connection successful! Result: (1,)
```

---

## 6. Create Database Tables (Schema)

Create `backend/database.py`:

```python
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Create engine
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Define Convoy table
class ConvoyDB(Base):
    __tablename__ = "convoys"
    
    id = Column(Integer, primary_key=True, index=True)
    convoy_name = Column(String, unique=True, index=True)
    source_lat = Column(Float)
    source_lon = Column(Float)
    destination_lat = Column(Float)
    destination_lon = Column(Float)
    priority = Column(String, default="medium")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Define Vehicle table
class VehicleDB(Base):
    __tablename__ = "vehicles"
    
    id = Column(Integer, primary_key=True, index=True)
    convoy_id = Column(Integer, index=True)
    registration_number = Column(String, unique=True, index=True)
    vehicle_type = Column(String)
    load_type = Column(String)
    load_weight_kg = Column(Float)
    capacity_kg = Column(Integer)
    driver_name = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)
print("✓ Tables created successfully!")
```

Run:
```bash
python database.py
```

Verify in PostgreSQL:
```bash
psql -U convoy_user -d smart_convoy_db -c "\dt"
```

You should see `convoys` and `vehicles` tables.

---

## 7. Common Connection Issues & Fixes

### Error: "FATAL: role 'convoy_user' does not exist"
**Fix:** Make sure you created the user in PostgreSQL:
```sql
CREATE USER convoy_user WITH PASSWORD 'convoy_pass';
```

### Error: "FATAL: database 'smart_convoy_db' does not exist"
**Fix:** Create the database:
```sql
CREATE DATABASE smart_convoy_db;
GRANT ALL PRIVILEGES ON DATABASE smart_convoy_db TO convoy_user;
```

### Error: "Connection refused" / "port 5432"
**Fix:** PostgreSQL is not running. Start it:
```bash
# macOS
brew services start postgresql

# Ubuntu
sudo systemctl start postgresql

# Windows (use Services app or pgAdmin)
```

### Error: "no password supplied" / "Ident authentication failed"
**Fix:** Update `.env` with correct credentials and ensure user exists with password:
```sql
ALTER USER convoy_user WITH PASSWORD 'convoy_pass';
```

### Error: "could not translate host name"
**Fix:** Use `localhost` or `127.0.0.1` in `.env`:
```
DATABASE_URL=postgresql://convoy_user:convoy_pass@localhost:5432/smart_convoy_db
```

---

## 8. Quick Reference Commands

### Connect to database
```bash
psql -U convoy_user -d smart_convoy_db
```

### View convoys
```sql
SELECT * FROM convoys;
```

### View vehicles
```sql
SELECT * FROM vehicles;
```

### Check user permissions
```sql
\du convoy_user
```

### Reset everything (⚠️ deletes data)
```sql
DROP DATABASE smart_convoy_db;
CREATE DATABASE smart_convoy_db;
GRANT ALL PRIVILEGES ON DATABASE smart_convoy_db TO convoy_user;
```

---

## 9. Next Steps

Once connected:
1. Update `routers/convoy_routes.py` to use SQLAlchemy ORM instead of in-memory dict
2. Replace `convoys_db: Dict[str, Convoy] = {}` with database queries
3. Use `SessionLocal()` to get database sessions in route handlers

Example:
```python
from database import SessionLocal, ConvoyDB

@router.post("/create")
def create_convoy(convoy: Convoy):
    db = SessionLocal()
    try:
        db_convoy = ConvoyDB(
            convoy_name=convoy.convoy_name,
            source_lat=convoy.source_lat,
            source_lon=convoy.source_lon,
            destination_lat=convoy.destination_lat,
            destination_lon=convoy.destination_lon,
            priority=convoy.priority.value
        )
        db.add(db_convoy)
        db.commit()
        db.refresh(db_convoy)
        return {"status": "success", "convoy_id": db_convoy.id}
    finally:
        db.close()
```

---

## Troubleshooting Checklist

- [ ] PostgreSQL is running (`psql -U postgres` works)
- [ ] Database exists (`\l` in psql shows `smart_convoy_db`)
- [ ] User exists with password (`\du` shows `convoy_user`)
- [ ] `.env` file is in `backend/` folder with correct `DATABASE_URL`
- [ ] `python test_db.py` returns success
- [ ] Tables exist (`\dt` shows `convoys` and `vehicles`)
- [ ] Backend can start without errors (`uvicorn main:app`)

---

## Support

If issues persist, check:
1. PostgreSQL logs: `tail -f /var/log/postgresql/postgresql.log`
2. Backend logs: Run `uvicorn main:app --reload` and watch terminal
3. Verify user: `psql -U convoy_user -d smart_convoy_db -c "SELECT 1;"`

Good luck! 🚀
