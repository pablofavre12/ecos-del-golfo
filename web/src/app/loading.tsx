import { Skeleton } from "@/components/ui/skeleton";

export default function CargandoPanel() {
  return (
    <>
      <Skeleton className="h-9 w-72" />
      <Skeleton className="mt-3 h-5 w-full max-w-lg" />
      <div className="mt-7 grid grid-cols-1 gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-2 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex flex-col gap-2 bg-card p-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-10 w-full" />
          </div>
        ))}
      </div>
      <Skeleton className="mt-10 h-4 w-40" />
      <Skeleton className="mt-4 h-40 w-full max-w-md" />
    </>
  );
}
