"""
data/seed.py
Seed script — populates the database with realistic dummy data for development
and testing: 10 clients, 5 recruiters, 50 candidates, 20 jobs, placements,
timesheets, and payroll records.

Usage:
    python -m data.seed
    python -m data.seed --reset    # wipes existing seed data first
"""
import argparse
import random
from datetime import date, datetime, timedelta

from db.models import (
    get_session, Client, Recruiter, Candidate, Job, Placement,
    Timesheet, Payroll, VisaStatusEnum, JobStatusEnum, PlacementStageEnum,
    TimesheetStatusEnum,
)

random.seed(42)  # reproducible seed data

# ── Reference data ────────────────────────────────────────────────────────────

SKILLS_POOL = [
    "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform",
    "SQL", "PostgreSQL", "MongoDB", "Redis", "Spark", "Kafka",
    "Machine Learning", "Data Engineering", "DevOps", "CI/CD",
    "Salesforce", "SAP", "Tableau", "Power BI", "Snowflake",
    "C#", ".NET", "Go", "Rust", "Scala", "Ruby on Rails",
]

LOCATIONS = [
    "New York, NY", "San Francisco, CA", "Austin, TX", "Chicago, IL",
    "Seattle, WA", "Boston, MA", "Atlanta, GA", "Remote", "Dallas, TX",
    "Denver, CO",
]

INDUSTRIES = [
    "Financial Services", "Healthcare", "Technology", "Retail",
    "Manufacturing", "Insurance", "Telecom", "Energy",
]

CLIENT_NAMES = [
    "Meridian Financial", "Northwind Health", "Vertex Technologies",
    "Summit Retail Group", "Atlas Manufacturing", "Pinnacle Insurance",
    "Coastal Telecom", "BrightPath Energy", "Horizon Bank", "Cedar Analytics",
]

RECRUITER_NAMES = [
    ("Alex Recruiter", "alex@company.com", "Tech"),
    ("Priya Sharma", "priya@company.com", "Finance"),
    ("Marcus Lee", "marcus@company.com", "Healthcare"),
    ("Dana Kim", "dana@company.com", "Tech"),
    ("Jordan Patel", "jordan.p@company.com", "Enterprise"),
]

FIRST_NAMES = [
    "James", "Maria", "Wei", "Fatima", "John", "Aisha", "Carlos", "Yuki",
    "Olga", "David", "Priyanka", "Tom", "Linda", "Ahmed", "Sofia", "Kevin",
    "Nina", "Raj", "Emma", "Lucas", "Mei", "Omar", "Grace", "Diego",
    "Hana", "Victor", "Ana", "Sam", "Ravi", "Claire",
]
LAST_NAMES = [
    "Smith", "Garcia", "Chen", "Khan", "Brown", "Patel", "Rodriguez", "Tanaka",
    "Ivanova", "Johnson", "Sharma", "Wilson", "Davis", "Hassan", "Lopez",
    "Murphy", "Singh", "Müller", "Kim", "Nguyen",
]

VISA_WEIGHTS = {
    VisaStatusEnum.citizen: 0.40, VisaStatusEnum.gc: 0.20, VisaStatusEnum.h1b: 0.25,
    VisaStatusEnum.opt: 0.08, VisaStatusEnum.stem_opt: 0.04, VisaStatusEnum.ead: 0.03,
}

JOB_TITLES = [
    "Senior Software Engineer", "Data Engineer", "DevOps Engineer",
    "ML Engineer", "Cloud Architect", "Backend Developer (Python)",
    "Full Stack Developer", "QA Automation Engineer", "Business Analyst",
    "Data Scientist", "Site Reliability Engineer", "Salesforce Developer",
    "SAP Consultant", "Project Manager (IT)", "Network Engineer",
    "Security Engineer", "Frontend Developer (React)", "Database Administrator",
    "Scrum Master", "Technical Program Manager",
]


def weighted_choice(weights: dict):
    items, probs = zip(*weights.items())
    return random.choices(items, weights=probs, k=1)[0]


# ── Seed functions ───────────────────────────────────────────────────────────

