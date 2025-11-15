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
  binance_event_latency_ms: number;
  binance_rtt_latency_ms: number;
  btcturk_event_latency_ms: number;
  btcturk_rtt_latency_ms: number;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get('limit') ? parseInt(searchParams.get('limit')!) : null;
    
    // CSV dosyasını oku (üst dizinden)
    const csvPath = join(process.cwd(), '..', 'spread_log.csv');
    console.log('Reading CSV from:', csvPath);
    
    const csvContent = await readFile(csvPath, 'utf-8');
    console.log('CSV content length:', csvContent.length);
    
    // CSV'yi parse et - header var
    const parsed = Papa.parse<SpreadData>(csvContent, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
    });
    
    console.log('Parsed rows:', parsed.data.length);
    console.log('Sample row:', parsed.data[0]);
    
    // Tüm veriyi filtrele (istatistikler için)
    const allData = parsed.data.filter((row: SpreadData) => 
      row && 
      typeof row.spread_pct === 'number' && 
      Number.isFinite(row.spread_pct)
    );
    
    // Grafik için sadece son N tanesini al
    const displayData = limit ? allData.slice(-limit) : allData;
    
    console.log('Total data length:', allData.length);
    console.log('Display data length:', displayData.length);
    
    if (allData.length === 0) {
      return NextResponse.json({
        data: [],
        stats: {
          avgSpread: '0',
          maxSpread: '0',
          minSpread: '0',
          avgSpreadTry: '0',
          maxSpreadTry: '0',
          minSpreadTry: '0',
          avgBinanceLatency: '0',
          avgBtcturkLatency: '0',
          dataPoints: 0,
          lastUpdate: 'N/A',
        },
      });
    }
    
    // İstatistikleri TÜM veriden hesapla (daha doğru max/min için)
    const spreadValues = allData.map(d => d.spread_pct).filter(v => Number.isFinite(v));
    const avgSpread = spreadValues.reduce((a, b) => a + b, 0) / spreadValues.length;
    const maxSpread = Math.max(...spreadValues);
    const minSpread = Math.min(...spreadValues);
    
    // TRY cinsinden max ve min değerler (TÜM veriden)
    const spreadTryValues = allData.map(d => d.spread_try).filter(v => Number.isFinite(v));
    const avgSpreadTry = spreadTryValues.length > 0 
      ? spreadTryValues.reduce((a, b) => a + b, 0) / spreadTryValues.length 
      : 0;
    // Pozitif spreadler arasından max (en karlı)
    const positiveSpreadTry = spreadTryValues.filter(v => v > 0);
    const maxSpreadTry = positiveSpreadTry.length > 0 ? Math.max(...positiveSpreadTry) : 0;
    // Negatif spreadler arasından min (en zararlı)
    const negativeSpreadTry = spreadTryValues.filter(v => v < 0);
    const minSpreadTry = negativeSpreadTry.length > 0 ? Math.min(...negativeSpreadTry) : 0;
    
    // Event latency kullan (daha gerçekçi, RTT çok yüksek)
    const binanceLatencyValues = allData.map(d => d.binance_event_latency_ms || d.binance_rtt_latency_ms).filter(v => Number.isFinite(v));
    const avgBinanceLatency = binanceLatencyValues.length > 0 
      ? binanceLatencyValues.reduce((a, b) => a + b, 0) / binanceLatencyValues.length 
      : 0;
    
    const btcturkLatencyValues = allData.map(d => d.btcturk_event_latency_ms || d.btcturk_rtt_latency_ms).filter(v => Number.isFinite(v));
    const avgBtcturkLatency = btcturkLatencyValues.length > 0 
      ? btcturkLatencyValues.reduce((a, b) => a + b, 0) / btcturkLatencyValues.length 
      : 0;
    
    return NextResponse.json({
      data: displayData, // Grafik için sadece son N tanesini gönder
      stats: {
        avgSpread: Number.isFinite(avgSpread) ? avgSpread.toFixed(6) : '0',
        maxSpread: Number.isFinite(maxSpread) ? maxSpread.toFixed(6) : '0',
        minSpread: Number.isFinite(minSpread) ? minSpread.toFixed(6) : '0',
        avgSpreadTry: Number.isFinite(avgSpreadTry) ? avgSpreadTry.toFixed(2) : '0',
        maxSpreadTry: Number.isFinite(maxSpreadTry) ? maxSpreadTry.toFixed(2) : '0',
        minSpreadTry: Number.isFinite(minSpreadTry) ? minSpreadTry.toFixed(2) : '0',
        avgBinanceLatency: Number.isFinite(avgBinanceLatency) ? avgBinanceLatency.toFixed(2) : '0',
        avgBtcturkLatency: Number.isFinite(avgBtcturkLatency) ? avgBtcturkLatency.toFixed(2) : '0',
        dataPoints: allData.length, // Toplam veri sayısı
        lastUpdate: displayData[displayData.length - 1]?.timestamp || 'N/A',
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
