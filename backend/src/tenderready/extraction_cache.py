"""Exact-source batch checkpoints: never published or approved on their own."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import time

from sqlalchemy import select
from .models import ExtractionBatchCache, ModelRun, ModelRunContext
from .nebius import ExtractionResult, IntegrationError, SourceInput, validate_requirement_sources

# Bump when prompt, interpretation or checkpoint contract changes.
CONTRACT_VERSION = 'contextual-line-refs-v1'


def batch_source(span, batch):
    context = '\n'.join(c.text for c in batch.contexts) or None
    return SourceInput(source_id=span.id, text=span.text[batch.start:batch.end], context=context)


def batch_fingerprint(span, batch, settings):
    # No credentials or authentication settings belong in fingerprints or rows.
    payload = {'contract': CONTRACT_VERSION, 'source_span': span.id,
        'start': batch.start, 'end': batch.end, 'source': batch_source(span, batch).model_dump(),
        'contexts': [{'kind':c.kind,'start':c.start,'end':c.end,'text':c.text} for c in batch.contexts],
        'model': settings.nebius_model, 'endpoint': settings.nebius_base_url,
        'thinking': settings.nebius_enable_thinking, 'json_mode': settings.nebius_json_mode,
        'format': settings.nebius_extraction_format,
        'max_output_tokens': settings.nebius_max_output_tokens}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


async def extract_checkpoint(analysis_id, span, batch, sessions, settings, client):
    """Return validated result, originating model-run ID, and cache-hit flag."""
    source = batch_source(span,batch)
    fingerprint = batch_fingerprint(span,batch,settings)
    with sessions() as db:
        cached = db.scalar(select(ExtractionBatchCache).where(
            ExtractionBatchCache.workspace_id == span.workspace_id,
            ExtractionBatchCache.analysis_id == analysis_id,
            ExtractionBatchCache.source_span_id == span.id,
            ExtractionBatchCache.fingerprint == fingerprint))
        if cached:
            try:
                result = ExtractionResult.model_validate(cached.result['extraction'])
                for req in result.batch.requirements:
                    validate_requirement_sources(req,{source.source_id:source.text})
            except (ValueError, KeyError, TypeError):
                raise IntegrationError('Stored extraction checkpoint failed source validation; review the analysis.', 'invalid_checkpoint') from None
            return result, cached.model_run_id, True
    started_at = datetime.now(timezone.utc)
    start = time.monotonic()
    try:
        result = await client.extract_requirements([source])
    except (Exception, asyncio.CancelledError) as error:
        code = error.code if isinstance(error, IntegrationError) else 'interrupted' if isinstance(error, asyncio.CancelledError) else 'analysis_failed'
        usage = getattr(error,'usage',None)
        with sessions.begin() as db:
            run = ModelRun(workspace_id=span.workspace_id, model=settings.nebius_model,
                operation='tender_requirement_extraction',duration_ms=round((time.monotonic()-start)*1000),outcome='failed',
                input_tokens=usage.input_tokens if usage else None, output_tokens=usage.output_tokens if usage else None)
            db.add(run);db.flush()
            db.add(ModelRunContext(workspace_id=span.workspace_id,model_run_id=run.id,analysis_id=analysis_id,
                source_span_id=span.id,started_at=started_at,completed_at=datetime.now(timezone.utc),
                attempts=usage.attempts if usage else None,error_code=code))
        raise
    with sessions.begin() as db:
        run=ModelRun(workspace_id=span.workspace_id,model=result.usage.model,
            operation='tender_requirement_extraction',input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,duration_ms=result.usage.duration_ms,outcome='succeeded')
        db.add(run);db.flush()
        db.add(ModelRunContext(workspace_id=span.workspace_id,model_run_id=run.id,analysis_id=analysis_id,
            source_span_id=span.id,started_at=started_at,completed_at=datetime.now(timezone.utc),attempts=result.usage.attempts))
        db.add(ExtractionBatchCache(workspace_id=span.workspace_id,analysis_id=analysis_id,
            source_span_id=span.id,model_run_id=run.id,fingerprint=fingerprint,
            result={'extraction':result.model_dump(), 'start_offset':span.start_offset+batch.start,
                    'end_offset':span.start_offset+batch.end,'contract':CONTRACT_VERSION}))
    return result, run.id, False


def source_context(span,batch):
    return [{'kind':c.kind,'text':c.text,'page':span.page,'source_document_id':span.document_version_id,
        'source_url':f'/workspaces/{span.workspace_id}/documents/{span.document_version_id}/file#page={span.page}',
        'start_offset':span.start_offset+c.start,'end_offset':span.start_offset+c.end} for c in batch.contexts]
