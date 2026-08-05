"use client";

import { Boxes, HardDrive, TrendingUp, Workflow } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingNotice } from "@/components/common/loading-notice";
import { useJobStats } from "@/lib/queries";

export function StatsCards() {
  const { data: stats, isLoading, error, refetch } = useJobStats();

  // Surface fetch failures inline rather than rendering zeros — that would lie
  // about the bucket state when really the API is just unreachable.
  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  const cards = [
    { title: "Processing Jobs", value: stats?.total_jobs ?? 0, icon: Workflow },
    { title: "Source Data (raw/)", value: stats?.source_bytes_human ?? "0 B", icon: Boxes },
    { title: "Artifacts on B2", value: stats?.artifact_count ?? 0, icon: HardDrive },
    {
      title: "Write Amplification",
      value: stats ? `${stats.write_amplification}×` : "0×",
      icon: TrendingUp,
    },
  ];

  return (
    <>
      {/* Stats scan the jobs/ and raw/ prefixes, which can take a moment on a
          large bucket. State that in words rather than showing blank cards. */}
      {isLoading && <LoadingNotice className="mb-3" subject="pipeline metrics" />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card, i) => (
          <Card
            key={card.title}
            className={`card-hover animate-fade-in-up stagger-${i + 1}`}
          >
            <CardHeader className="flex flex-row items-center justify-between pt-4 pb-2 px-4 space-y-0">
              <CardTitle className="text-xs font-semibold text-muted-foreground">
                {card.title}
              </CardTitle>
              <div className="stat-icon-wrap">
                <card.icon className="h-4 w-4" />
              </div>
            </CardHeader>
            <CardContent className="pb-5 px-4">
              {isLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <div className="stat-value">{card.value}</div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
