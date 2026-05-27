import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';
import type {
  User, SourceFile, ActivityRecord, ActivityRecordDetail,
  RecordRevision, EmissionCalculation, PaginatedResponse,
} from './types';

// ---- Auth ------------------------------------------------------------------

export function useMe() {
  return useQuery<User>({
    queryKey: ['me'],
    queryFn: () => api.get('/me/').then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}

// ---- Source Files ----------------------------------------------------------

export function useSourceFiles() {
  return useQuery<SourceFile[]>({
    queryKey: ['source-files'],
    queryFn: () => api.get('/source-files/').then((r) => r.data.results ?? r.data),
  });
}

// ---- Records ---------------------------------------------------------------

export interface RecordFilters {
  state?: string;
  quality_tier?: string;
  source_type?: string;
  date_from?: string;
  date_to?: string;
  source_file_id?: string;
  page?: number;
}

export function useRecords(filters: RecordFilters = {}) {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== '')
  );
  return useQuery<PaginatedResponse<ActivityRecord>>({
    queryKey: ['records', params],
    queryFn: () => api.get('/records/', { params }).then((r) => r.data),
  });
}

export function useRecordDetail(id: string | null) {
  return useQuery<ActivityRecordDetail>({
    queryKey: ['record', id],
    queryFn: () => api.get(`/records/${id}/`).then((r) => r.data),
    enabled: !!id,
  });
}

export function useRecordLineage(id: string | null) {
  return useQuery<ActivityRecordDetail>({
    queryKey: ['lineage', id],
    queryFn: () => api.get(`/records/${id}/lineage/`).then((r) => r.data),
    enabled: !!id,
  });
}

export function useRecordRevisions(id: string | null) {
  return useQuery<RecordRevision[]>({
    queryKey: ['revisions', id],
    queryFn: () => api.get(`/records/${id}/revisions/`).then((r) => r.data.results ?? r.data),
    enabled: !!id,
  });
}

export function useRecordCalculations(id: string | null) {
  return useQuery<EmissionCalculation[]>({
    queryKey: ['calculations', id],
    queryFn: () => api.get(`/records/${id}/calculation/`).then((r) => r.data.results ?? r.data),
    enabled: !!id,
  });
}

// ---- Mutations -------------------------------------------------------------

export function useBulkApprove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.post('/records/bulk-approve/', { record_ids: ids }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] });
    },
  });
}

export function useLockRecord() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/records/${id}/lock/`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] });
    },
  });
}

export function useIngestSAP() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return api.post('/ingest/sap/', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then((r) => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['source-files'] });
      qc.invalidateQueries({ queryKey: ['records'] });
    },
  });
}

export function useIngestUtility() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return api.post('/ingest/utility/', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then((r) => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['source-files'] });
      qc.invalidateQueries({ queryKey: ['records'] });
    },
  });
}

export function useIngestTravel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: object) =>
      api.post('/ingest/travel/', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['source-files'] });
      qc.invalidateQueries({ queryKey: ['records'] });
    },
  });
}

export function useAuditLog() {
  return useQuery<RecordRevision[]>({
    queryKey: ['audit-log'],
    queryFn: () => api.get('/audit-log/').then((r) => r.data.results ?? r.data),
  });
}
