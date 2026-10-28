import datetime as dt
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Role = Literal["admin", "hr", "manager", "employee"]


class _Strip(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class LoginIn(_Strip):
    email: str = Field(min_length=1, max_length=120)  # email or username
    password: str = Field(min_length=1, max_length=128)


USERNAME = r"^[A-Za-z0-9_.-]{3,40}$"


class RegisterIn(_Strip):
    username: str = Field(pattern=USERNAME)
    email: str = Field(pattern=EMAIL, max_length=120)
    full_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class EmployeeIn(_Strip):
    username: Optional[str] = Field(None, pattern=USERNAME)
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=EMAIL, max_length=120)
    department: str = Field(min_length=1, max_length=60)
    designation: str = Field(min_length=1, max_length=80)
    role: Role = "employee"
    manager_id: Optional[int] = None
    salary: float = Field(0, ge=0, le=10_000_000)
    join_date: Optional[dt.date] = None
    shift_id: Optional[int] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class EmployeeUpdate(_Strip):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    department: Optional[str] = Field(None, min_length=1, max_length=60)
    designation: Optional[str] = Field(None, min_length=1, max_length=80)
    role: Optional[Role] = None
    status: Optional[Literal["active", "inactive"]] = None
    manager_id: Optional[int] = None
    salary: Optional[float] = Field(None, ge=0, le=10_000_000)


class ShiftIn(_Strip):
    name: str = Field(min_length=2, max_length=40)
    start_time: dt.time
    end_time: dt.time

    @model_validator(mode="after")
    def _diff(self):
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        return self


class AssignIn(BaseModel):
    employee_id: int
    shift_id: int


class LeaveIn(_Strip):
    leave_type: str = Field(min_length=2, max_length=30)
    start_date: dt.date
    end_date: dt.date
    reason: str = Field("", max_length=500)

    @model_validator(mode="after")
    def _order(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if (self.end_date - self.start_date).days > 90:
            raise ValueError("A request cannot exceed 90 days")
        return self


class ReviewIn(_Strip):
    status: Literal["approved", "rejected"]


class PerformanceIn(_Strip):
    employee_id: int
    review_period: str = Field(min_length=2, max_length=40)
    rating: float = Field(ge=1, le=5)
    feedback: str = Field("", max_length=2000)


class PayrollRunIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


MUTABLE_TYPES = ["late", "leave", "payroll", "document", "performance", "announcement", "task", "onboarding", "exit"]


class OnboardingIn(_Strip):
    employee_id: int
    task_name: str = Field(min_length=2, max_length=120)
    due_date: Optional[dt.date] = None


class StatusIn(BaseModel):
    status: Literal["pending", "completed"]


class ResignationIn(_Strip):
    reason: str = Field(min_length=10, max_length=1000)
    notice_period: int = Field(30, ge=0, le=180)


class ExitStageIn(BaseModel):
    stage: Literal["notice_period", "handover", "clearance", "settlement", "completed"]


class AnnouncementIn(_Strip):
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=3, max_length=5000)
    pinned: bool = False


class TaskIn(_Strip):
    assigned_to: int
    title: str = Field(min_length=2, max_length=120)
    description: str = Field("", max_length=2000)
    due_date: Optional[dt.date] = None


class TaskUpdate(_Strip):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    due_date: Optional[dt.date] = None


class FeedbackIn(_Strip):
    message: str = Field(min_length=5, max_length=2000)
    rating: int = Field(ge=1, le=5)
    anonymous: bool = False


class ProfileIn(_Strip):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    phone: Optional[str] = Field(None, max_length=30)
    address: Optional[str] = Field(None, max_length=200)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if v and not re.fullmatch(r"[0-9+()\- ]{6,30}", v):
            raise ValueError("Enter a valid phone number")
        return v


class PrefsIn(BaseModel):
    pref_inapp: bool = True
    pref_email: bool = False
    muted_types: list[str] = []

    @field_validator("muted_types")
    @classmethod
    def _types(cls, v):
        bad = [t for t in v if t not in MUTABLE_TYPES]
        if bad:
            raise ValueError("Unknown notification type: " + ", ".join(bad))
        return sorted(set(v))


class TestEmailIn(BaseModel):
    to: Optional[str] = Field(None, pattern=EMAIL, max_length=120)
