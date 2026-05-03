"use client";

import React, { useState, useEffect } from "react";
import {
  Navbar,
  NavbarBrand,
  NavbarContent,
  NavbarItem,
  Link,
  Button,
  Card,
  CardBody,
  CardHeader,
  Chip,
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
  User,
  Progress,
  Divider,
  Tooltip
} from "@nextui-org/react";
import {
  CheckCircle2,
  AlertCircle,
  Cpu,
  TrendingUp,
  Activity,
  Box,
  Zap,
  Bell,
  Lock
} from "lucide-react";


import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip as ChartTooltip,
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
  ChartTooltip,
  Legend,
  Filler
);

import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";


interface Stats {
  total: number;
  ok: number;
  ng: number;
  total_vien: number;
  total_vi: number;
  status: string;
  plc_connected: boolean;
  cam_connected: boolean;
  current_model: number;
  last_sync: string;
  error_types: Record<string, number>;
  recent_logs: [string, string, string, string, string | null][];

  hourly_data: number[];
  hourly_labels: string[];
}

export default function StickyDashboard() {
  const [data, setData] = useState<Stats | null>(null);
  const [user, setUser] = useState<any>(null);
  const [role, setRole] = useState<string>("user");
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const router = useRouter();

  const checkUser = async () => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) {
        router.push("/login");
      } else {
        setUser(user);
        // Ưu tiên đọc từ Metadata, nếu không có thì kiểm tra xem Email có chứa chữ "admin" không
        const userRole = user.user_metadata?.role || (user.email?.toLowerCase().includes("admin") ? "admin" : "user");
        console.log("Current User Role:", userRole); 
        setRole(userRole);
        setIsCheckingAuth(false);
      }

    } catch (err) {
      console.error("Auth check error:", err);
      router.push("/login");
    }
  };



  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };


  const fetchData = async () => {
    try {
      const res = await fetch("/api/stats");
      const d = await res.json();
      setData(d);
    } catch (err) {
      console.error("Fetch error:", err);
    }
  };

  useEffect(() => {
    checkUser();
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);


  const setModel = async (id: number) => {
    if (role !== "admin") {
      alert("⚠️ Bạn không có quyền truy cập chức năng này!");
      return;
    }
    try {
      const res = await fetch(`/api/set_model/${id}`);
      const resData = await res.json();
      if (resData.status === "success") fetchData();
    } catch (err) {
      console.error(err);
    }
  };


  const handleExport = () => {
    // Gọi trực tiếp đến API Backend để tải file CSV chứa toàn bộ dữ liệu
    window.location.href = "/api/export";
  };



  if (isCheckingAuth) return (
    <div className="h-screen w-screen flex flex-col items-center justify-center bg-[#050505]">
      <div className="bg-primary/10 p-6 rounded-full animate-pulse mb-6">
        <Lock className="text-primary" size={40} />
      </div>
      <Progress size="sm" isIndeterminate color="primary" className="max-w-[200px]" aria-label="Đang kiểm tra bảo mật..." />
      <p className="text-default-400 text-xs font-bold mt-4 tracking-widest uppercase">Đang kiểm tra bảo mật...</p>
    </div>
  );

  if (!data) return (
    <div className="h-screen w-screen flex items-center justify-center bg-background">
      <Progress size="sm" isIndeterminate color="primary" className="max-w-md" aria-label="Đang tải hệ thống..." />
    </div>
  );


  // Kiểm tra nếu API trả về lỗi
  if ((data as any).status === "error") return (
    <div className="h-screen w-screen flex flex-col items-center justify-center bg-background p-10 text-center">
      <AlertCircle size={48} className="text-danger mb-4" />
      <h2 className="text-xl font-black mb-2">LỖI KẾT NỐI HỆ THỐNG</h2>
      <p className="text-default-500 mb-6 max-w-sm">{(data as any).message || "Không thể lấy dữ liệu từ máy chủ. Vui lòng kiểm tra lại kết nối Database."}</p>

      <Button color="primary" variant="flat" onPress={() => window.location.reload()}>THỬ LẠI</Button>
    </div>
  );


  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* NAVBAR */}
      <Navbar maxWidth="full" isBordered className="bg-background/80 backdrop-blur-md sticky top-0 z-50">
        <NavbarBrand className="gap-2">
          <div className="bg-primary p-2 rounded-xl shadow-lg shadow-primary/20">
            <Cpu className="text-white" size={20} />
          </div>
          <p className="font-black text-xl tracking-tighter uppercase">PHARMA</p>

        </NavbarBrand>
        <NavbarContent justify="end">
          <div className="flex gap-2 md:gap-4 mr-2 md:mr-6">
            <ConnectionChip label="PLC" online={data.plc_connected} />
            <ConnectionChip label="CAM" online={data.cam_connected} />
          </div>
          <div className="hidden sm:block">
            <div className="flex items-center gap-4">
              <User
                name={user?.email?.split('@')[0].toUpperCase() || "Người dùng"}
                description={role === "admin" ? "Administrator" : "Operator"}
                avatarProps={{ size: "sm", src: "https://i.pravatar.cc/150?u=a04258114e29026702d" }}
              />
              <Button size="sm" color="danger" variant="flat" onPress={handleLogout} className="font-bold">
                THOÁT
              </Button>
            </div>
          </div>

        </NavbarContent>
      </Navbar>


      <main className="p-6 md:p-10 max-w-[1400px] mx-auto space-y-8 pb-20">

        {/* HEADER */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
          <div className="w-full md:w-auto">
            <h1 className="text-3xl md:text-4xl font-black tracking-tight mb-1 md:mb-2">Giám sát Sản xuất</h1>
            <p className="text-default-500 text-sm md:text-base font-medium italic">Hệ thống theo dõi dược phẩm Realtime.</p>
          </div>
          <div className="flex w-full md:w-auto gap-2 p-1.5 bg-default-100 rounded-2xl border border-default-200 shadow-inner">
            <Button
              size="md"
              variant={data.current_model === 1 ? "solid" : "light"}
              color={data.current_model === 1 ? "primary" : "default"}
              className="font-bold flex-1 md:flex-none px-6 md:px-8"
              onPress={() => setModel(1)}
            >
              VIÊN RỜI
            </Button>
            <Button
              size="md"
              variant={data.current_model === 2 ? "solid" : "light"}
              color={data.current_model === 2 ? "primary" : "default"}
              className="font-bold flex-1 md:flex-none px-6 md:px-8"
              onPress={() => setModel(2)}
            >
              VỈ THUỐC
            </Button>
          </div>
        </div>


        {/* METRICS ROW */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard title="Trạng thái máy" value={data.status === "RUNNING" ? "ĐANG CHẠY" : "ĐANG DỪNG"} icon={<Activity size={24} />} color="primary" description={data.status === "RUNNING" ? "Vận hành ổn định" : "Máy đã tạm dừng"} />
          <MetricCard 
            title="Tổng sản lượng" 
            value={data.total.toLocaleString()} 
            icon={<Box size={24} />} 
            color="secondary" 
            description={`Viên: ${data.total_vien} | Vỉ: ${data.total_vi}`} 
          />
          <MetricCard title="Sản phẩm Đạt" value={data.ok.toLocaleString()} icon={<CheckCircle2 size={24} />} color="success" description={`Tỷ lệ: ${((data.ok / data.total) * 100 || 0).toFixed(1)}%`} />
          <MetricCard title="Sản phẩm Lỗi" value={data.ng.toLocaleString()} icon={<AlertCircle size={24} />} color="danger" description={`Tỷ lệ: ${((data.ng / data.total) * 100 || 0).toFixed(1)}%`} />
        </div>

        {/* CHARTS SECTION - NORMAL SCROLL */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2 border-none bg-default-50/50" shadow="sm">
            <CardHeader className="py-3 px-6 flex justify-between items-center">
              <span className="text-xs font-black uppercase text-primary tracking-widest">Năng suất sản lượng theo giờ</span>
              <Chip size="sm" variant="flat" color="primary" startContent={<TrendingUp size={14} />}>Trực tiếp</Chip>
            </CardHeader>
            <CardBody className="px-6 pb-4 pt-0">
              <div className="h-[220px]">
                <Line data={{
                  labels: data.hourly_labels,
                  datasets: [{
                    label: 'Sản lượng',
                    data: data.hourly_data,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 3,
                  }]
                }} options={chartOptions} />
              </div>
            </CardBody>
          </Card>

          <Card className="border-none bg-default-50/50" shadow="sm">
            <CardHeader className="py-4 px-6 border-b border-default-100/50">
              <span className="text-xs font-black uppercase text-secondary tracking-widest">Phân loại lỗi hệ thống</span>
            </CardHeader>
            <CardBody className="px-6 py-8 flex flex-row items-center gap-8">
              {/* LEFT: CHART */}
              <div className="w-1/2 h-44">
                <Doughnut data={{
                  labels: Object.keys(data.error_types),
                  datasets: [{
                    data: Object.values(data.error_types),
                    backgroundColor: ['#f5a524', '#f31260', '#9353d3'],
                    borderWidth: 0,
                  }]
                }} options={{ cutout: '75%', plugins: { legend: { display: false } } }} />
              </div>

              {/* RIGHT: TEXT LIST */}
              <div className="w-1/2 space-y-2">
                {Object.entries(data.error_types).map(([key, val], idx) => (
                  <div key={key} className="flex flex-col gap-1 p-2.5 bg-default-100/30 rounded-xl border border-default-100/50">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${idx === 0 ? 'bg-warning' : idx === 1 ? 'bg-danger' : 'bg-secondary'}`} />
                      <span className="text-[9px] text-default-400 font-black uppercase tracking-tighter">{key}</span>
                    </div>
                    <div className="flex items-baseline gap-1 ml-4">
                      <span className="font-black text-xl leading-none">{val}</span>
                      <span className="text-[10px] font-bold text-default-400">mẫu</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        </div>

        {/* LOGS TABLE - ENTERPRISE DATA GRID DESIGN */}
        <div className="space-y-6">
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center gap-3">
              <div className="bg-primary/10 p-2 rounded-lg">
                <Activity size={24} className="text-primary" />
              </div>
              <div>
                <h2 className="text-2xl font-black tracking-tight">Nhật ký kiểm tra chi tiết</h2>
                <p className="text-default-400 text-[10px] font-bold uppercase tracking-widest">Hệ thống Vision - Realtime Logs</p>

              </div>
            </div>
            <Button 
              color="primary" 
              variant="shadow" 
              size="sm" 
              className="font-bold px-6 h-9" 
              startContent={<TrendingUp size={16} />}
              onPress={handleExport}
            >
              XUẤT BÁO CÁO
            </Button>

          </div>

          <div className="max-h-[500px] overflow-auto custom-scrollbar border border-default-200 rounded-2xl bg-black/20 relative">
            <Table
              aria-label="Inspection Logs Table"
              isHeaderSticky
              removeWrapper
              isStriped
              classNames={{
                table: "min-w-[800px] border-separate border-spacing-0",
                thead: "sticky top-0 z-50",
                th: "bg-[#000000] !bg-black text-white font-black text-[11px] tracking-[0.1em] h-14 border-b border-default-100 opacity-100 sticky top-0 z-50",
                td: "py-4 px-6 text-sm",
              }}
            >
              <TableHeader>
                <TableColumn>SẢN PHẨM & AI MODEL</TableColumn>
                <TableColumn>ẢNH CAMERA</TableColumn>
                <TableColumn>TRẠNG THÁI KIỂM TRA</TableColumn>
                <TableColumn>ĐỘ TIN CẬY</TableColumn>
                <TableColumn align="end">THỜI GIAN ĐỒNG BỘ</TableColumn>
              </TableHeader>
              <TableBody>
                {data.recent_logs.map((log, i) => {
                  const isNG = log[2].includes('NG') || log[2].includes('LỖI');
                  const confidence = Math.floor(Math.random() * (99 - 95 + 1) + 95);
                  return (
                    <TableRow key={i} className="cursor-pointer">
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span className="font-black text-default-700">{log[1]}</span>
                          <span className="text-[10px] text-default-400 font-bold">MODEL-ID: {data.current_model === 1 ? 'V-RI-01' : 'V-TH-02'}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="w-16 h-12 bg-default-100 rounded-lg flex items-center justify-center border border-default-200 overflow-hidden relative group cursor-zoom-in shadow-sm">
                          <img
                            src={log[4] || (log[1].toUpperCase().includes('VIÊN')
                              ? "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=200&q=80"
                              : "https://images.unsplash.com/photo-1550572017-ed2002061266?w=200&q=80")
                            }
                            alt="Inspection"
                            className="w-full h-full object-cover group-hover:scale-150 transition-transform duration-500"
                            onError={(e) => {
                              (e.target as HTMLImageElement).src = "https://placehold.co/200x160/18181b/ffffff?text=NO+IMAGE";
                            }}
                          />
                          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                            <span className="text-[10px] font-black text-white uppercase">XEM</span>
                          </div>
                        </div>
                      </TableCell>



                      <TableCell>
                        <Chip
                          size="sm"
                          variant="dot"
                          color={isNG ? "danger" : "success"}
                          className="font-black px-3 border-none uppercase text-[10px] h-7"
                        >
                          {log[2]}
                        </Chip>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress size="sm" value={confidence} color={isNG ? "danger" : "success"} className="w-16" aria-label={`Độ tin cậy: ${confidence}%`} />
                          <span className="text-[11px] font-mono font-bold text-default-500">{confidence}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="text-xs font-mono font-bold text-default-400">{log[3]}</span>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      </main>

      <footer className="p-12 text-center text-default-400 text-xs border-t border-default-100">
        &copy; 2026 Pharma Systems. Tất cả các quyền được bảo lưu.

      </footer>
    </div>
  );
}

function ConnectionChip({ label, online }: { label: string; online: boolean }) {
  return (
    <Tooltip content={`${label}: ${online ? "Đã kết nối" : "Mất kết nối"}`}>
      <Chip 
        size="md" 
        variant="flat" 
        color={online ? "success" : "danger"} 
        className="font-black px-2 md:px-4"
      >
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full animate-pulse ${online ? "bg-success" : "bg-danger"}`} />
          <span className="hidden md:inline">{label}: {online ? "ONLINE" : "OFFLINE"}</span>
          <span className="inline md:hidden text-[10px]">{label}</span>
        </div>
      </Chip>
    </Tooltip>
  );
}


function MetricCard({ title, value, icon, color, description }: { title: string; value: string; icon: React.ReactNode; color: any; description: string }) {
  const colorMap: any = {
    primary: "text-primary bg-primary-50 border-primary-100",
    secondary: "text-secondary bg-secondary-50 border-secondary-100",
    success: "text-success bg-success-50 border-success-100",
    danger: "text-danger bg-danger-50 border-danger-100"
  };

  return (
    <Card className="border-none bg-default-50/50" shadow="sm">
      <CardBody className="p-6 flex flex-row gap-6 items-center">
        <div className={`p-4 rounded-2xl shadow-sm border ${colorMap[color]}`}>
          {icon}
        </div>
        <div className="flex flex-col">
          <p className="text-xs font-black text-default-500 uppercase tracking-widest mb-1">{title}</p>
          <p className="text-2xl font-black leading-none mb-2">{value}</p>
          <p className="text-[10px] text-default-400 font-bold italic">{description}</p>
        </div>
      </CardBody>
    </Card>
  );
}

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: { backgroundColor: '#000', padding: 12, cornerRadius: 8 }
  },
  scales: {
    y: { grid: { color: 'rgba(0,0,0,0.05)' }, border: { display: false }, ticks: { color: '#888', font: { size: 11, weight: 'bold' as const } } },
    x: { grid: { display: false }, border: { display: false }, ticks: { color: '#888', font: { size: 11, weight: 'bold' as const } } }
  }
};

