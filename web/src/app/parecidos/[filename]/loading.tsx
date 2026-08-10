import { Skeleton } from "@/components/ui/skeleton";

export default function CargandoParecidos() {
  return (
    <>
      <Skeleton className="h-9 w-64" />
      <Skeleton className="mt-3 h-5 w-full max-w-lg" />
      <div className="mt-6 rounded-sm border border-border bg-card p-5">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="mt-4 h-9 w-full" />
      </div>
      <div className="mt-10 grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-64 w-full" />
        ))}
      </div>
    </>
  );
}
