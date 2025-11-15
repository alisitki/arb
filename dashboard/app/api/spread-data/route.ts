import { NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import { join } from 'path';
import Papa from 'papaparse';

export interface SpreadData {
  timestamp: string;
  binance_bid: number;
  binance_ask: number;
  btcturk_bid: number;
  btcturk_ask: number;
  spread_try: number;
  spread_pct: number;
  binance_latency_ms: number;
  btcturk_latency_ms: number;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '100');
    
    // CSV dosyasını oku (üst dizinden)
    const csvPath = join(process.cwd(), '..', 'spread_log.csv');
    console.log('Reading CSV from:', csvPath);
    
    const csvContent = await readFile(csvPath, 'utf-8');
    console.log('CSV content length:', csvContent.length);
    
    // CSV'yi parse et - header yok, manuel header ekle
    const parsed = Papa.parse<unknown>(csvContent, {
      header: false,
      dynamicTyping: true,
      skipEmptyLines: true,
    });
    
    console.log('Parsed rows:', parsed.data.length);
    console.log('Sample row:', parsed.data[0]);
    
    // Manuel olarak obje formatına çevir
    const data = parsed.data.slice(-limit).map((row: unknown) => {
      const rowArray = row as (string | number)[];
      return {
        timestamp: rowArray[0] as string,
        binance_bid: rowArray[1] as number,
        binance_ask: rowArray[2] as number,
        btcturk_bid: rowArray[3] as number,
        btcturk_ask: rowArray[4] as number,
        spread_try: rowArray[5] as number,
        spread_pct: rowArray[6] as number,
        binance_latency_ms: rowArray[7] as number,
        btcturk_latency_ms: rowArray[8] as number,
      };
    }).filter((row: SpreadData) => 
      row && 
      typeof row.spread_pct === 'number' && 
      Number.isFinite(row.spread_pct)
    );
    
    console.log('Filtered data length:', data.length);
    
    if (data.length === 0) {
      return NextResponse.json({
        data: [],
        stats: {
          avgSpread: '0',
          maxSpread: '0',
          minSpread: '0',
          avgBinanceLatency: '0',
          avgBtcturkLatency: '0',
          dataPoints: 0,
          lastUpdate: 'N/A',
        },
      });
    }
    
    // İstatistikleri hesapla
    const spreadValues = data.map(d => d.spread_pct).filter(v => Number.isFinite(v));
    const avgSpread = spreadValues.reduce((a, b) => a + b, 0) / spreadValues.length;
    const maxSpread = Math.max(...spreadValues);
    const minSpread = Math.min(...spreadValues);
    
    const latencyValues = data.map(d => d.binance_latency_ms).filter(v => Number.isFinite(v));
    const avgBinanceLatency = latencyValues.reduce((a, b) => a + b, 0) / latencyValues.length;
    
    const btcturkLatencyValues = data.map(d => d.btcturk_latency_ms).filter(v => Number.isFinite(v));
    const avgBtcturkLatency = btcturkLatencyValues.reduce((a, b) => a + b, 0) / btcturkLatencyValues.length;
    
    return NextResponse.json({
      data,
      stats: {
        avgSpread: Number.isFinite(avgSpread) ? avgSpread.toFixed(4) : '0',
        maxSpread: Number.isFinite(maxSpread) ? maxSpread.toFixed(4) : '0',
        minSpread: Number.isFinite(minSpread) ? minSpread.toFixed(4) : '0',
        avgBinanceLatency: Number.isFinite(avgBinanceLatency) ? avgBinanceLatency.toFixed(2) : '0',
        avgBtcturkLatency: Number.isFinite(avgBtcturkLatency) ? avgBtcturkLatency.toFixed(2) : '0',
        dataPoints: data.length,
        lastUpdate: data[data.length - 1]?.timestamp || 'N/A',
      },
    });
  } catch (error) {
    console.error('Error reading CSV:', error);
    return NextResponse.json(
      { error: 'Failed to read spread data' },
      { status: 500 }
    );
  }
}
