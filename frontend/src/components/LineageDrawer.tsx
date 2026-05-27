import { useRecordLineage, useRecordRevisions } from '../api/hooks';
import type { ActivityRecordDetail } from '../api/types';

function LineageSection({ detail }: { detail: ActivityRecordDetail }) {
  const calc = detail.calculations.find((c) => c.is_current);

  return (
    <>
      {/* CO2e hero */}
      <div className="co2e-hero">
        <div className="co2e-value">
          {calc ? parseFloat(calc.co2e_kg).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '--'}
        </div>
        <div className="co2e-unit">kgCO2e</div>
        {calc && (
          <div className="text-xs text-subtle mt-2" style={{ padding: '0 16px' }}>
            {calc.calculation_notes}
          </div>
        )}
      </div>

      {/* Source lineage */}
      <div className="drawer-section">
        <div className="drawer-section-title">Source Lineage</div>
        {detail.source_file ? (
          <>
            <div className="lineage-row">
              <span className="lineage-label">File</span>
              <span className="lineage-value">{detail.source_file.filename}</span>
            </div>
            <div className="lineage-row">
              <span className="lineage-label">Source type</span>
              <span className="lineage-value" style={{ textTransform: 'uppercase' }}>{detail.source_file.source_type}</span>
            </div>
            <div className="lineage-row">
              <span className="lineage-label">File hash (SHA-256)</span>
              <span className="lineage-value">{detail.source_file.file_hash.slice(0, 16)}...</span>
            </div>
            <div className="lineage-row">
              <span className="lineage-label">Uploaded</span>
              <span className="lineage-value">
                {new Date(detail.source_file.created_at).toLocaleString()}
              </span>
            </div>
          </>
        ) : (
          <span className="text-subtle text-sm">Manual entry (no source file)</span>
        )}
        {detail.source_row && (
          <>
            <div className="lineage-row">
              <span className="lineage-label">Row index</span>
              <span className="lineage-value">#{detail.source_row.row_index}</span>
            </div>
            <div className="lineage-row">
              <span className="lineage-label">Raw payload</span>
              <span className="lineage-value" />
            </div>
            <pre className="code-block">
              {JSON.stringify(detail.source_row.raw_payload, null, 2)}
            </pre>
          </>
        )}
      </div>

      {/* Normalization */}
      <div className="drawer-section">
        <div className="drawer-section-title">Normalization</div>
        <div className="lineage-row">
          <span className="lineage-label">Original</span>
          <span className="lineage-value">{detail.quantity} {detail.unit}</span>
        </div>
        <div className="lineage-row">
          <span className="lineage-label">Normalized</span>
          <span className="lineage-value">{detail.normalized_quantity} {detail.normalized_unit}</span>
        </div>
        <div className="lineage-row">
          <span className="lineage-label">Category</span>
          <span className="lineage-value">{detail.category.replace(/_/g, ' ')}</span>
        </div>
        <div className="lineage-row">
          <span className="lineage-label">Scope</span>
          <span className="lineage-value">Scope {detail.scope}</span>
        </div>
      </div>

      {/* Emission calculation */}
      {calc && (
        <div className="drawer-section">
          <div className="drawer-section-title">Emission Calculation</div>
          <div className="lineage-row">
            <span className="lineage-label">Factor name</span>
            <span className="lineage-value">{calc.emission_factor.name}</span>
          </div>
          <div className="lineage-row">
            <span className="lineage-label">Factor source</span>
            <span className="lineage-value">{calc.emission_factor.source}</span>
          </div>
          <div className="lineage-row">
            <span className="lineage-label">Factor value</span>
            <span className="lineage-value">{calc.emission_factor.factor_value} kgCO2e/{calc.emission_factor.unit}</span>
          </div>
          <div className="lineage-row">
            <span className="lineage-label">Calculated at</span>
            <span className="lineage-value">{new Date(calc.calculated_at).toLocaleString()}</span>
          </div>
          <div className="lineage-row">
            <span className="lineage-label">Calculated by</span>
            <span className="lineage-value">system (auto)</span>
          </div>

          {/* Historical calcs */}
          {detail.calculations.length > 1 && (
            <>
              <div className="drawer-section-title" style={{ marginTop: 12 }}>Calculation history</div>
              {detail.calculations.map((c) => (
                <div key={c.id} className="lineage-row" style={{ opacity: c.is_current ? 1 : 0.5 }}>
                  <span className="lineage-label">{c.is_current ? 'Current' : 'Superseded'}</span>
                  <span className="lineage-value">
                    {c.co2e_kg} kgCO2e &bull; {new Date(c.calculated_at).toLocaleString()}
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Quality notes */}
      {detail.quality_notes.length > 0 && (
        <div className="drawer-section">
          <div className="drawer-section-title">Quality Notes</div>
          {detail.quality_notes.map((n, i) => (
            <div key={i} style={{
              display: 'flex', gap: 10, padding: '8px 12px',
              background: 'var(--color-surface-2)', borderRadius: 6, marginBottom: 6,
              borderLeft: `3px solid var(--color-${n.severity === 'red' ? 'danger' : n.severity === 'yellow' ? 'warning' : 'success'})`
            }}>
              <div>
                <div className="text-xs font-mono" style={{ color: 'var(--color-ink-subtle)', marginBottom: 3 }}>{n.code}</div>
                <div className="text-sm text-muted">{n.message}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function AuditTrail({ recordId }: { recordId: string }) {
  const { data: revisions, isLoading } = useRecordRevisions(recordId);
  if (isLoading) return <div className="spinner" />;
  if (!revisions?.length) return <span className="text-subtle text-sm">No edits recorded.</span>;

  return (
    <div className="drawer-section">
      <div className="drawer-section-title">Audit Trail</div>
      {revisions.map((r) => (
        <div key={r.id} className="lineage-row">
          <span className="lineage-label" style={{ fontSize: 11 }}>
            {new Date(r.changed_at).toLocaleString()}<br />
            <span style={{ color: 'var(--color-ink-tertiary)' }}>{r.changed_by_email}</span>
          </span>
          <span className="lineage-value">
            {r.field_name}: {r.old_value ?? 'null'} &rarr; {r.new_value ?? 'null'}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function LineageDrawer({ recordId, onClose }: { recordId: string; onClose: () => void }) {
  const { data: detail, isLoading } = useRecordLineage(recordId);

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer" role="dialog" aria-modal="true" aria-label="Record lineage">
        <div className="drawer-header">
          <div>
            <div className="text-lg">{detail ? detail.category.replace(/_/g, ' ') : 'Loading...'}</div>
            {detail && (
              <div className="text-sm text-subtle mt-1">
                {new Date(detail.activity_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' })}
                {detail.subcategory ? ` · ${detail.subcategory}` : ''}
              </div>
            )}
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close drawer" id="btn-close-drawer">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="drawer-body">
          {isLoading ? (
            <div className="empty-state"><div className="spinner" style={{ width: 28, height: 28 }} /></div>
          ) : detail ? (
            <>
              <LineageSection detail={detail} />
              <AuditTrail recordId={recordId} />
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-state-title">Record not found</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
