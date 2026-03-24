/** Convert a JSON object to a downloadable file */
export const downloadJsonFile = (jsonData: any, filename: string): void => {
  if (!filename) filename = 'data.json';
  if (!jsonData || typeof jsonData !== 'object') {
    console.error('Invalid JSON data provided for download.');
    return;
  }
  const jsonString = JSON.stringify(jsonData, null, 2); // Use null, 2 for readable formatting
  const blob = new Blob([jsonString], { type: 'application/json;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