def seed_clients(session) -> list[Client]:
    clients = []
    for i, name in enumerate(CLIENT_NAMES):
        client = Client(
            name=name,
            industry=random.choice(INDUSTRIES),
            contact_name=f"Contact Person {i+1}",
            contact_email=f"contact{i+1}@{name.lower().replace(' ', '')}.com",
            status="active",
            req_volume=random.randint(1, 8),
            margin_pct=round(random.uniform(8, 30), 1),
        )
        session.add(client)
        clients.append(client)
    session.flush()
    return clients


def seed_recruiters(session) -> list[Recruiter]:
    recruiters = []
    for name, email, team in RECRUITER_NAMES:
        rec = Recruiter(name=name, email=email, team=team)
        session.add(rec)
        recruiters.append(rec)
    session.flush()
    return recruiters


def seed_candidates(session, n=50) -> list[Candidate]:
    candidates = []
    for i in range(n):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        skills = random.sample(SKILLS_POOL, k=random.randint(3, 7))
        is_contractor = random.random() < 0.4

        candidate = Candidate(
            name=name,
            email=f"{first.lower()}.{last.lower()}{i}@example.com",
            phone=f"+1-555-{random.randint(1000,9999)}",
            skills=skills,
            visa_status=weighted_choice(VISA_WEIGHTS),
            location=random.choice(LOCATIONS),
            yoe=round(random.uniform(1, 15), 1),
            rate=round(random.uniform(50, 140), 0),
            is_active_contractor=is_contractor,
            tenure_days=random.randint(30, 720) if is_contractor else None,
            comms_gap_days=random.randint(0, 30) if is_contractor else None,
            overtime_pct=round(random.uniform(0, 25), 1) if is_contractor else None,
            client_feedback_score=round(random.uniform(2.5, 5.0), 1) if is_contractor else None,
        )
        session.add(candidate)
        candidates.append(candidate)
    session.flush()
    return candidates


def seed_jobs(session, clients: list[Client], n=20) -> list[Job]:
    jobs = []
    for i in range(n):
        client = random.choice(clients)
        required = random.sample(SKILLS_POOL, k=random.randint(3, 6))
        rate_min = round(random.uniform(50, 90), 0)

        job = Job(
            title=JOB_TITLES[i % len(JOB_TITLES)],
            client_id=client.id,
            jd_text=(
                f"We are looking for a {JOB_TITLES[i % len(JOB_TITLES)]} "
                f"with experience in {', '.join(required[:3])}. "
                f"This role is based in {random.choice(LOCATIONS)}."
            ),
            required_skills=required,
            location=random.choice(LOCATIONS),
            remote_ok=random.random() < 0.3,
            rate_min=rate_min,
            rate_max=rate_min + round(random.uniform(15, 40), 0),
            visa_requirement=None if random.random() < 0.7 else VisaStatusEnum.citizen,
            min_yoe=round(random.uniform(1, 5), 1),
            max_yoe=round(random.uniform(6, 15), 1),
            status=weighted_choice({
                JobStatusEnum.open: 0.6, JobStatusEnum.on_hold: 0.15,
                JobStatusEnum.filled: 0.15, JobStatusEnum.closed: 0.10,
            }),
        )
        session.add(job)
        jobs.append(job)
    session.flush()
    return jobs


def seed_placements(session, candidates, jobs, recruiters, clients) -> list[Placement]:
    placements = []
    stage_weights = {
        PlacementStageEnum.submitted: 0.35, PlacementStageEnum.interview: 0.25,
        PlacementStageEnum.offer: 0.10, PlacementStageEnum.hire: 0.15,
        PlacementStageEnum.rejected: 0.15,
    }
    # Create 60 placements across random candidate/job pairs
    for _ in range(60):
        candidate = random.choice(candidates)
        job = random.choice(jobs)
        stage = weighted_choice(stage_weights)
        bill_rate = job.rate_min + random.uniform(0, (job.rate_max or job.rate_min + 20) - job.rate_min)
        pay_rate = bill_rate * random.uniform(0.65, 0.85)

        placement = Placement(
            candidate_id=candidate.id,
            job_id=job.id,
            recruiter_id=random.choice(recruiters).id,
            client_id=job.client_id,
            stage=stage,
            match_score=round(random.uniform(40, 98), 1),
            skill_gap={"missing": random.sample(SKILLS_POOL, k=random.randint(0, 3))},
            bill_rate=round(bill_rate, 2),
            pay_rate=round(pay_rate, 2),
            margin=round(bill_rate - pay_rate, 2),
            submitted_at=datetime.utcnow() - timedelta(days=random.randint(0, 180)),
        )
        session.add(placement)
        placements.append(placement)
    session.flush()
    return placements


