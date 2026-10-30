import { useEffect, useRef, useCallback, type RefObject } from 'react';
import { createChart, IChartApi, ISeriesApi, ChartOptions, Time } from 'lightweight-charts';

export interface ChartData {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export function useChart(containerRef: RefObject<HTMLDivElement>) {
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 400,
      layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#1f2937',
      },
      grid: {
        vertLines: { color: '#e5e7eb' },
        horzLines: { color: '#e5e7eb' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#e5e7eb',
      },
      timeScale: {
        borderColor: '#e5e7eb',
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
      },
    } as ChartOptions);

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#16a34a',
      downColor: '#dc2626',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
    });

    const volumeSeries = chart.addHistogramSeries({
      color: '#9ca3af',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      base: 0,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (chartRef.current && container) {
        chartRef.current.applyOptions({
          width: container.clientWidth,
          height: 400,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      chart.remove();
      chartRef.current = null;
    };
  }, [containerRef]);

  const setData = useCallback((data: ChartData[]) => {
    if (candleSeriesRef.current && volumeSeriesRef.current) {
      candleSeriesRef.current.setData(data.map(d => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      })));
      volumeSeriesRef.current.setData(data.map(d => ({
        time: d.time,
        value: d.volume || 0,
        color: d.close >= d.open ? '#16a34a' : '#dc2626',
      })));
    }
  }, []);

  const updateLastBar = useCallback((data: ChartData) => {
    if (candleSeriesRef.current && volumeSeriesRef.current) {
      candleSeriesRef.current.update({
        time: data.time,
        open: data.open,
        high: data.high,
        low: data.low,
        close: data.close,
      });
      volumeSeriesRef.current.update({
        time: data.time,
        value: data.volume || 0,
        color: data.close >= data.open ? '#16a34a' : '#dc2626',
      });
    }
  }, []);

  return { setData, updateLastBar };
}