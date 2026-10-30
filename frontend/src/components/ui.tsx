interface StatCardProps {
  label: string;
  value: string | number;
  sublabel?: string;
  tone?: 'default' | 'positive' | 'negative' | 'neutral';
}

const TONES: Record<string, string> = {
  default: 'text-gray-900',
  positive: 'text-primary-600',
  negative: 'text-danger-600',
  neutral: 'text-gray-500',
};

export function StatCard({ label, value, sublabel, tone = 'default' }: StatCardProps) {
  return (
    <div className="bg-white rounded-lg shadow p-5 border border-gray-100">
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${TONES[tone]}`}>{value}</div>
      {sublabel && <div className="mt-1 text-xs text-gray-400">{sublabel}</div>}
    </div>
  );
}

export function Badge({ children, tone = 'neutral' }: { children: string; tone?: 'buy' | 'sell' | 'hold' | 'neutral' }) {
  const map: Record<string, string> = {
    buy: 'bg-green-100 text-green-700',
    sell: 'bg-red-100 text-red-700',
    hold: 'bg-yellow-100 text-yellow-700',
    neutral: 'bg-gray-100 text-gray-600',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${map[tone]}`}>
      {children}
    </span>
  );
}

export function Card({ title, children, action }: { title?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg shadow border border-gray-100">
      {title && (
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-primary-600 rounded-full animate-spin" />
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="bg-danger-50 border border-danger-100 text-danger-700 rounded-lg p-4 text-sm">
      {message}
    </div>
  );
}