"use client";

import React, { useState } from "react";
import { Card, CardBody, Input, Button, Checkbox } from "@nextui-org/react";
import { Lock, Mail, Cpu, AlertCircle } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const { data, error: authError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (authError) throw authError;
      
      // Chuyển hướng về Dashboard sau khi đăng nhập thành công
      router.push("/");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Lỗi đăng nhập. Vui lòng kiểm tra lại tài khoản.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#050505] relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 rounded-full blur-[120px]" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-secondary/10 rounded-full blur-[120px]" />

      <Card className="w-full max-w-[420px] bg-black/40 backdrop-blur-xl border-white/10 shadow-2xl p-4" shadow="lg">
        <CardBody className="gap-8 py-10">
          <div className="flex flex-col items-center gap-2">
            <div className="bg-primary p-3 rounded-2xl shadow-lg shadow-primary/30 mb-2">
              <Cpu className="text-white" size={32} />
            </div>
            <h1 className="text-3xl font-black tracking-tighter text-white">PHARMA MONITOR</h1>
            <p className="text-default-400 font-medium text-sm">Hệ thống quản lý sản xuất thông minh</p>
          </div>

          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            {error && (
              <div className="bg-danger-50 border border-danger-200 p-3 rounded-xl flex items-center gap-3 text-danger text-sm">
                <AlertCircle size={18} />
                <span className="font-bold">{error}</span>
              </div>
            )}

            <Input
              label="Email công ty"
              placeholder="admin@pharma.com"
              labelPlacement="outside"
              startContent={<Mail className="text-default-400" size={18} />}
              variant="bordered"
              size="lg"
              className="font-bold"
              value={email}
              onValueChange={setEmail}
              isRequired
            />

            <Input
              label="Mật khẩu"
              placeholder="••••••••"
              labelPlacement="outside"
              type="password"
              startContent={<Lock className="text-default-400" size={18} />}
              variant="bordered"
              size="lg"
              className="font-bold"
              value={password}
              onValueChange={setPassword}
              isRequired
            />

            <div className="flex justify-between items-center px-1">
              <Checkbox size="sm" classNames={{ label: "text-default-400 font-bold" }}>Ghi nhớ đăng nhập</Checkbox>
              <span className="text-xs text-primary font-black cursor-pointer hover:underline">Quên mật khẩu?</span>
            </div>

            <Button 
              type="submit" 
              color="primary" 
              size="lg" 
              className="font-black mt-4 shadow-lg shadow-primary/20"
              isLoading={loading}
            >
              ĐĂNG NHẬP HỆ THỐNG
            </Button>
          </form>

          <div className="text-center">
            <p className="text-xs text-default-500">
              Liên hệ IT nếu bạn không có tài khoản truy cập.
            </p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
