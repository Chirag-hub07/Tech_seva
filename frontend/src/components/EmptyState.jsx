import { DatabaseZap } from 'lucide-react'
export default function EmptyState({ title = 'No data to display', detail = 'This view will populate when the FastAPI service is connected.' }) {
  return <div className="empty-state"><DatabaseZap size={30} /><strong>{title}</strong><p>{detail}</p></div>
}
