import { RecordingList } from "@/components/RecordingList";
import { Uploader } from "@/components/Uploader";

export default function Home() {
  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-2xl font-semibold">Upload audio</h1>
        <p className="mt-1 text-zinc-600">
          Any length. It is transcribed with Gnani ASR and summarised by Gemini.
        </p>
        <div className="mt-4">
          <Uploader />
        </div>
      </section>
      <section>
        <h2 className="text-lg font-semibold">Past uploads</h2>
        <div className="mt-3">
          <RecordingList />
        </div>
      </section>
    </div>
  );
}
