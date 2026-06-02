/**
 * Generate a unique ID for messages
 */
export const generateId = (): string => {
  return Math.random().toString(36).substring(2, 11);
};

/**
 * Format a timestamp for display
 */
export const formatTime = (date: Date): string => {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

/**
 * Simulate a delay (for bot responses)
 */
export const delay = (ms: number): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, ms));
};

/**
 * Calculate tokens (simplified version for demo)
 */
export const calculateTokens = (text: string): number => {
  return Math.ceil(text.split(/\s+/).length * 1.3);
};

/**
 * Calculate cost (simplified version for demo)
 */
export const calculateCost = (tokens: number): number => {
  return tokens * 0.000002; // $0.002 per 1000 tokens
};

/**
 * Pull quick-reply options out of an assistant message.
 *
 * The agent marks suggested replies by wrapping each in double angle brackets,
 * e.g. `<<Yes>>` `<<Tell me more about credentials>>`. We render those as
 * clickable buttons and strip the markers from the displayed text. Returns the
 * cleaned text plus the de-duplicated options (in first-seen order).
 */
export const extractOptions = (content: string): { text: string; options: string[] } => {
  const options: string[] = [];
  const seen = new Set<string>();

  const matches = content.matchAll(/<<\s*([^<>]+?)\s*>>/g);
  for (const match of matches) {
    const option = match[1].trim();
    const key = option.toLowerCase();
    if (option && !seen.has(key)) {
      seen.add(key);
      options.push(option);
    }
  }

  // Remove the markers, then collapse the whitespace/blank lines they leave behind.
  const text = content
    .replace(/<<\s*[^<>]+?\s*>>/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return { text, options };
};