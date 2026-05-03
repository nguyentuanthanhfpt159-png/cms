"use client";

import React, { useState, useEffect } from "react";
import { 
  Activity, 
  Package, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Cpu, 
  Camera, 
  ChevronRight, 
  BarChart3,
  PieChart as PieChartIcon,
  RefreshCw
} from "lucide-react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  Filler,
} from "chart.js";
import { Line, Doughnut } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface Stats {
  total: number;
  ok: number;
  ng: number;
  status: string;
  plc_connected: boolean;
  cam_connected: boolean;
  current_model: string;
  current_model_id: number;
  last_sync: string;
  error_types: Record<string, number>;
  recent_logs: [string, string, string, string, string][];
  hourly_data: number[];
  hourly_labels: string[];
}

export default function Dashboard() {
  const [data, setData] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const res = await fetch("/api/stats");
      const d = await res.json();
      setData(d);
      setLoading(false);
    } catch (err) {
      console.error("Fetch error:", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);

  const setModel = async (id: number) => {
    try {
      const res = await fetch(`/api/set_model/${id}`);
      const resData = await res.json();
      if (resData.status === "success") {
        alert("Đã đổi Model thành công!");
        fetchData();
      }
    } catch (err) {
      alert("Lỗi kết nối server");
    }
  };

  if (!data || (data as any).status === "error") return (
    <div className="flex h-screen flex-col items-center justify-center bg-[#0b0f19] text-slate-400 gap-4">
      <RefreshCw className="h-12 w-12 animate-spin text-blue-500" />
      {(data as any)?.status === "error" && (
        <div className="text-rose-400 font-medium">Lỗi: {(data as any).message}</div>
      )}
    </div>
  );

  const lineChartData = {
    labels: data.hourly_labels || ['1h', '2h', '3h', '4h', '5h', '6h', '7h', '8h'],
    datasets: [
      {
        label: 'Sản lượng',
        data: (data as any).hourly_data || (data as any).vien_stats?.hourly || [0, 0, 0, 0, 0, 0, 0, 0],
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: '#3b82f6',
      },
    ],
  };

  const doughnutData = {
    labels: data.error_types ? Object.keys(data.error_types) : [],
    datasets: [
      {
        data: data.error_types ? Object.values(data.error_types) : [],
        backgroundColor: ['#f59e0b', '#ef4444', '#8b5cf6'],
        borderWidth: 0,
        hoverOffset: 10,
      },
    ],
  };

  return (
    <main className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto space-y-6">
      {/* HEADER */}
      <header className="glass rounded-3xl p-6 flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold bg-gradient-to-right from-blue-400 to-indigo-400 bg-clip-text text-transparent tracking-tight">
            PHARMA MONITOR PRO
          </h1>
          <div className="flex items-center gap-2 mt-1 text-slate-400 text-sm font-medium">
            <Clock className="h-4 w-4" />
            <span>HỆ THỐNG GIÁM SÁT THỜI GIAN THỰC</span>
            <span className="mx-2">|</span>
            <span>SYNC: <span className="text-blue-400 tabular-nums">{data.last_sync}</span></span>
          </div>
        </div>
        
        <div className="flex gap-4">
          <StatusIndicator 
            label="PLC" 
            online={data.plc_connected} 
            icon={<Cpu className="h-4 w-4" />} 
          />
          <StatusIndicator 
            label="CAM" 
            online={data.cam_connected} 
            icon={<Camera className="h-4 w-4" />} 
          />
        </div>
      </header>

      {/* CONTROL & MODEL SELECTION */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ModelButton 
          active={data.current_model_id === 1} 
          onClick={() => setModel(1)}
          title="Model: Viên rời"
          icon="📦"
        />
        <ModelButton 
          active={data.current_model_id === 2} 
          onClick={() => setModel(2)}
          title="Model: Vỉ thuốc"
          icon="💊"
        />
      </section>

      {/* STATS CARDS */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          label="Hệ thống" 
          value={data.status} 
          color={data.status === "RUNNING" ? "text-emerald-400" : "text-amber-400"}
          icon={<Activity className="h-6 w-6" />}
          borderColor="border-amber-500/50"
        />
        <StatCard 
          label="Tổng sản lượng" 
          value={data.total} 
          color="text-blue-400"
          icon={<Package className="h-6 w-6" />}
          borderColor="border-blue-500/50"
        />
        <StatCard 
          label="Sản phẩm đạt" 
          value={data.ok} 
          color="text-emerald-400"
          icon={<CheckCircle2 className="h-6 w-6" />}
          borderColor="border-emerald-500/50"
        />
        <StatCard 
          label="Sản phẩm lỗi" 
          value={data.ng} 
          color="text-rose-400"
          icon={<AlertCircle className="h-6 w-6" />}
          borderColor="border-rose-500/50"
        />
      </section>

      {/* CHARTS */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass rounded-3xl p-6">
          <div className="flex items-center gap-2 mb-6 text-blue-400 font-bold">
            <BarChart3 className="h-5 w-5" />
            <span>SẢN LƯỢNG THEO GIỜ</span>
          </div>
          <div className="h-64">
            <Line data={lineChartData} options={chartOptions} />
          </div>
        </div>
        
        <div className="glass rounded-3xl p-6">
          <div className="flex items-center gap-2 mb-6 text-amber-400 font-bold">
            <PieChartIcon className="h-5 w-5" />
            <span>PHÂN TÍCH LOẠI LỖI</span>
          </div>
          <div className="h-64 flex items-center justify-center">
            <Doughnut data={doughnutData} options={doughnutOptions} />
          </div>
        </div>
      </section>

      {/* LOGS & IMAGES */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass rounded-3xl p-6">
          <div className="flex items-center gap-2 mb-6 text-rose-400 font-bold">
            <AlertCircle className="h-5 w-5" />
            <span>HÌNH ẢNH LỖI GẦN ĐÂY</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[1,2,3,4,5,6].map(i => (
              <div key={i} className="aspect-square rounded-xl bg-black/40 border border-white/5 flex items-center justify-center text-xs text-slate-600">
                NO IMAGE
              </div>
            ))}
          </div>
        </div>

        <div className="glass rounded-3xl p-6">
          <div className="flex items-center gap-2 mb-6 text-blue-400 font-bold">
            <ChevronRight className="h-5 w-5" />
            <span>NHẬT KÝ KIỂM TRA</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-slate-500 text-xs uppercase tracking-wider border-b border-white/5">
                  <th className="pb-3 px-2">Loại</th>
                  <th className="pb-3 px-2">Kết quả</th>
                  <th className="pb-3 px-2 text-right">Giờ</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {data.recent_logs?.map((log, idx) => (
                  <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="py-3 px-2 text-slate-300">{log[1]}</td>
                    <td className={`py-3 px-2 font-bold ${log[2]?.includes('NG') || log[2]?.includes('LỖI') ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {log[2]}
                    </td>
                    <td className="py-3 px-2 text-right text-slate-500 tabular-nums">{log[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}

function StatusIndicator({ label, online, icon }: { label: string; online: boolean; icon: React.ReactNode }) {
  return (
    <div className="glass flex items-center gap-3 px-4 py-2 rounded-full border border-white/10">
      <div className={`p-1.5 rounded-full ${online ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
        {icon}
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] text-slate-500 font-bold leading-none">{label}</span>
        <span className={`text-xs font-black ${online ? 'text-emerald-400' : 'text-rose-400'}`}>
          {online ? 'ONLINE' : 'OFFLINE'}
        </span>
      </div>
      <div className={`h-2 w-2 rounded-full ${online ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
    </div>
  );
}

function ModelButton({ active, onClick, title, icon }: { active: boolean; onClick: () => void; title: string; icon: string }) {
  return (
    <button 
      onClick={onClick}
      className={`p-4 rounded-2xl flex items-center justify-center gap-3 transition-all duration-300 font-bold border ${
        active 
          ? 'bg-blue-600 border-blue-400 shadow-[0_0_20px_rgba(37,99,235,0.3)] text-white' 
          : 'glass border-white/10 text-slate-400 hover:bg-white/5'
      }`}
    >
      <span className="text-2xl">{icon}</span>
      {title}
    </button>
  );
}

function StatCard({ label, value, color, icon, borderColor }: { label: string; value: string | number; color: string; icon: React.ReactNode; borderColor: string }) {
  return (
    <div className={`glass relative overflow-hidden rounded-3xl p-6 border-l-4 ${borderColor}`}>
      <div className="flex justify-between items-start">
        <div className="space-y-1">
          <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">{label}</span>
          <div className={`text-3xl font-black tabular-nums ${color}`}>
            {value}
          </div>
        </div>
        <div className={`p-2 rounded-xl bg-white/5 ${color}`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(15, 23, 42, 0.9)',
      titleColor: '#3b82f6',
      bodyColor: '#fff',
      padding: 12,
      cornerRadius: 12,
      displayColors: false,
    }
  },
  scales: {
    y: {
      beginAtZero: true,
      grid: { color: 'rgba(255,255,255,0.05)', drawBorder: false },
      ticks: { color: '#64748b', font: { size: 10 } }
    },
    x: {
      grid: { display: false },
      ticks: { color: '#64748b', font: { size: 10 } }
    }
  }
};

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '75%',
  plugins: {
    legend: {
      position: 'bottom' as const,
      labels: {
        color: '#94a3b8',
        usePointStyle: true,
        pointStyle: 'circle',
        padding: 20,
        font: { size: 11, weight: 'bold' }
      }
    },
    tooltip: {
      backgroundColor: 'rgba(15, 23, 42, 0.9)',
      padding: 12,
      cornerRadius: 12,
    }
  }
};
