const MAX_FILENAME_LENGTH = 255;
// Linux and macOS allow 255 UTF-8 bytes and Windows 255 UTF-16 units; a character is never fewer bytes than units.
// Browsers shorten a name near that limit themselves, cutting into the suffix (by 11 bytes in Chrome, 5 in Firefox,
// likely room for their .crdownload and .part download files), so the name is kept well under it.
const MAX_FILENAME_BYTES = 200;
// Held back from a capped suffix so the name always keeps at least its first character (at most 4 bytes in UTF-8).
const MAX_CHARACTER_BYTES = 4;
const WINDOWS_RESERVED_NAMES = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
  'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]);

/** Windows treats a device name before the first dot as the device, in any case: CON, con.json and CON.v2.json */
const isWindowsReservedName = (name: string): boolean =>
  WINDOWS_RESERVED_NAMES.has(name.split('.')[0].toUpperCase());

/** Convert a JSON object to a downloadable file */
export const downloadJsonFile = (jsonData: unknown, filename: string = 'data.json'): void => {
  if (!jsonData || typeof jsonData !== 'object') {
    console.error('Invalid JSON data provided for download.');
    return;
  }

  const jsonString = JSON.stringify(jsonData, null, 2);
  saveBlob(new Blob([jsonString], { type: 'application/json;charset=utf-8' }), sanitizeFilename(filename, 'data.json'));
};

/**
 * Download a blob without re-encoding it, so its bytes are kept exactly, and return the filename it was saved as.
 * The name is free text, such as a model's Name; the suffix says what the file is, such as
 * `_v1.0.lif-mdr-mapping-group.json`. Both are made safe, and a long name is shortened, never the suffix.
 */
export const downloadBlobFile = (blob: Blob, name: string, suffix: string = '.json'): string => {
  const filename = toDownloadFilename(name, suffix);
  saveBlob(blob, filename);
  return filename;
};

/** The filename downloadBlobFile saves as: name and suffix made safe, shortening the name to fit. */
export const toDownloadFilename = (name: string, suffix: string = '.json'): string => {
  // A suffix too long to fit, such as one with a very long version, keeps its end: the part that says what the file is.
  const safeSuffix = fitToBytes(cleanFilenamePart(suffix), MAX_FILENAME_BYTES - MAX_CHARACTER_BYTES, true);
  let base = cleanFilenamePart(name).replace(/^[.\s]+|[.\s]+$/g, '') || 'data';
  if (isWindowsReservedName(base)) base = `_${base}`; // Prevent reserved Windows device names
  return `${fitToBytes(base, MAX_FILENAME_BYTES - getByteLength(safeSuffix))}${safeSuffix}`;
};

const encoder = new TextEncoder();
const getByteLength = (text: string): number => encoder.encode(text).length;

/** The most whole characters from the start of text, or from its end, that fit in maxBytes of UTF-8. */
const fitToBytes = (text: string, maxBytes: number, keepEnd: boolean = false): string => {
  const characters = Array.from(text); // Code points, so a surrogate pair is never split
  if (keepEnd) characters.reverse();
  const kept: string[] = [];
  let bytes = 0;
  for (const character of characters) {
    bytes += getByteLength(character);
    if (bytes > maxBytes) break;
    kept.push(character);
  }
  if (keepEnd) kept.reverse();
  return kept.join('');
};

const saveBlob = (blob: Blob, safeFilename: string): void => {
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

/** Replace whitespace and remove the characters no major operating system allows in a filename */
const cleanFilenamePart = (input: string): string => {
  let name = input.trim();
  name = name.replace(/\s+/g, '_'); // Replace all whitespace runs with underscores
  // Control characters (\x00-\x1F) are invalid in filenames on every major OS.
  // eslint-disable-next-line no-control-regex
  name = name.replace(/[<>:"/\\|?*\x00-\x1F]/g, ''); // Remove path separators and invalid chars
  return name.replace(/_+/g, '_'); // Collapse repeated underscores
};

/** Make a filename safe across major operating systems */
const sanitizeFilename = (input: string, fallback: string = 'data.json'): string => {
  if (!input || typeof input !== 'string') return fallback;

  let name = cleanFilenamePart(input);
  name = name.replace(/^[.\s]+|[.\s]+$/g, ''); // Remove leading/trailing dots and spaces
  if (!name) return fallback;  // If empty after sanitizing, use fallback

  const lastDot = name.lastIndexOf('.'); // Split extension from basename
  let ext = lastDot > 0 ? name.slice(lastDot) : '';
  ext = '.json'; // Force .json extension
  const maxBaseLength = MAX_FILENAME_LENGTH - ext.length;
  let base = lastDot > 0 ? name.slice(0, lastDot) : name;
  if (isWindowsReservedName(base)) base = `_${base}`; // Prevent reserved Windows device names
  base = base.slice(0, maxBaseLength); // Enforce max length
  if (!base) base = 'data'; // Final fallback if base becomes empty

  return `${base}${ext}`;
};
