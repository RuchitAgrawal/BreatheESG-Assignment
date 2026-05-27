import { useAuditLog } from '../api/hooks';

export default function AuditLogTab() {
  const { data: revisions, isLoading } = useAuditLog();

  if (isLoading) return <div className="empty-state"><div className="spinner" style={{ width: 28, height: 28 }} /></div>;

  if (!revisions?.length) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📋</div>
        <div className="empty-state-title">No audit log entries</div>
        <div className="empty-state-desc">Changes to activity records will appear here.</div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Changed by</th>
            <th>Field</th>
            <th>Old value</th>
            <th>New value</th>
          </tr>
        </thead>
        <tbody>
          {revisions.map((r) => (
            <tr key={r.id}>
              <td className="font-mono text-sm">
                {new Date(r.changed_at).toLocaleString()}
              </td>
              <td className="text-sm">{r.changed_by_email}</td>
              <td className="font-mono text-sm" style={{ color: 'var(--color-ink-subtle)' }}>
                {r.field_name}
              </td>
              <td className="font-mono text-sm text-subtle">{r.old_value ?? '--'}</td>
              <td className="font-mono text-sm" style={{ color: 'var(--color-ink)' }}>{r.new_value ?? '--'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
