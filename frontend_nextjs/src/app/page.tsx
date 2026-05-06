import AudioRecorder from '@/components/AudioRecorder'

export default function Home() {
  return (
    <main className="min-h-screen p-8 bg-gray-50 flex items-center justify-center">
      <div className="max-w-4xl w-full mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight sm:text-5xl">
            XiaoYue Pronunciation Trainer
          </h1>
          <p className="mt-4 text-lg text-gray-500">
            Practice your English pronunciation and get instant AI feedback.
          </p>
        </div>
        <AudioRecorder />
      </div>
    </main>
  )
}
