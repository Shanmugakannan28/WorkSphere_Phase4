from datetime import date, datetime, time

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String,
                        Text, Time, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="employee")  # admin|hr|manager|employee
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    pref_inapp: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    pref_email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    muted_types: Mapped[str] = mapped_column(String(200), default="", server_default="")


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(60), index=True)
    designation: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|inactive
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    salary: Mapped[float] = mapped_column(Float, default=0)  # monthly
    join_date: Mapped[date] = mapped_column(Date, default=date.today)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user: Mapped[User] = relationship()


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class EmployeeShift(Base):
    __tablename__ = "employee_shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"))
    shift: Mapped[Shift] = relationship()


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    check_in: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # present|late|half_day|absent|on_leave
    checkin_flag: Mapped[str | None] = mapped_column(String(20), nullable=True)  # early|on_time|late|no_shift
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual|auto


class LeavePolicy(Base):
    __tablename__ = "leave_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    leave_type: Mapped[str] = mapped_column(String(30), unique=True)
    days_per_year: Mapped[int] = mapped_column(Integer)  # 0 = unlimited


class LeaveBalance(Base):
    __tablename__ = "leave_balance"
    __table_args__ = (UniqueConstraint("employee_id", "leave_type", "year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type: Mapped[str] = mapped_column(String(30))
    year: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    used: Mapped[int] = mapped_column(Integer, default=0)


class Leave(Base):
    __tablename__ = "leaves"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|cancelled
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()


class Payroll(Base):
    __tablename__ = "payroll"
    __table_args__ = (UniqueConstraint("employee_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    basic: Mapped[float] = mapped_column(Float)
    allowances: Mapped[float] = mapped_column(Float, default=0)
    deductions: Mapped[float] = mapped_column(Float, default=0)
    bonus: Mapped[float] = mapped_column(Float, default=0)
    net: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="processed")
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20), default="info")  # info|late|leave|payroll|document|performance
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(200))
    file_url: Mapped[str] = mapped_column(String(200))  # authenticated download route
    stored_name: Mapped[str] = mapped_column(String(80))  # random on-disk name, never user-controlled
    doc_type: Mapped[str] = mapped_column(String(40), default="Other")
    content_type: Mapped[str] = mapped_column(String(60))
    size: Mapped[int] = mapped_column(Integer, default=0)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()


class Performance(Base):
    __tablename__ = "performance"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    review_period: Mapped[str] = mapped_column(String(40))
    rating: Mapped[float] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()


class Onboarding(Base):
    __tablename__ = "onboarding"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    task_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|completed
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()


class Resignation(Base):
    __tablename__ = "resignations"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    notice_period: Mapped[int] = mapped_column(Integer, default=30)  # days
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|withdrawn
    exit_stage: Mapped[str] = mapped_column(String(20), default="submitted")
    last_working_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()


class Announcement(Base):
    __tablename__ = "announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    assigned_to: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    employee: Mapped[Employee] = relationship()


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    employee: Mapped[Employee] = relationship()
