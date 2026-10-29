/** Exact surrounding source text carried separately from the requirement clause. */
export type SourceContext = {
  text: string;
  page: number;
  source_document_id: string;
  source_url: string;
};
