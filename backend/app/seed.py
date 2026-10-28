"""Demo data, created only when the database is empty."""
import datetime as dt
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (Announcement, Feedback, Onboarding, Task, Attendance, Employee, EmployeeShift, Leave, LeaveBalance, LeavePolicy,
                     Notification, Payroll, Performance, Shift, User)
from .config import settings
from .security import hash_password
from .services import init_balances, shift_window, workdays

ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME = settings.admin_email, settings.admin_password, settings.admin_name

# name, email, password, role, department, designation, manager email, monthly salary, shift
PEOPLE = [
    (ADMIN_NAME, ADMIN_EMAIL, ADMIN_PASSWORD, "admin", "Human Resources", "System Administrator", None, 120000, "Morning"),
    ("Priya Nair", "hr@worksphere.com", "Hr@12345", "hr", "Human Resources", "HR Manager", ADMIN_EMAIL, 90000, "Morning"),
    ("Rohan Mehta", "manager@worksphere.com", "Manager@123", "manager", "Engineering", "Engineering Manager", ADMIN_EMAIL, 110000, "Morning"),
    ("Neha Kapoor", "sales.manager@worksphere.com", "Manager@123", "manager", "Sales", "Sales Manager", ADMIN_EMAIL, 95000, "Morning"),
    ("Kannan", "kannan@worksphere.com", "Employee@123", "employee", "Engineering", "Backend Developer", "manager@worksphere.com", 70000, "Morning"),
    ("Ananya Iyer", "ananya@worksphere.com", "Employee@123", "employee", "Engineering", "QA Engineer", "manager@worksphere.com", 58000, "Evening"),
    ("Vikram Rao", "vikram@worksphere.com", "Employee@123", "employee", "Engineering", "Frontend Developer", "manager@worksphere.com", 68000, "Morning"),
    ("Isha Verma", "isha@worksphere.com", "Employee@123", "employee", "Engineering", "UI Designer", "manager@worksphere.com", 62000, "Evening"),
    ("Dev Malhotra", "dev@worksphere.com", "Employee@123", "employee", "Sales", "Account Executive", "sales.manager@worksphere.com", 55000, "Morning"),
    ("Sara Khan", "sara@worksphere.com", "Employee@123", "employee", "Sales", "Sales Associate", "sales.manager@worksphere.com", 48000, "Evening"),
    ("Arjun Das", "arjun@worksphere.com", "Employee@123", "employee", "Sales", "Support Agent", "sales.manager@worksphere.com", 42000, "Night"),
    ("Meera Pillai", "meera@worksphere.com", "Employee@123", "employee", "Finance", "Accountant", "hr@worksphere.com", 60000, "Morning"),
    ("Rahul Joshi", "rahul@worksphere.com", "Employee@123", "employee", "Finance", "Financial Analyst", "hr@worksphere.com", 64000, "Morning"),
    ("Tanvi Shah", "tanvi@worksphere.com", "Employee@123", "employee", "Human Resources", "Recruiter", "hr@worksphere.com", 52000, "Evening"),
]
# email, type, start offset, end offset, status, reason (offsets are days from today)
LEAVES = [
    ("kannan@worksphere.com", "Casual", 2, 3, "approved", "Family function"),
    ("vikram@worksphere.com", "Paid", 3, 4, "approved", "Short trip"),
    ("ananya@worksphere.com", "Sick", -1, 1, "approved", "Fever"),
    ("sara@worksphere.com", "Paid", -20, -18, "approved", "Vacation"),
    ("meera@worksphere.com", "Casual", -9, -9, "approved", "Personal work"),
    ("dev@worksphere.com", "Paid", 7, 9, "pending", "Wedding"),
    ("isha@worksphere.com", "Casual", 10, 10, "pending", "Appointment"),
]
FEEDBACK = ["Consistently delivers on time and collaborates well.",
            "Strong ownership; could improve on documentation.",
            "Meets expectations and is growing into a bigger role.",
            "Excellent quality of work and helpful to teammates.",
            "Good progress this period; needs to prioritise better."]


