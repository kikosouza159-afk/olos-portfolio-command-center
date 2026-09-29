from sqlalchemy import select

from app.client_catalog import CLIENT_CATALOG
from app.db import Base, SessionLocal, engine
from app.models import Client


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = {name.casefold() for name in db.scalars(select(Client.name)).all()}
        added = 0
        for name in CLIENT_CATALOG:
            if name.casefold() in existing:
                continue
            db.add(Client(name=name, active=True))
            existing.add(name.casefold())
            added += 1
        db.commit()
        print(f"Clientes importados: {added}. Total do catálogo: {len(CLIENT_CATALOG)}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
