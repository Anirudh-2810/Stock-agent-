import { useRef, useEffect } from 'react';
import { useChart } from '../hooks/useChart';
import type { ChartData } from '../hooks/useChart';

interface ChartProps {
  data?: ChartData[];
  height?: number;
}

export function Chart({ data = [], height = 400 }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { setData } = useChart(containerRef);

  useEffect(() => {
    if (data.length > 0) {
      setData(data);
    }
  }, [data, setData]);

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div ref={containerRef} className="chart-container" style={{ height }} />
    </div>
  );
}