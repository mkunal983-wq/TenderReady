import {workspaceHref} from './workspaceRoutes';
export function SampleGuide({workspaceId}:{workspaceId:string}) {
  return <details className="panel sample-guide"><summary>Synthetic sample workspace · No AI inference</summary>
    <p>This sample uses real PDFs, database records and deterministic checks. Its scripted approvals are labelled SYNTHETIC DEMO. No Nemotron call or official verification is claimed.</p>
    <ol><li>Open <a href={workspaceHref(workspaceId,'requirements')}>Requirements</a> and review RAM: the amended minimum is 32 GB, while the original datasheet states 16 GB.</li>
    <li>Open <a href={workspaceHref(workspaceId,'amendments')}>Amendments</a> to compare versions. The RAM approval is reopened; storage remains unchanged.</li>
    <li>Download the <a href="/samples/offline/replacement-32gb.pdf" download>32 GB replacement datasheet</a>. In <a href={workspaceHref(workspaceId,'evidence')}>Evidence Library</a>, choose the original datasheet under “Replace an existing document”, then upload this PDF.</li>
    <li>Rerun RAM and storage verification, inspect all criteria, confirm coverage, and approve findings with your reviewer name and comment. Replacement evidence conservatively reopens all checks using that evidence category.</li>
    <li>Resolve corrective <a href={workspaceHref(workspaceId,'tasks')}>Tasks</a>, then download both CSV files from <a href={workspaceHref(workspaceId,'export')}>Export</a>. Old findings and approvals remain in history.</li></ol>
    <p>Extra negative test: <a href="/samples/offline/wrong-model.pdf" download>wrong-model datasheet</a>. Uploading it as additional current evidence should produce a model conflict, even though it has 32 GB RAM.</p>
    <p>For real AI testing later, create a fresh workspace and upload your tender after configuring the server-side provider key. This sample is never silently converted to an AI run.</p>
  </details>;
}
