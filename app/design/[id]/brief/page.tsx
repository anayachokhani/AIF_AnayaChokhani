import { ExportBriefClient } from "../../../components/ExportBriefClient";

type DesignBriefPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    revision_id?: string | string[];
    revision?: string | string[];
  }>;
};

export default async function DesignBriefPage({ params, searchParams }: DesignBriefPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const requestedRevision = query.revision_id ?? query.revision;
  const revisionId = Array.isArray(requestedRevision) ? requestedRevision[0] : requestedRevision;
  return <ExportBriefClient key={`${id}:${revisionId ?? "latest"}`} designId={id} revisionId={revisionId} />;
}
