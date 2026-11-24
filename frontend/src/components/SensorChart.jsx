import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import EmptyState from './EmptyState'
import { getChartNumericKey, SENSOR_DEFINITIONS } from '../utils/sensorMetrics'

export default function SensorChart({ data, sensor }) {
  if (!data?.length) {
    return (
      <EmptyState
        title={`No ${sensor} measurements`}
        detail="No telemetry observations were recorded for the selected participant in this historical window."
      />
    )
  }

  const numericKey = getChartNumericKey(data, sensor)
  if (!numericKey) {
    return (
      <EmptyState
        title={`No numeric metrics for ${sensor}`}
        detail="The recorded telemetry payload does not contain plottable numeric values."
      />
    )
  }

  const sensorConfig = SENSOR_DEFINITIONS[sensor]
  const metricLabel = sensorConfig?.keyLabels?.[numericKey] || numericKey.replaceAll('_', ' ')

  const chartData = data.map((m) => {
    const metrics = m.measurements || m.values || {}
    const rawVal = metrics[numericKey]
    const numVal = typeof rawVal === 'number' ? rawVal : (Number.isFinite(Number(rawVal)) ? Number(rawVal) : null)
    const dateObj = new Date(m.measured_at)

    return {
      time: dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      fullTime: dateObj.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }),
      value: numVal,
      isValid: m.is_valid,
      measuredAt: m.measured_at,
    }
  })

  // Consistent label spacing on the X-axis
  const labelInterval = chartData.length > 7 ? Math.ceil(chartData.length / 7) - 1 : 'preserveStartEnd'

  return (
    <ResponsiveContainer width="100%" height={310}>
      <AreaChart data={chartData} margin={{ top: 18, right: 16, left: -20, bottom: 8 }}>
        <defs>
          <linearGradient id="sensor-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2d7a8a" stopOpacity={0.24} />
            <stop offset="100%" stopColor="#2d7a8a" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} strokeDasharray="3 4" stroke="#d9e5eb" />
        <XAxis
          dataKey="time"
          tickLine={false}
          axisLine={false}
          fontSize={12}
          interval={labelInterval}
          tickMargin={10}
          minTickGap={28}
        />
        <YAxis tickLine={false} axisLine={false} fontSize={12} width={42} />
        <Tooltip
          contentStyle={{
            background: '#ffffff',
            borderRadius: 12,
            border: '1px solid #d7e3e8',
            boxShadow: '0 10px 25px #17364a18',
            color: '#243d56',
          }}
          labelStyle={{ color: '#63798b', fontWeight: 700 }}
          itemStyle={{ color: '#166f82', fontWeight: 700 }}
          labelFormatter={(_, payload) => payload?.[0]?.payload?.fullTime || ''}
          formatter={(value, _, item) => {
            const isValid = item?.payload?.isValid
            const statusSuffix = isValid === false ? ' (Flagged / Invalid)' : ''
            const displayVal = value !== null && value !== undefined ? `${value}${statusSuffix}` : 'Unavailable'
            return [displayVal, metricLabel]
          }}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke="#2d7a8a"
          strokeWidth={3}
          fill="url(#sensor-area)"
          activeDot={{ r: 5, strokeWidth: 3, fill: '#fff' }}
          connectNulls={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