def seed(db: Session):
    if db.scalar(select(User.id)):
        return
    rnd, today = random.Random(7), dt.date.today()
    for t, n in (("Paid", 18), ("Casual", 8), ("Sick", 10), ("Unpaid", 0)):
        db.add(LeavePolicy(leave_type=t, days_per_year=n))
    shifts = {n: Shift(name=n, start_time=dt.time(a), end_time=dt.time(b))
              for n, a, b in (("Morning", 6, 14), ("Evening", 14, 22), ("Night", 22, 6))}
    db.add_all(shifts.values())
    db.flush()

    emps = {}
    for name, email, pw, role, dept, desig, mgr, sal, sh in PEOPLE:
        u = User(username=email.split("@")[0].lower(), email=email, password_hash=hash_password(pw), role=role)
        db.add(u)
        db.flush()
        e = Employee(user_id=u.id, name=name, email=email, department=dept, designation=desig,
                     salary=sal, join_date=today - dt.timedelta(days=rnd.randint(200, 900)))
        db.add(e)
        db.flush()
        emps[email] = e
        db.add(EmployeeShift(employee_id=e.id, shift_id=shifts[sh].id))
        init_balances(db, e.id)
    for name, email, pw, role, dept, desig, mgr, sal, sh in PEOPLE:
        if mgr:
            emps[email].manager_id = emps[mgr].id
    db.flush()

    leave_days = {}  # (employee_id) -> set of dates for approved leaves
    for email, typ, a, b, status, reason in LEAVES:
        e = emps[email]
        s, en = today + dt.timedelta(days=a), today + dt.timedelta(days=b)
        days = workdays(s, en)
        db.add(Leave(employee_id=e.id, leave_type=typ, start_date=s, end_date=en, days=days,
                     reason=reason, status=status, created_at=dt.datetime.now() - dt.timedelta(days=3)))
        if status == "approved":
            bal = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == e.id,
                                                       LeaveBalance.leave_type == typ,
                                                       LeaveBalance.year == today.year))
            if bal:
                bal.used += days
            d = s
            while d <= en:
                leave_days.setdefault(e.id, set()).add(d)
                d += dt.timedelta(days=1)

    # 45 days of attendance history
    shift_by_emp = {e.id: shifts[p[8]] for p in PEOPLE for e in [emps[p[1]]]}
    for back in range(45, 0, -1):
        day = today - dt.timedelta(days=back)
        if day.weekday() >= 5:
            continue
        for e in emps.values():
            sh = shift_by_emp[e.id]
            start, end = shift_window(sh, day)
            if day in leave_days.get(e.id, ()):
                db.add(Attendance(employee_id=e.id, date=day, status="on_leave", source="auto"))
                continue
            r = rnd.random()
            if r < 0.05:
                db.add(Attendance(employee_id=e.id, date=day, status="absent", source="auto"))
            elif r < 0.17:
                late = rnd.randint(14, 55)
                db.add(Attendance(employee_id=e.id, date=day, status="late", checkin_flag="late", late_minutes=late,
                                  check_in=start + dt.timedelta(minutes=late),
                                  check_out=end + dt.timedelta(minutes=rnd.randint(0, 20))))
            else:
                off = rnd.randint(-40, 9)
                db.add(Attendance(employee_id=e.id, date=day, status="present",
                                  checkin_flag="early" if off < -30 else "on_time",
                                  check_in=start + dt.timedelta(minutes=off),
                                  check_out=end + dt.timedelta(minutes=rnd.randint(-5, 25))))

    # performance reviews
    for p in PEOPLE:
        e = emps[p[1]]
        if p[3] == "admin":
            continue
        reviewer = emps[p[6]].user_id if p[6] else emps[ADMIN_EMAIL].user_id
        for i, period in enumerate(("2026 Q1", "2026 Q2")):
            db.add(Performance(employee_id=e.id, reviewer_id=reviewer, review_period=period,
                               rating=rnd.choice([3, 3.5, 4, 4, 4.5, 5]), feedback=rnd.choice(FEEDBACK),
                               created_at=dt.datetime.now() - dt.timedelta(days=150 - i * 90)))

    # last month's payroll
    prev = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    for e in emps.values():
        db.add(Payroll(employee_id=e.id, month=prev, basic=round(e.salary * .6, 2), allowances=round(e.salary * .4, 2), deductions=0, bonus=0, net=e.salary))
    for e in emps.values():
        db.add(Notification(user_id=e.user_id, title="Welcome to WorkSphere",
                            message="Check in from the dashboard, request leave, and view your documents here.",
                            type="info"))
    db.commit()


def seed_phase4(db: Session):
    """Demo data for Phase 4 (runs once, also on databases created by earlier phases)."""
    if db.scalar(select(Announcement.id)):
        return
    from .services import default_onboarding
    admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
    emps = list(db.scalars(select(Employee).join(User, User.id == Employee.user_id).where(User.role == "employee").order_by(Employee.id)))
    if not admin or not emps:
        return
    today, now = dt.date.today(), dt.datetime.now()
    db.add(Announcement(title="Welcome to WorkSphere Phase 4", pinned=True, created_by=admin.id,
                        message="You can now complete onboarding tasks, track your assigned tasks, share feedback, and export reports.\n\nOpen the menu on the left to explore."))
    db.add(Announcement(title="Quarterly town hall", created_by=admin.id,
                        message=f"Join us on {(today + dt.timedelta(days=5)):%d %b %Y} at 4 PM in the main hall. Agenda: company results, new policies and Q&A."))
    for i, e in enumerate(emps[-2:]):          # the two newest employees are "new joiners"
        default_onboarding(db, e)
        db.flush()
        for t in db.scalars(select(Onboarding).where(Onboarding.employee_id == e.id).limit(2 + 2 * i)):
            t.status, t.completed_at = "completed", now
    samples = [("Review the Q3 performance data", "Prepare a short summary for the town hall.", 4),
               ("Update your emergency contact", "Add the details in your profile.", 2),
               ("Complete the security awareness course", "30 minutes, link in the handbook.", 8)]
    for i, e in enumerate(emps[:6]):
        title, desc, due = samples[i % 3]
        db.add(Task(assigned_to=e.id, assigned_by=admin.id, title=title, description=desc,
                    due_date=today + dt.timedelta(days=due - (6 if i == 4 else 0)),
                    status="completed" if i == 3 else "pending", completed_at=now if i == 3 else None))
    for i, e in enumerate(emps[:5]):
        db.add(Feedback(employee_id=e.id, rating=[5, 4, 3, 4, 2][i], anonymous=i % 2 == 1,
                        message=["Great team culture and flexible hours.", "The new leave calendar is really helpful.",
                                 "Meeting rooms are often double-booked.", "Onboarding was smooth and well organised.",
                                 "Would like clearer career growth paths."][i]))
    db.commit()
