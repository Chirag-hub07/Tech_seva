import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import EmptyState from './EmptyState'
export default function SensorChart({ data, sensor }) {
  if (!data?.length) return <EmptyState title={`No ${sensor} measurements`} detail="No measurements were returned for the selected time range." />
  const numericKey = Object.keys(data[0].measurements || data[0].values || {}).find((key) => typeof (data[0].measurements || data[0].values)[key] === 'number')
  const chartData = data.map((m) => ({ time: new Date(m.measured_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), value: (m.measurements || m.values || {})[numericKey] ?? m.value }))
  return <ResponsiveContainer width="100%" height={285}><LineChart data={chartData} margin={{ top: 12, right: 12, left: -20, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={12} /><YAxis tickLine={false} axisLine={false} fontSize={12} /><Tooltip /><Line type="monotone" dataKey="value" stroke="#0e7490" strokeWidth={3} dot={false} /></LineChart></ResponsiveContainer>
}
