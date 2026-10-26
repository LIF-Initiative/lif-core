export const errorToString = (error: any): string => {
  // Handle null/undefined
  if (!error) return "Unknown error";
  
  // Handle Axios errors (most common case)
  if (error.response) {
    // Server responded with error status
    const data = error.response.data;
    if (data?.detail) {
      let det = data.detail;
      if (Array.isArray(det) && det.length === 1) det = det[0];
      switch(typeof det) {
        case 'string': return String(det);
        case 'object':
          if (det.msg) return String(det.msg);
          try { return JSON.stringify(det); }
          catch { return "[Complex detail object]"; }
        default: 
          console.error("Unhandled error details:", det);
          return `See console for details.`;
      }
    }
    if (data?.message) return String(data.message);
    if (data?.error) return String(data.error);
    
    // Include status code for context
    const status = error.response.status;
    const statusText = error.response.statusText;
    
    if (typeof data === 'string') return `${status}: ${data}`;
    if (data && typeof data === 'object') {
      try {
        return `${status} ${statusText}: ${JSON.stringify(data)}`;
      } catch {
        return `${status} ${statusText}: [Complex Error Object]`;
      }
    }
    return `${status} ${statusText}`;
  }
  
  // Handle network errors
  if (error.request) {
    return "Network error: Unable to reach server";
  }
  
  // Handle standard Error objects
  if (error instanceof Error) {
    return error.message || "Unknown error occurred";
  }
  
  // Handle string errors
  if (typeof error === 'string') {
    return error;
  }
  
  // Last resort - try to serialize
  try {
    return JSON.stringify(error);
  } catch {
    return String(error) || "Unserializable error";
  }
};


/** Helpful for handling non-Axios responses */
export const throwCustomError = async (response: Response) => {
  const errData = await response.json().catch(() => null);
  const errResp = {...response, data: errData, };
  const errStr = errorToString({response: errResp}); // `HTTP ${response.status} error! ${await response.json()}`
  throw new Error(errStr);
};


/** Helpful for debugging object contents */
export const obj2Str = (e: object) => {
  if (!e || typeof e !== 'object') { console.warn("obj2Str called with non-object:", e); return ""; }
  const mapped = Object.keys(e).sort().map(k => {
    const v = (e as any)[k];
    const showLength = Array.isArray(v);
    return ` ${showLength ? `${k}.length` : k}: ${showLength ? v.length : v}`;
  });
  return `{\n${mapped.join(",\n ")}\n}`;
};
