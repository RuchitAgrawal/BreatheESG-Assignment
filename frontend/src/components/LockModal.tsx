import { useState } from 'react';
import { useLockRecord } from '../api/hooks';
import type { ActivityRecord } from '../api/types';

export default function LockModal({
  records, onClose, onSuccess,
}: {
  records: ActivityRecord[];
  onClose: () => void;
  onSuccess: (n: number) => void;
}) {
  const [locking, setLocking] = useState(false);
  const lockRecord = useLockRecord();

  const tolock = records.filter((r) => r.state === 'approved');

  async function handleLock() {
    setLocking(true);
    let locked = 0;
    for (const rec of tolock) {
      try {
        await lockRecord.mutateAsync(rec.id);
        locked++;
      } catch {
        // continue locking others
      }
    }
    setLocking(false);
    onSuccess(locked);
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-title">Lock for Audit</div>
        <div className="modal-body">
          <p>
            You are about to lock <strong style={{ color: 'var(--color-ink)' }}>{tolock.length} approved record{tolock.length !== 1 ? 's' : ''}</strong> for audit.
          </p>
          <p style={{ marginTop: 12 }}>
            Locked records <strong style={{ color: 'var(--color-ink)' }}>cannot be edited</strong>. This action is irreversible.
            The emission calculations and audit trail for these records will be permanently preserved.
          </p>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose} id="btn-lock-cancel">Cancel</button>
          <button
            className="btn btn-danger"
            onClick={handleLock}
            disabled={locking || tolock.length === 0}
            id="btn-lock-confirm"
          >
            {locking ? <span className="spinner" /> : null}
            {locking ? 'Locking...' : `Lock ${tolock.length} records`}
          </button>
        </div>
      </div>
    </div>
  );
}
