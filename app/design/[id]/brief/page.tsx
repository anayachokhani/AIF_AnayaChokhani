import { ExportBriefClient } from "../../../components/ExportBriefClient";

type DesignBriefPageProps = {
  params: Promise<{ id: string }>;
};

export default async function DesignBriefPage({ params }: DesignBriefPageProps) {
  const { id } = await params;
  return <ExportBriefClient designId={id} />;
}
