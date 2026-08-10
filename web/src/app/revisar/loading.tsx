import { Skeleton } from "@/components/ui/skeleton";

export default function CargandoRevisar() {
  return (
    <>
      <Skeleton className="h-9 w-48" />
      <Skeleton className="mt-4 h-16 w-full" />
      <Skeleton className="mt-4 h-14 w-full" />
      <div className="mt-5 grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
        <div className="rounded-sm border border-border bg-card p-5">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="mt-4 h-9 w-full" />
          <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-5">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    </>
  );
}
