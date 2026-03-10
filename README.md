# 🎫 Ticket Tracking System (TTS)

A high-performance platform for teams to report, assign, and track software defects and tasks. This system bridges the gap between internal management and **JIRA integration**, providing advanced reporting, role-based access, and automated notification workflows.

---

## 🛠 Tech Stack
- **Backend:** Django & Django REST Framework (DRF)
- **Frontend:** React.js 
- **Database:** PostgreSQL (with Soft Delete implementation)
- **Auth:** JWT (SimpleJWT)
- **Testing:** Pytest & Pytest-Django
- **Tasks/Scheduler:** for Cron Jobs
- **Reports:** PDF Generation
- **Email:** Gmail

---

## 🔑 Key Features

### 1. Authentication & Roles
* **Admin:** Manage users/projects, assign tickets, set deadlines, and generate global reports.
* **Developer:** View assigned tasks, update status, add comments, and subscribe to ticket updates.
* **JWT-based Login:** Secure access with scoped permissions and role-based enforcement.

### 2. Project & JIRA Management
* **JIRA Sync:** Configure JIRA URL and Access Tokens per project. 
* **Archive System:** Projects can be moved to "Active" or "Archive" status; archived reports act as point-in-time snapshots.
* **Soft Delete:** Any delete operation marks data as inactive without removing it from the database.

### 3. Ticket Workflow
* **Attributes:** Title, Severity, Priority, Status (Open/In Progress/Resolved/Closed), and Deadlines.
* **Subscription:** Automatic subscription for Reporters and Assignees; manual subscription for others to receive updates.
* **Move Logic:** Support for moving tickets between projects (restricted to projects sharing the same JIRA URL).

### 4. Advanced Reporting & Notifications
* **Graphical Stats:** Visualize tickets by status, priority, and deadline compliance using React dashboards.
* **User Analytics:** Detailed stats on "Tickets Spilled" vs. "Deadlines Met."
* **Cron Jobs:** Automated email reminders for approaching deadlines (Developer) and overdue summaries (Admin CC).

---

## 📂 Project Structure

### Backend (Django)
```text
├── config/              # ASGI, WSGI, and settings/ directory
├── apps/                # Direct access to individual apps
│   ├── user/  # JWT & User Roles
│   ├── projects/        # Project & JIRA Config
│   ├── tickets/         # Ticket CRUD & JIRA API Logic
│   ├── notifications/   # Celery Tasks & Email Logic
│   └── reports/         # PDF Generation Logic
├── pytest.ini           # Pytest configuration
├── requirements.txt
└── manage.py
```

How to pull and run.
```bash
git clone https://github.com/jtg-induction/T2-BE-Ticket-Tracking-System/
cd ticket-tracking-system
pipenv install

pipenv shell

python manage.py migrate

python manage.py runserver
```
