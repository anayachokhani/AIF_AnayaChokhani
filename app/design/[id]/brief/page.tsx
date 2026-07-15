import { ExportBriefClient } from "../../../components/ExportBriefClient";

type DesignBriefPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ revision?: string | string[] }>;
};

export default async function DesignBriefPage({ params, searchParams }: DesignBriefPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const revisionId = Array.isArray(query.revision) ? query.revision[0] : query.revision;
  return <ExportBriefClient designId={id} revisionId={revisionId} />;
}
