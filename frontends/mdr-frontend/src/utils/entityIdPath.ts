/**
 * Utility functions for handling the portable EntityIdPath format.
 *
 * New API format: comma-separated numeric IDs where the last element is
 * negative if it represents an attribute ID.
 *
 * Examples:
 *   - Entity path ending in attribute: "654,22,6,-352"
 *   - Entity path ending in entity:    "654,22,6,6543"
 *
 * Internal format (PathId): dot-separated entity IDs, e.g., "654.22.6"
 */

export interface ParsedEntityIdPath {
  /** Array of entity IDs in the path (all positive) */
  entityIds: number[];
  /** The attribute ID if the path ends with an attribute (originally negative in the path) */
  attributeId?: number;
  /** Whether this path ends with an entity (vs an attribute) */
  endsWithEntity: boolean;
}

/**
 * Check if a path string uses the old dot-separated format.
 * Old format was: "Entity.Child.attribute" (names) or "4.238.6" (IDs with dots)
 */
export function isOldDotFormat(path: string | null | undefined): boolean {
  if (!path) return false;
  const trimmed = path.trim();
  // Old format uses dots, new format uses commas
  return trimmed.includes('.') && !trimmed.includes(',');
}

/**
 * Check if a path string uses the new comma-separated format.
 */
export function isNewCommaFormat(path: string | null | undefined): boolean {
  if (!path) return false;
  return path.trim().includes(',');
}

/**
 * Parse an EntityIdPath from the API (comma-separated format) into its components.
 * Handles both old dot format and new comma format for backwards compatibility.
 *
 * @param path The EntityIdPath string from the API
 * @returns Parsed path components, or null if parsing fails
 */
export function parseEntityIdPath(path: string | null | undefined): ParsedEntityIdPath | null {
  if (!path) return null;

  const trimmed = path.trim();
  if (!trimmed) return null;

  try {
    let parts: string[];

    if (isNewCommaFormat(trimmed)) {
      // New comma-separated format: "654,22,6,-352"
      parts = trimmed.split(',').map((s) => s.trim()).filter(Boolean);
    } else if (isOldDotFormat(trimmed)) {
      // Old dot-separated format: "4.238.6" or "Person.Child.attr"
      parts = trimmed.split('.').map((s) => s.trim()).filter(Boolean);
    } else {
      // Single element
      parts = [trimmed];
    }

    if (parts.length === 0) return null;

    // Check if all parts are numeric (handles both old numeric dot and new comma format)
    const allNumeric = parts.every((p) => /^-?\d+$/.test(p));

    if (!allNumeric) {
      // Old name-based format - can't parse into IDs, log and skip
      console.warn(`EntityIdPath uses old name-based format, cannot parse: "${path}"`);
      return null;
    }

    const numbers = parts.map((p) => parseInt(p, 10));
    const lastNum = numbers[numbers.length - 1];

    if (lastNum < 0) {
      // Last element is negative = attribute ID
      return {
        entityIds: numbers.slice(0, -1),
        attributeId: Math.abs(lastNum),
        endsWithEntity: false,
      };
    } else {
      // All positive = path ends with an entity
      return {
        entityIds: numbers,
        attributeId: undefined,
        endsWithEntity: true,
      };
    }
  } catch (e) {
    console.warn(`Failed to parse EntityIdPath: "${path}"`, e);
    return null;
  }
}

/**
 * Build an EntityIdPath string in the new API format (comma-separated).
 *
 * @param entityIds Array of entity IDs in the path
 * @param attributeId Optional attribute ID (will be stored as negative)
 * @returns Comma-separated EntityIdPath string
 */
export function buildEntityIdPath(entityIds: number[], attributeId?: number): string {
  if (!entityIds || entityIds.length === 0) {
    if (attributeId) {
      // Path with just an attribute (edge case, currently out of scope)
      return String(-Math.abs(attributeId));
    }
    return '';
  }

  const parts = [...entityIds];
  if (attributeId !== undefined && attributeId !== null) {
    // Append attribute as negative number
    parts.push(-Math.abs(attributeId));
  }

  return parts.join(',');
}

