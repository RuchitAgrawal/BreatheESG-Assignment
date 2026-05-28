import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useMe, useSourceFiles, useRecords,
  useBulkApprove, useIngestSAP, useIngestUtility, useIngestTravel,
} from '../api/hooks';
import { useAuthStore } from '../store/auth';
import type { RecordFilters } from '../api/hooks';
import type { SourceType, ActivityRecord } from '../api/types';
import LineageDrawer from '../components/LineageDrawer';
import LockModal from '../components/LockModal';
import UploadModal from '../components/UploadModal';
import AuditLogTab from '../components/AuditLogTab';
import Toast, { useToast } from '../components/Toast';

const SOURCE_ICONS: Record<SourceType, string> = { sap: 'SAP', utility: 'UTL', travel: 'TRV' };

function StateBadge({ state }: { state: string }) {
  const cls = {
    ingested: 'badge badge-ingested',
    needs_review: 'badge badge-needs-review',
    approved: 'badge badge-approved',
    locked: 'badge badge-locked',
    failed: 'badge badge-failed',
    processing: 'badge badge-processing',
    completed: 'badge badge-completed',
  }[state] ?? 'badge badge-ingested';
  const label = state.replace('_', ' ').toUpperCase();
  return <span className={cls}>{label}</span>;
}

function QualityDot({ tier }: { tier: string }) {
  return <span className={`quality-dot quality-dot-${tier}`} title={tier} />;
}

function ScopeBadge({ scope }: { scope: string }) {
  return <span className={`badge badge-scope-${scope}`}>S{scope}</span>;
}

function SourceBadge({ type }: { type: SourceType | null }) {
  if (!type) return null;
  return <span className={`badge source-badge source-badge-${type}`}>{SOURCE_ICONS[type]}</span>;
}

