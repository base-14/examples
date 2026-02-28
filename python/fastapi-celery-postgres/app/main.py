from fastapi import Depends, FastAPI, HTTPException
from opentelemetry.propagate import inject
from sqlalchemy.orm import Session

from . import models, schemas, tasks
from .database import SessionLocal, engine
from .telemetry import setup_telemetry

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Set up OpenTelemetry
setup_telemetry(app, engine)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/ping")
async def ping():
    return {"message": "pong"}


@app.post("/tasks/", response_model=schemas.Task)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    db_task = models.Task(title=task.title)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    # Distributed Tracing: Propagate trace context across async boundary
    # Without this, the Celery worker would start a new trace, breaking
    # the correlation between HTTP request → task queue → worker execution.
    # The inject() adds W3C traceparent header that the worker extracts.
    headers: dict[str, str] = {}
    inject(headers)
    tasks.process_task.apply_async(args=[db_task.id], headers=headers)

    return db_task


@app.get("/tasks/", response_model=list[schemas.Task])
def read_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tasks = db.query(models.Task).offset(skip).limit(limit).all()
    return tasks


@app.get("/tasks/{task_id}", response_model=schemas.Task)
def read_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
