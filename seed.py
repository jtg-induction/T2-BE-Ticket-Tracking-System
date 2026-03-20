import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from ticket.enums import Category, Priority, Status
from ticket.models import Ticket

# Exact imports based on your file structure
from user.enums import Roles

User = get_user_model()

print("--- Starting Data Seeding ---")

# 1. Create YOUR Login User (Superuser)
my_email = "admin@example.com"
my_password = "password123"

if not User.objects.filter(email=my_email).exists():
    admin_user = User.objects.create_superuser(
        email=my_email,
        password=my_password,
        jira_id="JIRA-ADMIN-001",
        jira_api_token="encrypted_token_here",
        first_name="Anmol",
        last_name="Admin",
        role=Roles.software_dev,  # This is "SD"
    )
    print(f"Created Superuser: {my_email} / {my_password}")
else:
    admin_user = User.objects.get(email=my_email)

# 2. Create Team Members
team = []
for i in range(4):
    u_email = f"member{i}@example.com"
    u, created = User.objects.get_or_create(
        email=u_email,
        defaults={
            "jira_id": f"JIRA-USER-{100 + i}",
            "jira_api_token": "token",
            "first_name": f"Developer_{i}",
            "role": random.choice(Roles.values),
        },
    )
    if created:
        u.set_password("password123")
        u.save()
    team.append(u)

# 3. Create Projects
projects = []
project_list = [("Nexus Core", "NEX"), ("Titan UI", "TTN"), ("Ghost Backend", "GHOST")]

for title, key in project_list:
    proj, _ = ProjectModel.objects.get_or_create(
        jira_project_key=key,
        site_url="https://iiituna.atlassian.net",
        defaults={"title": title, "owner": admin_user, "jira_id": f"PROJ-{key}"},
    )
    projects.append(proj)

    # Add everyone to every project
    for person in [admin_user] + team:
        ProjectMember.objects.get_or_create(
            project=proj,
            user=person,
            defaults={
                "is_admin": (person == admin_user),
                "status": MemberStatus.MEMBER,
            },
        )

# 4. Generate 75 Tickets with high variance
print("Generating tickets...")
now = timezone.now()

for i in range(75):
    proj = random.choice(projects)
    worker = random.choice(team + [admin_user])

    # Spread dates over last 90 days
    days_ago = random.randint(0, 90)
    created_date = now - timedelta(days=days_ago)

    # Deadline logic: 60% have deadlines
    deadline = None
    if random.random() > 0.4:
        deadline = created_date + timedelta(days=random.randint(5, 15))

    current_status = random.choice(Status.values)
    completion_date = None

    # If ticket is Done or Closed, set a completion date
    if current_status in [Status.DONE, Status.CLOSED]:
        # Some are completed late (Spilled)
        days_to_complete = random.randint(3, 20)
        completion_date = created_date + timedelta(days=days_to_complete)

    t = Ticket.objects.create(
        name=f"Task {i}: {random.choice(['Update', 'Fix', 'Debug'])} {proj.title}",
        jira_id=f"{proj.jira_project_key}-{500 + i}",
        project=proj,
        assignee=worker,
        reporter=admin_user,
        status=current_status,
        priority=random.choice(Priority.values),
        category=random.choice(Category.values),
        deadline=deadline,
        completed_at=completion_date,
    )

    # Force the creation date back in time
    Ticket.objects.filter(id=t.id).update(created_at=created_date)

print(f"--- Seeding Successful! Log in with: {my_email} ---")
