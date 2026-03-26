/** Convert a JSON object to a downloadable file */
export const downloadJsonFile = (jsonData: unknown, filename: string = 'data.json'): void => {
  if (!jsonData || typeof jsonData !== 'object') {
    console.error('Invalid JSON data provided for download.');
    return;
  }

  const safeFilename = sanitizeFilename(filename, 'data.json');
  const jsonString = JSON.stringify(jsonData, null, 2);
  const blob = new Blob([jsonString], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = safeFilename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
};

/** Make a filename safe across major operating systems */
const sanitizeFilename = (input: string, fallback: string = 'data.json'): string => {
  if (!input || typeof input !== 'string') return fallback;
  const MAX_FILENAME_LENGTH = 255;
  const WINDOWS_RESERVED_NAMES = new Set([
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
  ]);

  let name = input.trim();
  name = name.replace(/\s+/g, '_'); // Replace all whitespace runs with underscores
  name = name.replace(/[<>:"/\\|?*\x00-\x1F]/g, ''); // Remove path separators and invalid chars
  name = name.replace(/^[.\s]+|[.\s]+$/g, ''); // Remove leading/trailing dots and spaces
  name = name.replace(/_+/g, '_'); // Collapse repeated underscores
  if (!name) return fallback;  // If empty after sanitizing, use fallback

  const lastDot = name.lastIndexOf('.'); // Split extension from basename
  let ext = lastDot > 0 ? name.slice(lastDot) : '';
  ext = '.json'; // Force .json extension
  const maxBaseLength = MAX_FILENAME_LENGTH - ext.length;
  let base = lastDot > 0 ? name.slice(0, lastDot) : name;
  if (WINDOWS_RESERVED_NAMES.has(base.toUpperCase())) base = `_${base}`; // Prevent reserved Windows device names
  base = base.slice(0, maxBaseLength); // Enforce max length
  if (!base) base = 'data'; // Final fallback if base becomes empty

  return `${base}${ext}`;
};