import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import EmptyState from './EmptyState'
export default function SensorChart({ data, sensor }) {
  if (!data?.length) return <EmptyState title={`No ${sensor} measurements`} detail="No measurements were returned for the selected time range." />
  const numericKey = Object.keys(data[0].measurements || data[0].values || {}).find((key) => typeof (data[0].measurements || data[0].values)[key] === 'number')
  const chartData = data.map((m) => ({ time: new Date(m.measured_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), value: (m.measurements || m.values || {})[numericKey] ?? m.value }))
  return <ResponsiveContainer width="100%" height={310}><AreaChart data={chartData} margin={{ top: 18, right: 16, left: -20, bottom: 0 }}><defs><linearGradient id="sensor-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2d7a8a" stopOpacity={.24} /><stop offset="100%" stopColor="#2d7a8a" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} strokeDasharray="3 4" stroke="#d9e5eb" /><XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={12} interval="preserveStartEnd" /><YAxis tickLine={false} axisLine={false} fontSize={12} width={42} /><Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #d7e3e8', boxShadow: '0 10px 25px #17364a18' }} /><Area type="monotone" dataKey="value" stroke="#2d7a8a" strokeWidth={3} fill="url(#sensor-area)" activeDot={{ r: 5, strokeWidth: 3, fill: '#fff' }} /></AreaChart></ResponsiveContainer>
}
