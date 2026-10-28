# WorkSphere HRMS: Phases 1 to 4 (complete)

FastAPI backend + vanilla JS frontend, served together from **one port** (http://127.0.0.1:8000).

## Run
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```
Open http://127.0.0.1:8000 (API docs at /docs). On first start a `.env` with a random SECRET_KEY and
a SQLite DB with demo data are created automatically. Delete `worksphere.db` to reset.

## Demo logins
| Role | Email | Password |
|---|---|---|
| Admin | admin@worksphere.com | Admin@123 |
| HR | hr@worksphere.com | Hr@12345 |
| Manager | manager@worksphere.com | Manager@123 |
| Employee | kabir@worksphere.com | Employee@123 |

## Phase 1 and 2 (core + RBAC)
- Auth: register (always EMPLOYEE), login by email or username, JWT with role, protected routes, role-based menus.
- Roles: EMPLOYEE / HR / ADMIN (+ MANAGER for team-level approvals). Every API checks the role and ownership.
- Employees (add/edit/search), attendance (one check-in per day, late tracking, half-day, overtime), leave (apply/approve, policies, balances, over-use blocked),
  payroll (basic + allowances, deductions, overtime bonus, monthly summary, payslip download), dashboard KPIs, notifications bell.
- Self-service: My profile, attendance history, leave tracking, salary/payslips. Admin: User management page (create, change role, activate/deactivate, reset password, delete).

## Phase 4 (Employee experience and integrations)
- 21 Onboarding: default checklist auto-created for new employees, HR/managers add tasks, employees tick them off, progress per employee.
- 22 Resignation and exit: submit/withdraw, HR approve/reject, exit stages (notice, handover, clearance, settlement, completed). Completing the exit deactivates the login.
- 23 Announcements: HR/Admin post (optionally pinned), everyone reads, list + detail page, everyone is alerted.
- 24 Tasks: HR/Admin/Managers assign (managers only to their team), assignees update status, overdue tracking.
- 25 Integrations: CSV and PDF exports (role-scoped, formula-injection safe), .ics calendar file + "Add to Google Calendar" links, email alerts via SMTP (.env) or storage/outbox.log when SMTP is not set.
- 26 Feedback: rating + message, optional anonymous, HR dashboard.
- 27 Profile and settings: edit name/phone/address, change password, in-app/email preferences and per-type muting.

Existing databases are upgraded automatically (new tables and columns are added on start). Demo Phase 4 data is added once.

## Change the admin login
Edit `.env` (ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME), delete `worksphere.db`, run again.

## Phase 3 modules
- 14 Shifts and attendance: shifts/assignments, check-in/out, late (after grace) and early detection, auto-mark absent/on-leave (background job every 10 min + manual button), weekly schedule.
- 15 Leave calendar: month calendar, team availability by day, conflict rule (max 2 per department on leave per day, set LEAVE_CONFLICT_LIMIT).
- 16 Documents: validated upload (type, size, magic bytes), random on-disk names, authenticated download, owner/HR-only access, expiry alerts.
- 17 Performance: reviews (1-5), history, no self-review, scoped by role.
- 18 Analytics: attendance/leave trends, rating insights, department report, date/department filters, CSV export.
- 19 Alerts: late attendance, leave requests/decisions, payroll, document expiry; bell badge polls every 6 s.
- 20 Employee search: name/department/role search; status, attendance and performance filters.

## Security
JWT (HS256) auth, role checks on every route (admin/hr/manager/employee, managers limited to their team), Pydantic validation, PBKDF2 password hashing, login throttling, secrets in `.env`, files outside the web root.

Notes: the DB is SQLite for easy local use; change DATABASE_URL for another database. Alerts use polling, not WebSockets.
