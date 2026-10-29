/** Explicit offline fixture workflow. Every write uses the normal persisted API.
 * Never calls or substitutes for /analyze and never creates a model-run record.
 */
export const SAMPLE_SUPPLIER = 'Synthetic TenderReady Demo Supplier';
export type SampleWorkspace = {id:string;title:string;supplier_name:string;revision:number};
type Request = <T>(path:string, init?:RequestInit)=>Promise<T>;
type Requirement = {id:string;text:string};
type Assessment = {id:string;status:string};
type Snapshot = {changes:{classification:string;impacts?:{new_assessment:Assessment|null}[]}[]};
export class SampleWorkflowError extends Error {
  constructor(message:string, public workspace:SampleWorkspace|null) { super(message); }
}
export async function createSampleWorkflow(request:Request, progress:(message:string)=>void):Promise<SampleWorkspace> {
  let workspace:SampleWorkspace|null=null;
  const post=<T,>(path:string,body?:unknown)=>request<T>(path,{method:'POST',...(body?{body:JSON.stringify(body)}:{})});
  try {
    progress('Loading synthetic PDFs…');
    // Obtain all fixtures before creating any database records.
    const files=await Promise.all(['original-tender.pdf','datasheet-16gb.pdf','ram-amendment.pdf'].map(async name=>{
      const response=await fetch(`/samples/offline/${name}`);
      if(!response.ok)throw new Error(`Sample file unavailable: ${name}`);
      return {name,body:await response.blob()};
    }));
    workspace=await post<SampleWorkspace>('/workspaces',{title:'SAMPLE — RAM amendment: 16 to 32 GB',supplier_name:SAMPLE_SUPPLIER});
    const prefix=`/workspaces/${workspace.id}`;
    const upload=(index:number,path:string)=>request<{id:string}>(prefix+path,{method:'POST',headers:{'Content-Type':'application/pdf','X-Filename':files[index].name},body:files[index].body});
    const reviewer='SYNTHETIC DEMO — scripted review';
    progress('Uploading original tender and supplier evidence…');
    const original=await upload(0,'/documents');
    await upload(1,'/evidence?evidence_type=datasheet');
    const originalPath=`${prefix}/documents/${original.id}`;
    await post(originalPath+'/extract-labelled');
    const requirements=await request<Requirement[]>(originalPath+'/requirements');
    if(requirements.length!==2)throw new Error('Expected two labelled sample requirements. Inspect the saved workspace.');
    for(const req of requirements){
      const assessment=await post<Assessment>(`${prefix}/requirements/${req.id}/verify`,{coverage_confirmed:true,reviewer});
      if(assessment.status!=='supported')throw new Error('Original sample evidence was not supported. Inspect the finding.');
      await post(`${prefix}/assessments/${assessment.id}/reviews`,{action:'approved',reviewer,comment:'Synthetic scripted approval for this sample only. Original labelled model and threshold match. Not a real supplier review.'});
    }
    await post(originalPath+'/baseline',{coverage_confirmed:true,reviewer});
    progress('Applying the 32 GB amendment and checking dependencies…');
    const amendment=await upload(2,'/documents?kind=amendment');
    const amendmentPath=`${prefix}/documents/${amendment.id}`;
    await post(amendmentPath+'/extract-labelled');
    const payload={mode:'delta',coverage_confirmed:true,reviewer};
    const preview=await post<{fingerprint:string}>(amendmentPath+'/compare',payload);
    const result=await post<Snapshot>(amendmentPath+'/apply-amendment',{...payload,fingerprint:preview.fingerprint});
    if(!result.changes.some(c=>c.classification==='Modified'&&c.impacts?.some(i=>i.new_assessment?.status==='conflicting')) || !result.changes.some(c=>c.classification==='Unchanged'))
      throw new Error('The sample did not produce the expected RAM conflict and unchanged storage requirement. Inspect saved findings.');
    return workspace;
  } catch(error) {
    throw new SampleWorkflowError(error instanceof Error?error.message:'Sample workflow failed.',workspace);
  }
}
