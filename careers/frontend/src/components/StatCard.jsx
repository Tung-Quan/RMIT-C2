export function StatCard({ icon: Icon, label, value, tone = "zinc" }) {
  const toneClasses = {
    zinc: "bg-zinc-100 text-zinc-700",
    sky: "bg-sky-50 text-sky-700",
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700"
  };

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-zinc-500">{label}</p>
          <p className="mt-2 text-3xl font-semibold text-zinc-900">{value}</p>
        </div>
        {Icon && (
          <div className={`rounded-lg p-3 ${toneClasses[tone] || toneClasses.zinc}`}>
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
    </div>
  );
}