/**
 * Convert an internal PathId (dot-separated entity IDs) to API format (comma-separated).
 * Optionally append an attribute ID as a negative number.
 *
 * @param dotPathId Internal PathId like "654.22.6"
 * @param attributeId Optional attribute ID to append as negative
 * @returns API format EntityIdPath like "654,22,6,-352"
 */
export function dotPathToApiFormat(dotPathId: string | null | undefined, attributeId?: number): string {
  if (!dotPathId) {
    // No entity path provided - this likely means the path lookup failed
    console.warn(`dotPathToApiFormat: No entity path provided for attributeId=${attributeId}. Returning just -attributeId.`);
    if (attributeId) {
      return String(-Math.abs(attributeId));
    }
    return '';
  }

  const parts = dotPathId
    .split('.')
    .map((s) => s.trim())
    .filter(Boolean);

  // Validate all parts are numeric
  const numericParts = parts.filter((p) => /^\d+$/.test(p)).map((p) => parseInt(p, 10));

  if (numericParts.length !== parts.length) {
    console.warn(`dotPathToApiFormat: PathId contains non-numeric segments: "${dotPathId}". Only numeric parts will be used.`);
  }

  // If no numeric parts found (e.g., path was all names like "Person.Assessment"),
  // we can't build a valid numeric path
  if (numericParts.length === 0) {
    console.warn(`dotPathToApiFormat: Could not extract any numeric IDs from path "${dotPathId}". attributeId=${attributeId}`);
    if (attributeId) {
      return String(-Math.abs(attributeId));
    }
    return '';
  }

  if (attributeId !== undefined && attributeId !== null) {
    numericParts.push(-Math.abs(attributeId));
  }

  return numericParts.join(',');
}

/**
 * Convert an API format EntityIdPath (comma-separated) to internal PathId format (dot-separated).
 * Strips off the attribute ID (negative number) if present.
 *
 * @param apiPath API format path like "654,22,6,-352"
 * @returns Internal PathId like "654.22.6" and extracted attributeId
 */
export function apiPathToDotFormat(apiPath: string | null | undefined): { dotPath: string; attributeId?: number } {
  const parsed = parseEntityIdPath(apiPath);
  if (!parsed) {
    return { dotPath: '', attributeId: undefined };
  }

  return {
    dotPath: parsed.entityIds.join('.'),
    attributeId: parsed.attributeId,
  };
}

/**
 * Build a lookup key for wire matching from an EntityIdPath and attribute ID.
 * Used to match transformation attributes with DOM elements.
 *
 * @param entityIdPath The EntityIdPath from API (or internal PathId)
 * @param attributeId The attribute ID
 * @returns A consistent lookup key string
 */
export function buildAttributeLookupKey(
  entityIdPath: string | null | undefined,
  attributeId: number | null | undefined
): string {
  if (!attributeId) return '';

  // Normalize the path to internal dot format for consistent lookups
  let normalizedPath = '';

  if (entityIdPath) {
    if (isNewCommaFormat(entityIdPath)) {
      // Convert API format to internal format
      const { dotPath } = apiPathToDotFormat(entityIdPath);
      normalizedPath = dotPath;
    } else if (isOldDotFormat(entityIdPath)) {
      // Check if it's numeric dot format vs name-based
      const parts = entityIdPath.split('.').map((s) => s.trim()).filter(Boolean);
      if (parts.every((p) => /^\d+$/.test(p))) {
        // Already in internal numeric dot format
        normalizedPath = entityIdPath;
      } else {
        // Name-based format - can't normalize, use as-is for fallback
        normalizedPath = entityIdPath;
      }
    } else {
      normalizedPath = entityIdPath;
    }
  }

  return normalizedPath ? `${normalizedPath}|${attributeId}` : String(attributeId);
}

/**
 * Extract entity IDs from an internal PathId or API EntityIdPath for entity lookups.
 *
 * @param path Either internal PathId ("654.22.6") or API path ("654,22,6,-352")
 * @returns Array of entity IDs
 */
export function extractEntityIds(path: string | null | undefined): number[] {
  const parsed = parseEntityIdPath(path);
  return parsed?.entityIds ?? [];
}
