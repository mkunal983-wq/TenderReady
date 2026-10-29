"""Exact, version-scoped component links. No fuzzy clause assignment."""
import re
from sqlalchemy import select
from .models import RequirementVersion, SourceSpan, Assessment, ReviewDecision
from .product_scope import requirement_scope


def components(db, parent):
    source = db.get(SourceSpan, parent.source_span_id)
    spans = list(db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == parent.workspace_id,
        SourceSpan.document_version_id == source.document_version_id)))
    scope = requirement_scope(parent, spans)
    if scope['state'] == 'needs_review':
        return []
    candidates = db.scalars(select(RequirementVersion).join(SourceSpan,
        RequirementVersion.source_span_id == SourceSpan.id).where(
        RequirementVersion.workspace_id == parent.workspace_id,
        SourceSpan.document_version_id == source.document_version_id,
        SourceSpan.page == source.page, RequirementVersion.id != parent.id)).all()
    linked = []
    for child in candidates:
        if len(child.statement) >= len(parent.statement):
            continue  # Strictly decreasing text length makes dependency cycles impossible.
        if db.scalar(select(RequirementVersion.id).where(RequirementVersion.workspace_id == parent.workspace_id,
                RequirementVersion.supersedes_id == child.id).limit(1)):
            continue
        child_scope = requirement_scope(child, spans)
        if child_scope['state'] == 'needs_review' or child_scope['key'] != scope['key']:
            continue
        matches = list(re.finditer(r'(?m)^\s*' + re.escape(child.statement) + r'\s*$', parent.statement))
        if len(matches) != 1:
            continue
        latest = db.scalar(select(Assessment).where(Assessment.workspace_id == parent.workspace_id,
            Assessment.requirement_version_id == child.id).order_by(Assessment.created_at.desc(), Assessment.id.desc()).limit(1))
        review_id = db.scalar(select(ReviewDecision.id).where(ReviewDecision.assessment_id == latest.id).order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc()).limit(1)) if latest else None
        linked.append({'review_id': review_id, 'requirement_id':child.id, 'assessment_id':latest.id if latest else None,
            'source_document_id':source.document_version_id, 'page':source.page, 'quote':child.statement})
    # Identical candidate clauses cannot be resolved by choosing the newest arbitrarily.
    return [item for item in linked if sum(other['quote'] == item['quote'] for other in linked) == 1]


def changed(db, parent):
    for item in parent.checks:
        if item.get('method') != 'component_dependency':
            continue
        rid = item['requirement_id']
        if db.scalar(select(RequirementVersion.id).where(RequirementVersion.workspace_id == parent.workspace_id,
                RequirementVersion.supersedes_id == rid).limit(1)):
            return True
        latest = db.scalar(select(Assessment.id).where(Assessment.workspace_id == parent.workspace_id,
            Assessment.requirement_version_id == rid).order_by(Assessment.created_at.desc(),Assessment.id.desc()).limit(1))
        review_id = db.scalar(select(ReviewDecision.id).where(ReviewDecision.assessment_id == latest).order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc()).limit(1)) if latest else None
        if review_id != item.get('review_id') or latest != item['assessment_id']:
            return True
    return False
