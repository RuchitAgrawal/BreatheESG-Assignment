import { useRef, useState } from 'react';

export default function UploadModal({
  onClose, onSuccess, onError, ingestSAP, ingestUtility, ingestTravel,
}: {
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
  ingestSAP: any;
  ingestUtility: any;
  ingestTravel: any;
}) {
  const [tab, setTab] = useState<'sap' | 'utility' | 'travel'>('sap');
  const [travelText, setTravelText] = useState('');
  const sapRef = useRef<HTMLInputElement>(null);
  const utilRef = useRef<HTMLInputElement>(null);

  async function handleSAP() {
    const file = sapRef.current?.files?.[0];
    if (!file) return;
    try {
      const r = await ingestSAP.mutateAsync(file);
      onSuccess(r.already_ingested
        ? 'File already ingested -- no duplicates created'
        : `SAP: ${r.row_count} rows ingested, ${r.error_count} errors`);
      onClose();
    } catch {
      onError('SAP ingestion failed. Check file format.');
    }
  }

  async function handleUtility() {
    const file = utilRef.current?.files?.[0];
    if (!file) return;
    try {
      const r = await ingestUtility.mutateAsync(file);
      onSuccess(r.already_ingested
        ? 'File already ingested -- no duplicates created'
        : `Utility: ${r.row_count} rows ingested, ${r.error_count} errors`);
      onClose();
    } catch {
      onError('Utility ingestion failed. Check file format.');
    }
  }

  async function handleTravel() {
    try {
      const payload = JSON.parse(travelText);
      const r = await ingestTravel.mutateAsync(payload);
      onSuccess(r.already_ingested
        ? 'Report already ingested -- no duplicates created'
        : `Travel: ${r.row_count} segments ingested, ${r.error_count} errors`);
      onClose();
    } catch (e) {
      if (e instanceof SyntaxError) onError('Invalid JSON -- check your paste.');
      else onError('Travel ingestion failed.');
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 500 }}>
        <div className="modal-title">Upload Data</div>

        <div className="flex gap-2" style={{ marginBottom: 16 }}>
          {(['sap', 'utility', 'travel'] as const).map((t) => (
            <button
              key={t}
              id={`tab-upload-${t}`}
              className="btn btn-ghost btn-sm"
              style={tab === t ? { borderColor: 'var(--color-primary)', color: 'var(--color-primary)' } : {}}
              onClick={() => setTab(t)}
            >
              {t.toUpperCase()}
            </button>
          ))}
        </div>

        {tab === 'sap' && (
          <div className="modal-body" style={{ marginBottom: 0 }}>
            <p style={{ marginBottom: 12 }}>
              Upload a SAP SE16N flat file export (CSV). English or German column headers are both supported.
            </p>
            <input id="input-sap-file" type="file" accept=".csv,.txt" ref={sapRef} className="form-input" />
          </div>
        )}

        {tab === 'utility' && (
          <div className="modal-body" style={{ marginBottom: 0 }}>
            <p style={{ marginBottom: 12 }}>
              Upload a utility portal CSV export (e.g. Dominion Energy, UK Power Networks).
            </p>
            <input id="input-utility-file" type="file" accept=".csv" ref={utilRef} className="form-input" />
          </div>
        )}

        {tab === 'travel' && (
          <div className="modal-body" style={{ marginBottom: 0 }}>
            <p style={{ marginBottom: 12 }}>
              Paste a Concur-style travel report JSON. Export from Concur, copy the full payload, paste here.
            </p>
            <textarea
              id="input-travel-json"
              className="form-input"
              rows={8}
              placeholder={'{\n  "report_id": "RPT-2024-Q4",\n  "trips": [...]\n}'}
              value={travelText}
              onChange={(e) => setTravelText(e.target.value)}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            />
          </div>
        )}

        <div className="modal-footer" style={{ marginTop: 16 }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button
            id="btn-ingest-submit"
            className="btn btn-primary"
            onClick={tab === 'sap' ? handleSAP : tab === 'utility' ? handleUtility : handleTravel}
            disabled={ingestSAP.isPending || ingestUtility.isPending || ingestTravel.isPending}
          >
            {(ingestSAP.isPending || ingestUtility.isPending || ingestTravel.isPending)
              ? <><span className="spinner" /> Processing...</>
              : 'Ingest'
            }
          </button>
        </div>
      </div>
    </div>
  );
}
