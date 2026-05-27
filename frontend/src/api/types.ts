// All TypeScript types matching Django API responses

export interface Organization {
  id: string;
  name: string;
  slug: string;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'analyst' | 'admin';
  organization: Organization;
}

export type SourceType = 'sap' | 'utility' | 'travel';
export type FileStatus = 'processing' | 'completed' | 'failed';

export interface SourceFile {
  id: string;
  source_type: SourceType;
  filename: string;
  status: FileStatus;
  row_count: number | null;
  error_count: number | null;
  created_at: string;
  uploaded_by_email: string | null;
}

export type RecordState = 'ingested' | 'needs_review' | 'approved' | 'locked';
export type QualityTier = 'green' | 'yellow' | 'red';
export type Scope = '1' | '2' | '3';

export interface QualityNote {
  code: string;
  message: string;
  severity: 'green' | 'yellow' | 'red';
}

export interface ActivityRecord {
  id: string;
  activity_date: string;
  category: string;
  subcategory: string;
  quantity: string;
  unit: string;
  normalized_quantity: string;
  normalized_unit: string;
  scope: Scope;
  state: RecordState;
  quality_tier: QualityTier;
  quality_notes: QualityNote[];
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  locked_at: string | null;
  created_at: string;
  source_type: SourceType | null;
  source_filename: string | null;
  co2e_kg: string | null;
}

export interface EmissionFactor {
  id: string;
  name: string;
  source: string;
  category: string;
  factor_value: string;
  unit: string;
  valid_from: string;
  valid_to: string | null;
  version: number;
}

export interface EmissionCalculation {
  id: string;
  co2e_kg: string;
  calculation_notes: string;
  calculated_at: string;
  is_current: boolean;
  emission_factor: EmissionFactor;
}

export interface SourceRow {
  id: string;
  row_index: number;
  raw_payload: Record<string, unknown>;
  parse_status: 'ok' | 'failed';
  parse_error: string | null;
  created_at: string;
}

export interface ActivityRecordDetail extends ActivityRecord {
  source_row: SourceRow | null;
  source_file: {
    id: string;
    filename: string;
    source_type: SourceType;
    file_hash: string;
    created_at: string;
  } | null;
  calculations: EmissionCalculation[];
  reviewed_by_email: string | null;
  locked_by_email: string | null;
  updated_at: string;
}

export interface RecordRevision {
  id: string;
  activity_record_id: string | null;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  change_reason: string;
  changed_at: string;
  changed_by_email: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
