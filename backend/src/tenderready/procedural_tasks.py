"""Source-linked procedural work, never inferred completion or deadlines."""
from sqlalchemy import select
from .models import CorrectiveTask, SourceSpan, Assessment
from .check_planning import build_check_plan


def prepare_task(db, requirement, assessment_id):
    source = db.get(SourceSpan, requirement.source_span_id)
    plan = build_check_plan(requirement, source)
    if plan['kind'] != 'procedure':
        return None
    title = 'Tender action: ' + ' '.join(requirement.statement.split())[:220]
    existing = db.scalar(select(CorrectiveTask).join(Assessment, Assessment.id == CorrectiveTask.assessment_id).where(
        CorrectiveTask.workspace_id == requirement.workspace_id,
        Assessment.requirement_version_id == requirement.id, CorrectiveTask.title == title))
    if existing:
        return existing
    action = plan.get('action', {})
    instruction = action.get('instruction', 'Carry out the stated step and retain its completion record.')
    explanation = (f'{action.get("title", "Tender action")}\n{instruction}\n\n'
        f'Follow this tender instruction on page {source.page}:\n{requirement.statement}\n\n'
        'Carry out the stated step and retain its receipt, submitted document, or other completion record. '
        'Record what you did in the task comment. Check any conditions in the quoted clause before acting. '
        'Closing this task does not approve the evidence assessment. No due date has been inferred.\n'
        f'Source: /workspaces/{requirement.workspace_id}/documents/{source.document_version_id}/file#page={source.page}')
    task = CorrectiveTask(workspace_id=requirement.workspace_id, assessment_id=assessment_id,
        title=title, explanation=explanation, priority='medium')
    db.add(task); db.flush()
    return task
