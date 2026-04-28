"use client";

import { useState } from "react";

import type { ChartType } from "@/lib/charts";
import type { DetailChartRunPoint } from "@/lib/songs";

interface ChartRunVisualizationProps {
  chartType: ChartType;
  points: DetailChartRunPoint[];
  title: string;
}

const HOT_100_TICKS = [1, 25, 50, 75, 100];
const BILLBOARD_200_TICKS = [1, 50, 100, 150, 200];

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function ChartRunVisualization({
  chartType,
  points,
  title,
}: ChartRunVisualizationProps) {
  const [expanded, setExpanded] = useState(false);

  if (points.length < 2) {
    return null;
  }

  const ticks =
    chartType === "hot-100" ? HOT_100_TICKS : BILLBOARD_200_TICKS;
  const yMax = chartType === "hot-100" ? 100 : 200;
  const width = 720;
  const height = 260;
  const padding = { top: 20, right: 24, bottom: 28, left: 40 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const plotted = points.map((point, index) => {
    const x =
      padding.left +
      (points.length === 1 ? 0 : (innerWidth * index) / (points.length - 1));
    const y = padding.top + ((point.rank - 1) / (yMax - 1)) * innerHeight;

    return {
      ...point,
      x,
      y,
    };
  });

  const path = plotted.map((point) => `${point.x},${point.y}`).join(" ");
  const peakPoint = plotted.reduce((best, point) =>
    point.rank < best.rank ? point : best,
  );

  return (
    <section className="mt-6">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        className="text-[12px] font-[600] leading-[1.45] text-[#0A0A0A] transition-colors hover:text-[#C8102E]"
      >
        {expanded ? "▼" : "▶"} Chart Run Visualization
      </button>

      {expanded ? (
        <div className="mt-3 overflow-hidden rounded border border-black/10 bg-white px-3 py-4">
          <div className="mb-3 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
            {title}
          </div>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-auto w-full"
            role="img"
            aria-label={`${title} chart run`}
          >
            {ticks.map((tick) => {
              const y = padding.top + ((tick - 1) / (yMax - 1)) * innerHeight;
              return (
                <g key={tick}>
                  <line
                    x1={padding.left}
                    y1={y}
                    x2={width - padding.right}
                    y2={y}
                    stroke="rgba(0, 0, 0, 0.08)"
                    strokeWidth="1"
                  />
                  <text
                    x={padding.left - 8}
                    y={y + 4}
                    textAnchor="end"
                    fontSize="10"
                    fill="#888888"
                  >
                    {tick}
                  </text>
                </g>
              );
            })}

            <polyline
              fill="none"
              stroke="#C8102E"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
              points={path}
            />

            <circle cx={peakPoint.x} cy={peakPoint.y} r="4" fill="#C8102E" />
            <text
              x={peakPoint.x + 8}
              y={Math.max(padding.top + 12, peakPoint.y - 8)}
              fontSize="10"
              fontWeight="600"
              fill="#C8102E"
            >
              #{peakPoint.rank}
            </text>

            <text
              x={padding.left}
              y={height - 6}
              fontSize="10"
              fill="#888888"
            >
              {formatDate(points[0].chart_date)}
            </text>
            <text
              x={width - padding.right}
              y={height - 6}
              textAnchor="end"
              fontSize="10"
              fill="#888888"
            >
              {formatDate(points[points.length - 1].chart_date)}
            </text>
          </svg>
        </div>
      ) : null}
    </section>
  );
}
