'use client';

import { useState, useEffect } from 'react';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Activity, Zap, Clock, RefreshCw } from 'lucide-react';

interface SpreadData {
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

interface Stats {
  avgSpread: string;
  maxSpread: string;
  minSpread: string;
  avgSpreadTry: string;
  maxSpreadTry: string;
  minSpreadTry: string;
  avgBinanceLatency: string;
  avgBtcturkLatency: string;
  dataPoints: number;
  lastUpdate: string;
}

export default function Dashboard() {
  const [data, setData] = useState<SpreadData[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [usdtTryRate, setUsdtTryRate] = useState<number>(0);

  const fetchUsdtTryRate = async () => {
    try {
      const response = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=USDTTRY');
      const result = await response.json();
      const rate = parseFloat(result.price);
      if (rate > 0) {
        setUsdtTryRate(rate);
      }
    } catch (error) {
      console.error('Error fetching USDT/TRY rate:', error);
    }
  };

  const fetchData = async () => {
    try {
      // Son 500 veri noktası (yaklaşık 15-20 dakika)
      const response = await fetch('/api/spread-data?limit=500');
      const result = await response.json();
      setData(result.data);
      setStats(result.stats);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    
    const loadData = async () => {
      if (mounted) {
        await fetchData();
        await fetchUsdtTryRate();
      }
    };
    
    void loadData();
    
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        void fetchData();
        void fetchUsdtTryRate();
      }, 2000); // Her 2 saniyede bir güncelle
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('tr-TR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const chartData = data.map((item) => ({
    time: formatTime(item.timestamp),
    spread: Number.isFinite(item.spread_pct) ? parseFloat(item.spread_pct.toFixed(6)) : 0,
    binanceLatency: Number.isFinite(item.binance_event_latency_ms) ? item.binance_event_latency_ms : (Number.isFinite(item.binance_rtt_latency_ms) ? item.binance_rtt_latency_ms : 0),
    btcturkLatency: Number.isFinite(item.btcturk_event_latency_ms) ? item.btcturk_event_latency_ms : (Number.isFinite(item.btcturk_rtt_latency_ms) ? item.btcturk_rtt_latency_ms : 0),
  }));

  if (loading) {
    return (
      <div className="min-h-screen bg-linear-to-br from-gray-900 via-gray-800 to-gray-900 flex items-center justify-center">
        <div className="text-white text-2xl flex items-center gap-3">
          <RefreshCw className="animate-spin" size={32} />
          <span>Veriler yükleniyor...</span>
        </div>
      </div>
    );
  }

  const latestData = data[data.length - 1];
  const spreadTrend = data.length > 1 ? 
    data[data.length - 1].spread_pct - data[data.length - 2].spread_pct : 0;

