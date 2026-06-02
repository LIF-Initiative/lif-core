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
 * e.g. `<<Yes>>` `<<Tell me more about credentials>>`, and the prompts place
 * them at the very end of the response. We only parse a *trailing run* of
 * markers — so markers that appear mid-message (e.g. inside a code example) or
 * a dangling marker left by a truncated response are left in the text untouched
 * rather than corrupting it. Returns the cleaned text plus the de-duplicated
 * options (first-seen order).
 */
export const extractOptions = (content: string): { text: string; options: string[] } => {
  // Drop a dangling, unclosed marker from a truncated response (e.g. "<<Tell me mo").
  const cleaned = content.replace(/<<[^<>\n]*$/, '');

  // Match the trailing run of complete markers (and the whitespace before it).
  const trailing = cleaned.match(/(?:\s*<<[^<>\n]+?>>)+\s*$/);
  if (!trailing) {
    return { text: cleaned.trim(), options: [] };
  }

  const options: string[] = [];
  const seen = new Set<string>();
  for (const match of trailing[0].matchAll(/<<\s*([^<>\n]+?)\s*>>/g)) {
    const option = match[1].trim();
    const key = option.toLowerCase();
    if (option && !seen.has(key)) {
      seen.add(key);
      options.push(option);
    }
  }

  return { text: cleaned.slice(0, trailing.index).trim(), options };
};
