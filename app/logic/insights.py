"""Analytics for administrators: where citizens need better information.

Everything here comes from daily totals, anonymous search text with personal
details removed, and citizen reports. None of it identifies a visitor.
"""

from collections import Counter
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.logic.dashboard import bar_rows
from app.logic.reports import PROBLEM_LABELS
from app.logic.verification import overall_status
from app.models import (
    CitizenReport,
    DailyView,
    GovernmentInstitution,
    GovernmentService,
    SearchLog,
)

PERIOD_DAYS = 30
TOP_LIMIT = 8


def top_counts(rows):
    """Keep the largest few of a list of (label, count) pairs, as bar rows."""
    counts = Counter()
    for label, count in rows:
        if label:
            counts[label] += count
    return bar_rows(dict(counts.most_common(TOP_LIMIT)))


def build_insights(today=None):
    today = today or date.today()
    since = today - timedelta(days=PERIOD_DAYS)

    searches = db.session.execute(
        select(SearchLog.query_text, func.count())
        .where(func.date(SearchLog.searched_at) >= since.isoformat())
        .group_by(SearchLog.query_text)
    ).all()
    failed = db.session.execute(
        select(SearchLog.query_text, func.count())
        .where(
            func.date(SearchLog.searched_at) >= since.isoformat(),
            SearchLog.results_count == 0,
        )
        .group_by(SearchLog.query_text)
    ).all()

    viewed = db.session.execute(
        select(GovernmentService.name, func.sum(DailyView.view_count))
        .join(DailyView, DailyView.service_id == GovernmentService.id)
        .where(DailyView.view_date >= since)
        .group_by(GovernmentService.id)
    ).all()

    institution_views = db.session.execute(
        select(GovernmentInstitution.name, func.sum(DailyView.view_count))
        .join(DailyView, DailyView.institution_id == GovernmentInstitution.id)
        .where(DailyView.view_date >= since)
        .group_by(GovernmentInstitution.id)
    ).all()
    institution_searches = db.session.execute(
        select(GovernmentInstitution.name, func.count())
        .join(SearchLog, SearchLog.top_institution_id == GovernmentInstitution.id)
        .where(func.date(SearchLog.searched_at) >= since.isoformat())
        .group_by(GovernmentInstitution.id)
    ).all()

    reported = db.session.execute(
        select(CitizenReport.service_name, func.count()).group_by(CitizenReport.service_name)
    ).all()
    problems = db.session.execute(
        select(CitizenReport.problem_type, func.count()).group_by(CitizenReport.problem_type)
    ).all()

    services = db.session.scalars(
        select(GovernmentService)
        .where(GovernmentService.is_archived.is_(False))
        .options(
            joinedload(GovernmentService.institution),
            selectinload(GovernmentService.verification_records),
        )
        .order_by(GovernmentService.name)
    ).unique().all()

    return {
        "period_days": PERIOD_DAYS,
        "searched": top_counts(searches),
        "failed_searches": top_counts(failed),
        "viewed": top_counts(viewed),
        "institutions": top_counts(list(institution_views) + list(institution_searches)),
        "reported": top_counts(reported),
        "problems": top_counts(
            (PROBLEM_LABELS.get(kind, kind), count) for kind, count in problems
        ),
        "outdated": [s for s in services if overall_status(s, today) == "outdated"],
    }
