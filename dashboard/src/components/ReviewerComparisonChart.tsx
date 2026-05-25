"use client";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
export function ReviewerComparisonChart({ data }: { data: Array<{ reviewer: string; score: number }> }) {
  return <ResponsiveContainer width="100%" height={245}><BarChart data={data}><XAxis dataKey="reviewer" tick={{ fontSize: 12 }} /><YAxis domain={[0, 100]} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="score" fill="#079455" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>;
}
