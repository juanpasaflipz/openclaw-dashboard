import { CHANNELS } from "@/lib/constants";

const difficultyColor: Record<string, string> = {
  Easy: "bg-success/20 text-success",
  Medium: "bg-amber-500/20 text-amber-400",
  Hard: "bg-red-500/20 text-red-400",
};

export default function ChannelsGrid() {
  return (
    <section className="py-24 px-4" id="channels">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
          12 Channels, One Dashboard
        </h2>
        <p className="text-text-secondary text-center mb-16 max-w-2xl mx-auto">
          Deploy your agent everywhere your users are — from Telegram to
          Microsoft Teams.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {CHANNELS.map((channel) => (
            <div
              key={channel.name}
              className="glass-card p-5 flex flex-col items-center text-center gap-2"
            >
              <span className="text-3xl">{channel.icon}</span>
              <span className="font-medium text-sm">{channel.name}</span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${difficultyColor[channel.difficulty]}`}
              >
                {channel.difficulty}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
