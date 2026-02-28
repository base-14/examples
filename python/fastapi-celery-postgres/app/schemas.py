from datetime import datetime

from pydantic import BaseModel


class TaskBase(BaseModel):
    title: str


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
