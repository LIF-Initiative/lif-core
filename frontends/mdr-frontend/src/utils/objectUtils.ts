/** Validate JSON string and return true if valid or throw error */
export const isValidJSON = (json: string): boolean => {
  try {
    JSON.parse(json);
  } catch (err) {
    throw new Error('Failed to parse JSON. The content is not valid JSON. Detaiils:' + (err as Error).message);
  }
  return true;
}
/** Validate JSON file and return true if valid or throw error */
export const isValidJSONFile = (file: File): boolean => {
  const reader = new FileReader();
  reader.onload = async (ev) => {
    // console.log('FileReader event:', ev);
    const isJsonType = file.type === 'application/json';
    const isJsonExt = file.name.endsWith('.json');
    if (!isJsonType && !isJsonExt) throw new Error('Invalid file type. Please upload a .json file.');

    try {
      const text = await file.text();
      JSON.parse(text);
    } catch (err) {
      throw new Error('Failed to parse file. The content is not valid JSON. Details:' + (err as Error).message);
    }  
  } //end reader.onload
  return true;
}