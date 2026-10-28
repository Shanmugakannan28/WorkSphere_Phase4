import datetime as dt
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attendance, Employee, Leave, Performance, User
from ..security import require_roles
from ..services import scope_ids

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def _rate(a, b):
    return round(100 * a / b, 1) if b else 0


@router.get("/overview")
def overview(start: Optional[dt.date] = None, end: Optional[dt.date] = None, department: Optional[str] = None,
             db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr", "manager"))):
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=29)
    if start > end or (end - start).days > 366:
        raise HTTPException(400, "Invalid date range (max 366 days)")
    stmt = select(Employee).where(Employee.status == "active")
    ids = scope_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Employee.id.in_(ids))
    if department:
        stmt = stmt.where(Employee.department == department)
    emps = list(db.scalars(stmt))
    eids = [e.id for e in emps]
    dept_of = {e.id: e.department for e in emps}

    att = list(db.scalars(select(Attendance).where(
        Attendance.employee_id.in_(eids), Attendance.date.between(start, end)))) if eids else []
    leaves = list(db.scalars(select(Leave).where(
        Leave.employee_id.in_(eids), Leave.status == "approved",
        Leave.start_date <= end, Leave.end_date >= start))) if eids else []
    pending = len(list(db.scalars(select(Leave.id).where(Leave.employee_id.in_(eids), Leave.status == "pending")))) if eids else 0
    reviews = list(db.scalars(select(Performance).where(Performance.employee_id.in_(eids)))) if eids else []

    # attendance trend (weekdays only)
    days, d = {}, start
    while d <= end:
        if d.weekday() < 5:
            days[d] = {"present": 0, "late": 0, "absent": 0, "on_leave": 0}
        d += dt.timedelta(days=1)
    for a in att:
        if a.date in days and a.status in days[a.date]:
            days[a.date][a.status] += 1
    trend = [{"date": k.isoformat(), **v} for k, v in days.items()]

    # leave trend by month and type
    by_month = defaultdict(lambda: defaultdict(int))
    for l in leaves:
        by_month[l.start_date.strftime("%Y-%m")][l.leave_type] += l.days
    months = sorted(by_month)
    types = sorted({t for m in by_month.values() for t in m})
    leave_trend = {"months": months, "types": types,
                   "data": {t: [by_month[m].get(t, 0) for m in months] for t in types}}

    # performance
    ratings = defaultdict(list)
    for r in reviews:
        ratings[r.employee_id].append(r.rating)
    avg = {i: sum(v) / len(v) for i, v in ratings.items()}
    dist = {str(i): 0 for i in range(1, 6)}
    for v in avg.values():
        dist[str(min(5, max(1, round(v))))] += 1
    names = {e.id: e.name for e in emps}
    top = sorted(avg.items(), key=lambda x: -x[1])[:5]

    # department report
    rep = []
    for dep in sorted(set(dept_of.values())):
        dids = {i for i, dd in dept_of.items() if dd == dep}
        da = [a for a in att if a.employee_id in dids]
        p, la, ab = (sum(1 for a in da if a.status == s) for s in ("present", "late", "absent"))
        dr = [avg[i] for i in dids if i in avg]
        rep.append({"department": dep, "headcount": len(dids), "present": p, "late": la, "absent": ab,
                    "attendance_rate": _rate(p + la, p + la + ab), "late_rate": _rate(la, p + la),
                    "leave_days": sum(l.days for l in leaves if l.employee_id in dids),
                    "avg_rating": round(sum(dr) / len(dr), 2) if dr else None})

    tp, tl, ta = (sum(1 for a in att if a.status == s) for s in ("present", "late", "absent"))
    allr = list(avg.values())
    return {"range": {"start": start, "end": end},
            "kpis": {"headcount": len(emps), "attendance_rate": _rate(tp + tl, tp + tl + ta), "late_count": tl,
                     "absent_count": ta, "leave_days": sum(l.days for l in leaves),
                     "avg_rating": round(sum(allr) / len(allr), 2) if allr else None, "pending_leaves": pending},
            "attendance_trend": trend, "leave_trend": leave_trend,
            "rating_distribution": dist,
            "top_performers": [{"name": names[i], "rating": round(v, 2)} for i, v in top],
            "departments": rep}
