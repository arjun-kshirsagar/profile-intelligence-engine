from app.db import SessionLocal
from app.models import Evaluation

db = SessionLocal()
eval = db.query(Evaluation).order_by(Evaluation.id.desc()).first()
print(f"ID: {eval.id}")
print(f"Status: {eval.status}")
print(f"Stage: {eval.stage}")
