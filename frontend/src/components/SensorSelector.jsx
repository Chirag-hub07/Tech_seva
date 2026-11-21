import { Activity, Check, ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export default function SensorSelector({ sensors, value, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (event) => { if (!ref.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  return <div className="sensor-picker" ref={ref}><button className="sensor-trigger" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}><Activity size={17} /><strong>{value}</strong><ChevronDown size={16} className={open ? 'open' : ''} /></button>{open && <div className="sensor-menu" role="listbox">{sensors.map((sensor) => <button key={sensor} className={sensor === value ? 'active' : ''} onClick={() => { onChange(sensor); setOpen(false) }} role="option" aria-selected={sensor === value}><span>{sensor}</span>{sensor === value && <Check size={16} />}</button>)}</div>}</div>
}
