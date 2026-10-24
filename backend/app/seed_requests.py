"""Demo data for M10: Sunrise Tower service requests, committee tenure, meetings and one open vote."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from .models.core import User
from .models.property import Unit
from .models.requests import CommitteeMember, Meeting, Proposal, ProposalVote, RequestComment, ServiceRequest
from .routers.complaints import DEFAULT_SLA


def seed_requests(db, ctx):
    sun = ctx["sunrise"]
    usr = lambda k: db.scalar(select(User).where(User.email == f"{k}@flatwise.demo"))
    units = {u.number: u for u in db.scalars(select(Unit).where(Unit.property_id == sun.id))}
    ago = lambda h: datetime.now(timezone.utc) - timedelta(hours=h)
    ct, pa = usr("caretaker"), usr("padmin")
    # (category, title, unit, raised by, status, hours ago, assignee, rating, reopened, resolved hours ago, text)
    rows = [
        ("lift", "Block A lift stops between floors", "A-501", "owner", "open", 60, None, None, 0, None, "The Block A lift stopped between the 4th and 5th floor twice today. Nobody was inside."),
        ("water", "Low water pressure on the 3rd floor", "B-302", "tenant", "assigned", 5, ct, None, 0, None, "No water in the kitchen tap since morning."),
        ("electricity", "Corridor light out on floor 5", "A-501", "owner", "in_progress", 8, ct, None, 0, None, "Two tube lights in the 5th floor corridor are dead."),
        ("security", "Main gate latch is broken", "A-801", "ownerrep", "in_progress", 3, ct, None, 0, None, "The pedestrian gate does not lock at night."),
        ("cleaning", "Garbage not collected from Block B", "B-302", "owner2", "resolved", 30, ct, None, 0, 6, "Bins on the B block landing overflow."),
        ("noise", "Drilling after 10 pm", "B-302", "tenant", "closed", 120, pa, 4, 0, 100, "Renovation noise late at night in the flat above."),
        ("other", "Visitor parking sign needed", "A-501", "owner", "closed", 216, pa, 5, 0, 190, "Visitors park in resident slots because the area is not marked."),
        ("water", "Leaking pipe in the basement", "A-501", "owner", "assigned", 96, ct, None, 1, None, "The leak came back after the first repair."),
        ("lift", "Lift button panel damaged", "B-302", "owner2", "closed", 288, ct, 3, 0, 260, "Buttons for floors 6 and 7 do not light up."),
        ("electricity", "Generator did not start in load shedding", "A-801", "ownerrep", "resolved", 26, ct, None, 0, 20, "The generator failed to start for 40 minutes last night."),
        ("security", "Stranger near the parking area", "B-302", "tenant", "closed", 360, pa, 5, 0, 350, "A stranger was seen checking car doors."),
        ("cleaning", "Stairwell needs cleaning, Block A", "A-501", "owner", "open", 2, None, None, 0, None, ""),
    ]
    for cat, title, unit, who, status, h, assignee, rating, reopened, res_h, text in rows:
        created = ago(h)
        r = ServiceRequest(property_id=sun.id, unit_id=units[unit].id, raised_by=usr(who).id, category=cat, title=title, text=text, status=status, assignee_id=assignee.id if assignee else None,
                           created_at=created, sla_hours=DEFAULT_SLA[cat], due_at=created + timedelta(hours=DEFAULT_SLA[cat]), reopened=reopened, rating=rating,
                           rating_note="Fixed on time." if rating and rating >= 4 else ("Took a while." if rating else ""),
                           assigned_at=created + timedelta(hours=1) if assignee else None, resolved_at=ago(res_h) if res_h else None, closed_at=ago(res_h - 8) if status == "closed" and res_h else None)
        if reopened:
            r.due_at = ago(-10)
        db.add(r)
        db.flush()
        db.add(RequestComment(request_id=r.id, user_id=r.raised_by, text="raised", kind="event", at=created))
        if assignee:
            db.add(RequestComment(request_id=r.id, user_id=pa.id, text=f"assigned:{assignee.name}", kind="event", at=created + timedelta(hours=1)))
        if status in ("in_progress", "resolved", "closed"):
            db.add(RequestComment(request_id=r.id, user_id=ct.id, text="We are on it. Parts will arrive tomorrow." if status == "in_progress" else "Done. Please check and confirm.", at=created + timedelta(hours=3)))
        if status in ("resolved", "closed"):
            db.add(RequestComment(request_id=r.id, user_id=ct.id, text="status:resolved", kind="event", at=ago(res_h)))
    # committee with tenure
    today = date.today()
    mem = {}
    for key, name, bn, role, start, end, email in (
            ("pres", "Dr. Kamal Uddin", "ডা. কামাল উদ্দিন", "president", date(2026, 1, 1), date(2028, 12, 31), "president"),
            ("sec", "Shirin Akter", "শিরীন আক্তার", "secretary", date(2026, 1, 1), date(2027, 12, 31), "secretary"),
            ("tre", "Abdul Karim", "আব্দুল করিম", "treasurer", date(2025, 1, 1), today + timedelta(days=45), "treasurer"),
            ("mem", "Jahangir Alam", "জাহাঙ্গীর আলম", "member", date(2025, 1, 1), date(2027, 12, 31), "member"),
            ("old", "Rafiqul Islam", "রফিকুল ইসলাম", "president", date(2023, 1, 1), date(2025, 12, 31), None)):
        m = CommitteeMember(property_id=sun.id, user_id=usr(email).id if email else None, name=name, name_bn=bn, role=role, start_date=start, end_date=end,
                            note="Previous president" if key == "old" else "")
        db.add(m)
        db.flush()
        mem[key] = m
    cur = [mem[k] for k in ("pres", "sec", "tre", "mem")]
    att = lambda present: [{"member_id": m.id, "name": m.name, "name_bn": m.name_bn, "role": m.role, "present": m.id in present} for m in cur]
    db.add(Meeting(property_id=sun.id, title="Monthly committee meeting, August", held_on=today - timedelta(days=52), place="Ground floor hall", status="held", created_by=usr("secretary").id,
                   agenda="1. Service charge dues\n2. Lift service contract\n3. Security guard roster", attendance=att({mem[k].id for k in ("pres", "sec", "tre", "mem")}),
                   minutes="The committee reviewed dues for July. The lift service contract will be re-tendered. The guard roster was adjusted for night shifts.",
                   decisions=["Re-tender the lift service contract by October", "Send SMS reminders for dues older than 60 days", "Add one night guard on Fridays"]))
    db.add(Meeting(property_id=sun.id, title="Monthly committee meeting, September", held_on=today - timedelta(days=21), place="Ground floor hall", status="held", created_by=usr("secretary").id,
                   agenda="1. Roof waterproofing quotes\n2. Generator service\n3. Parking rules", attendance=att({mem[k].id for k in ("pres", "sec", "tre")}),
                   minutes="Three roof waterproofing quotes were compared. The generator service will be monthly. Visitor parking will be marked.",
                   decisions=["Take a final decision on roof waterproofing after a site visit", "Monthly generator service from October", "Mark visitor parking bays"]))
    db.add(Meeting(property_id=sun.id, title="Monthly committee meeting, November", held_on=today + timedelta(days=12), place="Ground floor hall", status="scheduled", created_by=usr("secretary").id,
                   agenda="1. Lift motor overhaul vote result\n2. Annual general meeting preparation\n3. Budget 2027", attendance=att(set())))
    # one open vote and one closed vote
    p = Proposal(property_id=sun.id, title="Approve the lift motor overhaul quotation (Block A)", text="Metro Lift Service quoted BDT 1,20,000 for the Block A motor overhaul, with a 12 month warranty. Approve to go ahead.", created_by=usr("secretary").id,
                 created_at=datetime.now(timezone.utc) - timedelta(days=2))
    db.add(p)
    db.flush()
    for who, choice in (("president", "approve"), ("secretary", "approve"), ("treasurer", "reject")):
        db.add(ProposalVote(proposal_id=p.id, user_id=usr(who).id, choice=choice))
    q = Proposal(property_id=sun.id, title="Monthly generator service from October", text="Contract the generator vendor for a monthly service visit.", created_by=usr("president").id, status="closed", result="approved",
                 tally={"approve": 4, "reject": 1, "eligible": 5}, created_at=datetime.now(timezone.utc) - timedelta(days=19), closed_at=datetime.now(timezone.utc) - timedelta(days=14))
    db.add(q)
    db.flush()
    for who, choice in (("president", "approve"), ("secretary", "approve"), ("treasurer", "approve"), ("member", "approve"), ("owner", "reject")):
        db.add(ProposalVote(proposal_id=q.id, user_id=usr(who).id, choice=choice))
    db.flush()
