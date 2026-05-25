"use client";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
export function CostLatencyChart({ data }: { data: Array<{ name: string; latency: number }> }) {
  return <ResponsiveContainer width="100%" height={245}><BarChart data={data}><XAxis dataKey="name" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="latency" name="Latency (s)" fill="#155eef" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>;
}
