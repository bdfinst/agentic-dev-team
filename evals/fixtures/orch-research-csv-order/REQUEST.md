# Request

Let users choose the column order of the monthly sales report's CSV export.
The order is a per-download choice in the export dialog, not saved anywhere.
No new endpoints: the existing export call gains an optional `columns` list.
