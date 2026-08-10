import { Skeleton } from "@/components/ui/skeleton";

export default function CargandoBiblioteca() {
  return (
    <>
      <Skeleton className="h-9 w-60" />
      <Skeleton className="mt-3 h-5 w-full max-w-lg" />
      <div className="mt-6 flex gap-3">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-14 w-40" />
        ))}
      </div>
      <div className="mt-5 grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="overflow-hidden rounded-sm border border-border bg-card">
            <Skeleton className="h-40 w-full rounded-none" />
            <div className="flex flex-col gap-2.5 p-3.5">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
