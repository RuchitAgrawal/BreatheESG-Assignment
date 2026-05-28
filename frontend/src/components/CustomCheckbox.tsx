interface CustomCheckboxProps {
  checked: boolean;
  onChange: () => void;
}

export default function CustomCheckbox({ checked, onChange }: CustomCheckboxProps) {
  return (
    <div 
      className={`custom-checkbox ${checked ? 'checked' : ''}`} 
      onClick={(e) => {
        e.stopPropagation();
        onChange();
      }}
    >
      {checked && (
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--color-surface-1)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      )}
    </div>
  );
}
