import { RecordingView } from "@/components/RecordingView";

export default async function RecordingPage({ params }: PageProps<"/recordings/[id]">) {
  const { id } = await params;
  return <RecordingView id={id} />;
}
