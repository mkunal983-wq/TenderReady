import {workspaceHref} from './workspaceRoutes';
export function SampleGuide({workspaceId}:{workspaceId:string}) {
  return <details className="panel sample-guide"><summary>Sample workspace · AI not used</summary>
    <p>This demo uploads sample PDFs, saves results, and checks values using fixed rules. Automatic sample approvals are marked SYNTHETIC DEMO. It does not use Nemotron or check documents with an official authority.</p>
    <ol><li>Open <a href={workspaceHref(workspaceId,'requirements')}>Requirements</a> and check RAM: the updated tender asks for at least 32 GB, but the original product document says 16 GB.</li>
    <li>Open <a href={workspaceHref(workspaceId,'amendments')}>Amendments</a> to compare versions. The RAM approval needs a new review; the storage requirement stays the same.</li>
    <li>Download the <a href="/samples/offline/replacement-32gb.pdf" download>32 GB replacement datasheet</a>. In <a href={workspaceHref(workspaceId,'evidence')}>Evidence Library</a>, choose the original datasheet under “Replace an existing document”, then upload this PDF.</li>
    <li>Run the RAM and storage checks again. Make sure the checks cover the full requirement, then add your name and comment to approve the result. Replacing a document makes all checks that use that document type need a new review.</li>
    <li>Complete the <a href={workspaceHref(workspaceId,'tasks')}>Tasks</a>, then download both CSV files from <a href={workspaceHref(workspaceId,'export')}>Export</a>. Earlier results and approvals stay in the history.</li></ol>
    <p>Try a document with the wrong product model: <a href="/samples/offline/wrong-model.pdf" download>wrong-model datasheet</a>. Add it to the evidence library to test whether the app catches the wrong model, even though it has 32 GB RAM.</p>
    <p>To test real AI, first set up the AI key securely on the server. Then create a new workspace and upload your tender. This demo stays separate from real AI results.</p>
  </details>;
}