def seed_timesheets_and_payroll(session, candidates):
    """For active contractors, create ~12 weeks of timesheets + payroll history."""
    active = [c for c in candidates if c.is_active_contractor]

    for candidate in active:
        bill_rate = candidate.rate * random.uniform(1.25, 1.6)
        pay_rate = candidate.rate

        # Weekly timesheets for the last 12 weeks
        for week_offset in range(12):
            week_start = date.today() - timedelta(weeks=week_offset)
            week_start = week_start - timedelta(days=week_start.weekday())  # Monday

            hours = round(random.uniform(35, 45), 1)
            overtime = max(0, hours - 40)

            # ~5% chance of an anomaly for testing PyOD in Sprint 5
            is_anomaly = random.random() < 0.05
            if is_anomaly:
                hours = round(random.uniform(60, 80), 1)  # suspiciously high
                overtime = hours - 40

            ts = Timesheet(
                contractor_id=candidate.id,
                week_start=week_start,
                hours=hours,
                overtime_hours=round(overtime, 1),
                status=TimesheetStatusEnum.flagged if is_anomaly else TimesheetStatusEnum.approved,
                anomaly_flag=is_anomaly,
                anomaly_score=round(random.uniform(0.7, 0.95), 2) if is_anomaly else None,
                anomaly_reason="Unusually high weekly hours" if is_anomaly else None,
            )
            session.add(ts)

        # Monthly payroll for the last 3 months
        for month_offset in range(3):
            period = (date.today().replace(day=1) - timedelta(days=30 * month_offset)).replace(day=1)
            margin = bill_rate - pay_rate
            payroll = Payroll(
                contractor_id=candidate.id,
                period=period,
                bill_rate=round(bill_rate, 2),
                pay_rate=round(pay_rate, 2),
                margin=round(margin, 2),
                margin_pct=round((margin / bill_rate) * 100, 1),
            )
            session.add(payroll)

    session.flush()


# ── Main ─────────────────────────────────────────────────────────────────────

def reset(session):
    """Delete all seed data (preserves users table)."""
    from db.models import Prediction
    for model in [Payroll, Timesheet, Placement, Job, Candidate, Recruiter, Client, Prediction]:
        session.query(model).delete()
    session.commit()
    print("✅ Existing data cleared")


def main(do_reset: bool = False):
    session = get_session()
    try:
        if do_reset:
            reset(session)

        print("Seeding clients...")
        clients = seed_clients(session)

        print("Seeding recruiters...")
        recruiters = seed_recruiters(session)

        print("Seeding candidates...")
        candidates = seed_candidates(session, n=50)

        print("Seeding jobs...")
        jobs = seed_jobs(session, clients, n=20)

        print("Seeding placements...")
        placements = seed_placements(session, candidates, jobs, recruiters, clients)

        print("Seeding timesheets and payroll...")
        seed_timesheets_and_payroll(session, candidates)

        session.commit()

        print("\n✅ Seed complete:")
        print(f"   {len(clients)} clients")
        print(f"   {len(recruiters)} recruiters")
        print(f"   {len(candidates)} candidates ({sum(1 for c in candidates if c.is_active_contractor)} active contractors)")
        print(f"   {len(jobs)} jobs")
        print(f"   {len(placements)} placements")

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe existing seed data first")
    args = parser.parse_args()
    main(do_reset=args.reset)
