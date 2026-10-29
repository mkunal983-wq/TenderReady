"""Current draft revisions; immutable snapshots continue to use their exact IDs."""
from sqlalchemy import select
from .models import RequirementVersion, SourceSpan


def current_rows(db, wid, did, include_reference=False):
    rows=list(db.execute(select(RequirementVersion,SourceSpan).join(SourceSpan,
        SourceSpan.id==RequirementVersion.source_span_id).where(
            RequirementVersion.workspace_id==wid,SourceSpan.workspace_id==wid,
            SourceSpan.document_version_id==did).order_by(SourceSpan.page,SourceSpan.start_offset,
                                                        RequirementVersion.created_at,RequirementVersion.id)))
    superseded={r.supersedes_id for r,_ in rows if r.supersedes_id}
    return [(r,s) for r,s in rows if r.id not in superseded and not r.condition.get('canonicalized_from')
            and (include_reference or r.condition.get('disposition') not in {'reference','duplicate'})]