  return (
    <div className="min-h-screen bg-linear-to-br from-gray-900 via-gray-800 to-gray-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold text-white mb-2 flex items-center gap-3">
              <Activity className="text-blue-500" size={40} />
              Arbitraj Spread Monitör
            </h1>
            <p className="text-gray-400">
              Binance - BTCTurk BTC/USDT Fiyat Farkı
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-6 py-3 rounded-lg font-semibold flex items-center gap-2 transition-all ${
                autoRefresh
                  ? 'bg-green-600 hover:bg-green-700 text-white'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              <RefreshCw className={autoRefresh ? 'animate-spin' : ''} size={20} />
              {autoRefresh ? 'Otomatik Güncelleme' : 'Manuel Mod'}
            </button>
            <button
              onClick={fetchData}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-all"
            >
              Yenile
            </button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-linear-to-br from-blue-500/10 to-blue-600/20 backdrop-blur-lg rounded-xl p-6 border border-blue-500/30">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-gray-300 text-sm font-medium">Anlık Spread</h3>
              {spreadTrend > 0 ? (
                <TrendingUp className="text-green-500" size={24} />
              ) : (
                <TrendingDown className="text-red-500" size={24} />
              )}
            </div>
            <p className="text-3xl font-bold text-white mb-1">
              {latestData ? latestData.spread_pct.toFixed(6) : '0'}%
            </p>
            <p className="text-gray-400 text-sm">
              ${latestData?.spread_try?.toFixed(2) ?? '0'} USDT
              {usdtTryRate > 0 && latestData?.spread_try && (
                <span className="block text-gray-500 text-xs mt-1">
                  (₺{(latestData.spread_try * usdtTryRate).toFixed(2)} TRY)
                </span>
              )}
            </p>
            <div className="flex justify-between mt-3 pt-3 border-t border-blue-500/20">
              <div className="text-left">
                <span className="text-xs text-green-400 block">
                  Max: ${stats?.maxSpreadTry ?? '0'}
                </span>
                {usdtTryRate > 0 && stats?.maxSpreadTry && parseFloat(stats.maxSpreadTry) !== 0 && (
                  <span className="text-xs text-gray-600">
                    ₺{(parseFloat(stats.maxSpreadTry) * usdtTryRate).toFixed(2)}
                  </span>
                )}
              </div>
              <div className="text-right">
                <span className="text-xs text-red-400 block">
                  Min: ${stats?.minSpreadTry ?? '0'}
                </span>
                {usdtTryRate > 0 && stats?.minSpreadTry && parseFloat(stats.minSpreadTry) !== 0 && (
                  <span className="text-xs text-gray-600">
                    ₺{(parseFloat(stats.minSpreadTry) * usdtTryRate).toFixed(2)}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="bg-linear-to-br from-green-500/10 to-green-600/20 backdrop-blur-lg rounded-xl p-6 border border-green-500/30">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-gray-300 text-sm font-medium">Ortalama Spread</h3>
              <Activity className="text-green-500" size={24} />
            </div>
            <p className="text-3xl font-bold text-white mb-1">
              {stats ? parseFloat(stats.avgSpread).toFixed(6) : '0'}%
            </p>
            <p className="text-gray-400 text-sm">
              ${stats?.avgSpreadTry ?? '0'} USDT
              {usdtTryRate > 0 && stats?.avgSpreadTry && parseFloat(stats.avgSpreadTry) !== 0 && (
                <span className="block text-gray-500 text-xs mt-1">
                  (₺{(parseFloat(stats.avgSpreadTry) * usdtTryRate).toFixed(2)} TRY)
                </span>
              )}
            </p>
          </div>

          <div className="bg-linear-to-br from-purple-500/10 to-purple-600/20 backdrop-blur-lg rounded-xl p-6 border border-purple-500/30">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-gray-300 text-sm font-medium">Binance Gecikmesi</h3>
              <Zap className="text-purple-500" size={24} />
            </div>
            <p className="text-3xl font-bold text-white mb-1">
              {(latestData?.binance_event_latency_ms || latestData?.binance_rtt_latency_ms)?.toFixed(1) ?? '0'}ms
            </p>
            <p className="text-gray-400 text-sm">
              Ort: {stats?.avgBinanceLatency ?? '0'}ms
            </p>
          </div>

          <div className="bg-linear-to-br from-orange-500/10 to-orange-600/20 backdrop-blur-lg rounded-xl p-6 border border-orange-500/30">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-gray-300 text-sm font-medium">BTCTurk Gecikmesi</h3>
              <Clock className="text-orange-500" size={24} />
            </div>
            <p className="text-3xl font-bold text-white mb-1">
              {(latestData?.btcturk_event_latency_ms || latestData?.btcturk_rtt_latency_ms)?.toFixed(1) ?? '0'}ms
            </p>
            <p className="text-gray-400 text-sm">
              Ort: {stats?.avgBtcturkLatency ?? '0'}ms
            </p>
          </div>
        </div>

        {/* Spread Chart */}
        <div className="bg-gray-800/50 backdrop-blur-lg rounded-xl p-6 border border-gray-700">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
            <TrendingUp className="text-blue-500" size={28} />
            Spread Yüzdesi (%)
          </h2>
          <ResponsiveContainer width="100%" height={400}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="spreadGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="time" 
                stroke="#9ca3af" 
                tick={{ fill: '#9ca3af' }}
                angle={-45}
                textAnchor="end"
                height={80}
              />
              <YAxis stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#fff',
                }}
                formatter={(value: number) => {
                  if (typeof value === 'number' && Number.isFinite(value)) {
                    return value.toFixed(4);
                  }
                  return '0';
                }}
              />
              <Area
                type="monotone"
                dataKey="spread"
                stroke="#3b82f6"
                strokeWidth={3}
                fillOpacity={1}
                fill="url(#spreadGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Latency Comparison Chart */}
        <div className="bg-gray-800/50 backdrop-blur-lg rounded-xl p-6 border border-gray-700">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
            <Zap className="text-purple-500" size={28} />
            API Gecikme Karşılaştırması (ms)
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="time" 
                stroke="#9ca3af" 
                tick={{ fill: '#9ca3af' }}
                angle={-45}
                textAnchor="end"
                height={80}
              />
              <YAxis stroke="#9ca3af" tick={{ fill: '#9ca3af' }} />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#fff',
                }}
                formatter={(value: number) => {
                  if (typeof value === 'number' && Number.isFinite(value)) {
                    return value.toFixed(2) + 'ms';
                  }
                  return '0ms';
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="binanceLatency"
                stroke="#a855f7"
                strokeWidth={2}
                dot={false}
                name="Binance"
              />
              <Line
                type="monotone"
                dataKey="btcturkLatency"
                stroke="#fb923c"
                strokeWidth={2}
                dot={false}
                name="BTCTurk"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Live Prices */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-linear-to-br from-cyan-500/10 to-cyan-600/20 backdrop-blur-lg rounded-xl p-6 border border-cyan-500/30">
            <h3 className="text-xl font-bold text-white mb-4">Binance Fiyatları (USDT)</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-300">Alış (Bid):</span>
                <div className="text-right">
                  <span className="text-2xl font-bold text-green-400 block">
                    ${latestData?.binance_bid?.toLocaleString('en-US') ?? '0'}
                  </span>
                  {usdtTryRate > 0 && latestData?.binance_bid && (
                    <span className="text-xs text-gray-500">
                      ≈ ₺{(latestData.binance_bid * usdtTryRate).toLocaleString('tr-TR', {maximumFractionDigits: 0})}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-300">Satış (Ask):</span>
                <div className="text-right">
                  <span className="text-2xl font-bold text-red-400 block">
                    ${latestData?.binance_ask?.toLocaleString('en-US') ?? '0'}
                  </span>
                  {usdtTryRate > 0 && latestData?.binance_ask && (
                    <span className="text-xs text-gray-500">
                      ≈ ₺{(latestData.binance_ask * usdtTryRate).toLocaleString('tr-TR', {maximumFractionDigits: 0})}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="bg-linear-to-br from-yellow-500/10 to-yellow-600/20 backdrop-blur-lg rounded-xl p-6 border border-yellow-500/30">
            <h3 className="text-xl font-bold text-white mb-4">BTCTurk Fiyatları (USDT)</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-300">Alış (Bid):</span>
                <div className="text-right">
                  <span className="text-2xl font-bold text-green-400 block">
                    ${latestData?.btcturk_bid?.toLocaleString('en-US') ?? '0'}
                  </span>
                  {usdtTryRate > 0 && latestData?.btcturk_bid && (
                    <span className="text-xs text-gray-500">
                      ≈ ₺{(latestData.btcturk_bid * usdtTryRate).toLocaleString('tr-TR', {maximumFractionDigits: 0})}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-300">Satış (Ask):</span>
                <div className="text-right">
                  <span className="text-2xl font-bold text-red-400 block">
                    ${latestData?.btcturk_ask?.toLocaleString('en-US') ?? '0'}
                  </span>
                  {usdtTryRate > 0 && latestData?.btcturk_ask && (
                    <span className="text-xs text-gray-500">
                      ≈ ₺{(latestData.btcturk_ask * usdtTryRate).toLocaleString('tr-TR', {maximumFractionDigits: 0})}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-gray-500 text-sm py-4">
          <p>Son Güncelleme: {stats?.lastUpdate || 'N/A'}</p>
          <p className="mt-1">Toplam {stats?.dataPoints || 0} veri noktası</p>
        </div>
      </div>
    </div>
  );
}
