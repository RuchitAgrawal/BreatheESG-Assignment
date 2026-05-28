export default function SkeletonRow() {
  return (
    <tr>
      <td className="col-check">
        <div className="skeleton" style={{ width: 16, height: 16, borderRadius: 4 }}></div>
      </td>
      <td className="col-quality">
        <div className="flex justify-center">
          <div className="skeleton" style={{ width: 8, height: 8, borderRadius: '50%' }}></div>
        </div>
      </td>
      <td>
        <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 4 }}></div>
      </td>
      <td>
        <div className="skeleton" style={{ width: 120, height: 16, borderRadius: 4, marginBottom: 6 }}></div>
        <div className="skeleton" style={{ width: 180, height: 12, borderRadius: 4 }}></div>
      </td>
      <td>
        <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 4 }}></div>
      </td>
      <td>
        <div className="skeleton" style={{ width: 60, height: 16, borderRadius: 4 }}></div>
      </td>
      <td className="col-scope">
        <div className="skeleton" style={{ width: 40, height: 18, borderRadius: 9999 }}></div>
      </td>
      <td>
        <div className="skeleton" style={{ width: 30, height: 18, borderRadius: 4 }}></div>
      </td>
      <td className="col-state">
        <div className="skeleton" style={{ width: 80, height: 18, borderRadius: 9999 }}></div>
      </td>
    </tr>
  );
}