function formatDate(s: string) {
  return new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCategory(cat: string) {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function DashboardPage() {
  const { logout } = useAuthStore();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { data: sourceFiles } = useSourceFiles();
  const { addToast, toasts, removeToast } = useToast();

  const [filters, setFilters] = useState<RecordFilters>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeDrawerId, setActiveDrawerId] = useState<string | null>(null);
  const [showLockModal, setShowLockModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [activeTab, setActiveTab] = useState<'records' | 'audit'>('records');

  const { data: recordsData, isLoading } = useRecords(filters);
  const records = recordsData?.results ?? [];
  const totalCount = recordsData?.count ?? 0;

  const bulkApprove = useBulkApprove();
  const ingestSAP = useIngestSAP();
  const ingestUtility = useIngestUtility();
  const ingestTravel = useIngestTravel();

  function setFilter(key: keyof RecordFilters, val: string) {
    setFilters((f) => ({ ...f, [key]: val || undefined, page: 1 }));
    setSelectedIds(new Set());
  }

  function setPage(page: number) {
    setFilters((f) => ({ ...f, page }));
    setSelectedIds(new Set());
  }

  function toggleSelect(id: string) {
    setSelectedIds((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selectedIds.size === records.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(records.map((r) => r.id)));
    }
  }

  async function handleBulkApprove() {
    const ids = Array.from(selectedIds);
    const result = await bulkApprove.mutateAsync(ids);
    addToast(`Approved ${result.approved} records`, 'success');
    setSelectedIds(new Set());
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  const allApproved = records.length > 0 && records.every((r) => r.state === 'approved' || r.state === 'locked');
  const canLock = allApproved && records.some((r) => r.state === 'approved');

  return (
    <div className="app-shell">
      {/* ---- Sidebar ---- */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">B</div>
          <div>
            <div className="sidebar-org">{me?.organization.name ?? '...'}</div>
            <div className="sidebar-role">{me?.role ?? ''}</div>
          </div>
        </div>

        <div className="sidebar-section-label">Data Sources</div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div
            className={`sidebar-file-item ${!filters.source_file_id ? 'active' : ''}`}
            onClick={() => setFilter('source_file_id', '')}
          >
            <span className="sidebar-file-name text-muted">All sources</span>
          </div>
          {(sourceFiles ?? []).map((sf) => (
            <div
              key={sf.id}
              className={`sidebar-file-item ${filters.source_file_id === sf.id ? 'active' : ''}`}
              onClick={() => setFilter('source_file_id', sf.id)}
            >
              <SourceBadge type={sf.source_type} />
              <span className="sidebar-file-name">{sf.filename}</span>
              <StateBadge state={sf.status} />
            </div>
          ))}
        </div>

        <div className="sidebar-upload-btn">
          <button
            id="btn-upload-data"
            className="btn btn-ghost w-full"
            onClick={() => setShowUploadModal(true)}
          >
            + Upload data
          </button>
        </div>

        <div style={{ padding: '0 12px 12px' }}>
          <button className="btn btn-ghost w-full" onClick={handleLogout} id="btn-logout">
            Sign out
          </button>
        </div>
      </aside>

      {/* ---- Main ---- */}
      <main className="main-content">
        {/* Header */}
        <div className="panel-header">
          <div className="flex items-center gap-4">
            <div>
              <div className="flex items-center gap-2">
                <button
                  className={`btn btn-sm ${activeTab === 'records' ? 'btn-ghost' : 'btn-ghost text-subtle'}`}
                  style={activeTab === 'records' ? { borderColor: 'var(--color-primary)', color: 'var(--color-primary)' } : {}}
                  onClick={() => setActiveTab('records')}
                  id="tab-records"
                >
                  Activity Records
                </button>
                <button
                  className={`btn btn-sm btn-ghost`}
                  style={activeTab === 'audit' ? { borderColor: 'var(--color-primary)', color: 'var(--color-primary)' } : {}}
                  onClick={() => setActiveTab('audit')}
                  id="tab-audit"
                >
                  Audit Log
                </button>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              id="btn-lock-audit"
              className="btn btn-primary"
              disabled={!canLock}
              onClick={() => setShowLockModal(true)}
              title={canLock ? 'Lock all approved records for audit' : 'All records must be approved before locking'}
            >
              Lock for Audit
            </button>
          </div>
        </div>

        {activeTab === 'audit' ? (
          <AuditLogTab onOpenRecord={(id) => setActiveDrawerId(id)} />
        ) : (
          <>
            {/* Filter bar */}
            <div className="filter-bar">
              <select id="filter-state" className="filter-select" value={filters.state ?? ''} onChange={(e) => setFilter('state', e.target.value)}>
                <option value="">All states</option>
                <option value="ingested">Ingested</option>
                <option value="needs_review">Needs Review</option>
                <option value="approved">Approved</option>
                <option value="locked">Locked</option>
              </select>
              <select id="filter-quality" className="filter-select" value={filters.quality_tier ?? ''} onChange={(e) => setFilter('quality_tier', e.target.value)}>
                <option value="">All quality</option>
                <option value="green">Green</option>
                <option value="yellow">Yellow</option>
                <option value="red">Red</option>
              </select>
              <select id="filter-source" className="filter-select" value={filters.source_type ?? ''} onChange={(e) => setFilter('source_type', e.target.value)}>
                <option value="">All sources</option>
                <option value="sap">SAP</option>
                <option value="utility">Utility</option>
                <option value="travel">Travel</option>
              </select>
              <input
                id="filter-date-from"
                type="date"
                className="filter-select"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
                value={filters.date_from ?? ''}
                onChange={(e) => setFilter('date_from', e.target.value)}
                title="Activity date from"
              />
              <input
                id="filter-date-to"
                type="date"
                className="filter-select"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
                value={filters.date_to ?? ''}
                onChange={(e) => setFilter('date_to', e.target.value)}
                title="Activity date to"
              />
              {(filters.date_from || filters.date_to) && (
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ fontSize: 11 }}
                  onClick={() => setFilters((f) => ({ ...f, date_from: undefined, date_to: undefined }))}
                >
                  Clear dates
                </button>
              )}
              <span className="filter-count">{totalCount} records</span>
            </div>

            {/* Table */}
            <div style={{ flex: 1, overflowY: 'auto', position: 'relative' }}>
              {isLoading ? (
                <div className="empty-state">
                  <div className="spinner" style={{ width: 28, height: 28 }} />
                </div>
              ) : records.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">📭</div>
                  <div className="empty-state-title">No records found</div>
                  <div className="empty-state-desc">Try adjusting your filters or upload data from the sidebar.</div>
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="col-check">
                        <input
                          type="checkbox"
                          id="check-all"
                          checked={selectedIds.size === records.length && records.length > 0}
                          onChange={toggleAll}
                        />
                      </th>
                      <th className="col-quality">Q</th>
                      <th>Date</th>
                      <th>Category</th>
                      <th>Quantity</th>
                      <th>CO2e</th>
                      <th className="col-scope">Scope</th>
                      <th>Source</th>
                      <th className="col-state">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((rec) => (
                      <RecordRow
                        key={rec.id}
                        record={rec}
                        selected={selectedIds.has(rec.id)}
                        onSelect={() => toggleSelect(rec.id)}
                        onOpen={() => setActiveDrawerId(rec.id)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Pagination Controls */}
            {totalCount > 0 && (
              <div className="flex items-center justify-between" style={{ padding: '12px 16px', borderTop: '1px solid var(--color-hairline)', background: 'var(--color-surface-1)' }}>
                <div className="text-sm text-subtle">
                  Showing page {filters.page || 1}
                </div>
                <div className="flex gap-2">
                  <button 
                    className="btn btn-ghost btn-sm" 
                    disabled={!recordsData?.previous} 
                    onClick={() => setPage((filters.page || 1) - 1)}
                  >
                    Previous
                  </button>
                  <button 
                    className="btn btn-ghost btn-sm" 
                    disabled={!recordsData?.next} 
                    onClick={() => setPage((filters.page || 1) + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            {/* Bulk action bar */}
            {selectedIds.size > 0 && (
              <div className="bulk-bar">
                <span className="bulk-count">{selectedIds.size} record{selectedIds.size !== 1 ? 's' : ''} selected</span>
                <button
                  id="btn-bulk-approve"
                  className="btn btn-primary"
                  onClick={handleBulkApprove}
                  disabled={bulkApprove.isPending}
                >
                  {bulkApprove.isPending ? <span className="spinner" /> : null}
                  Approve selected
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Clear
                </button>
              </div>
            )}
          </>
        )}
      </main>

      {/* ---- Drawer ---- */}
      {activeDrawerId && (
        <LineageDrawer
          recordId={activeDrawerId}
          onClose={() => setActiveDrawerId(null)}
        />
      )}

      {/* ---- Lock modal ---- */}
      {showLockModal && (
        <LockModal
          records={records}
          onClose={() => setShowLockModal(false)}
          onSuccess={(n) => addToast(`${n} records locked for audit`, 'success')}
        />
      )}

      {/* ---- Upload modal ---- */}
      {showUploadModal && (
        <UploadModal
          onClose={() => setShowUploadModal(false)}
          onSuccess={(msg) => addToast(msg, 'success')}
          onError={(msg) => addToast(msg, 'error')}
          ingestSAP={ingestSAP}
          ingestUtility={ingestUtility}
          ingestTravel={ingestTravel}
        />
      )}

      <Toast toasts={toasts} onRemove={removeToast} />
    </div>
  );
}

function RecordRow({
  record, selected, onSelect, onOpen,
}: {
  record: ActivityRecord;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <tr className={selected ? 'selected' : ''} onClick={onOpen}>
        <td className="col-check" onClick={(e) => { e.stopPropagation(); onSelect(); }}>
          <input type="checkbox" checked={selected} onChange={onSelect} onClick={(e) => e.stopPropagation()} />
        </td>
        <td className="col-quality" onClick={(e) => { e.stopPropagation(); setExpanded((x) => !x); }}>
          <div className="flex items-center justify-center" style={{ gap: 4 }}>
            <QualityDot tier={record.quality_tier} />
          </div>
        </td>
        <td className="text-sm font-mono">{formatDate(record.activity_date)}</td>
        <td>
          <div className="text-sm font-500" style={{ color: 'var(--color-ink)' }}>{formatCategory(record.category)}</div>
          {record.subcategory && <div className="text-xs text-subtle truncate" style={{ maxWidth: 200 }}>{record.subcategory}</div>}
        </td>
        <td className="font-mono text-sm">
          {parseFloat(record.normalized_quantity).toLocaleString(undefined, { maximumFractionDigits: 2 })} {record.normalized_unit}
        </td>
        <td className="font-mono text-sm" style={{ color: 'var(--color-primary-hover)' }}>
          {record.co2e_kg ? `${parseFloat(record.co2e_kg).toLocaleString(undefined, { maximumFractionDigits: 1 })} kg` : '--'}
        </td>
        <td className="col-scope"><ScopeBadge scope={record.scope} /></td>
        <td><SourceBadge type={record.source_type} /></td>
        <td className="col-state"><StateBadge state={record.state} /></td>
      </tr>
      {expanded && record.quality_notes.length > 0 && (
        <tr>
          <td colSpan={9} style={{ background: 'var(--color-surface-2)', padding: '0 12px' }}>
            <div style={{ padding: '10px 0', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {record.quality_notes.map((n, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <QualityDot tier={n.severity} />
                  <span className="font-mono text-xs" style={{ color: 'var(--color-ink-subtle)', minWidth: 160 }}>{n.code}</span>
                  <span className="text-muted">{n.message}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
