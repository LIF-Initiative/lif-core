/**
 * Utility functions for handling the portable EntityIdPath format.
 *
 * UNIFIED FORMAT: Both API format and internal PathId use comma-separated numeric IDs.
 * The last element is negative if it represents an attribute ID.
 *
 * Examples:
 *   - Entity path ending in attribute: "654,22,6,-352"
 *   - Entity path ending in entity:    "654,22,6"
 *   - Internal PathId (same format):   "654,22,6"
 *
 * NOTE: Legacy formats (dot-separated like "654.22.6" or name-based paths like
 * "Person.CredentialAward") are NOT supported. The backend should migrate any
 * existing data to the comma-separated format. Legacy paths will trigger a
 * console warning and be skipped.
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
 * Check if a path string uses the legacy dot-separated format.
 * Legacy format was: "Entity.Child.attribute" (names) or "4.238.6" (IDs with dots)
 * This is used for detection/warning purposes only - legacy format is NOT supported.
 */
export function isLegacyDotFormat(path: string | null | undefined): boolean {
  if (!path) return false;
  const trimmed = path.trim();
  // Legacy format uses dots, new format uses commas
  return trimmed.includes('.') && !trimmed.includes(',');
}

/**
 * Check if a path string uses the supported comma-separated format.
 */
export function isNewCommaFormat(path: string | null | undefined): boolean {
  if (!path) return false;
  return path.trim().includes(',');
}

/**
 * Parse an EntityIdPath from the API (comma-separated format) into its components.
 *
 * ONLY supports the comma-separated format (e.g., "654,22,6,-352").
 * Legacy formats (dot-separated or name-based) are NOT supported and will
 * trigger a console warning. Backend migration should convert existing data.
 *
 * @param path The EntityIdPath string from the API
 * @returns Parsed path components, or null if parsing fails or legacy format encountered
 */
export function parseEntityIdPath(path: string | null | undefined): ParsedEntityIdPath | null {
  if (!path) return null;

  const trimmed = path.trim();
  if (!trimmed) return null;

  try {
    // Check for legacy dot-separated format - NOT supported
    if (isLegacyDotFormat(trimmed)) {
      console.warn(
        `EntityIdPath: Encountered legacy dot-separated format: "${path}". ` +
        `This format is not supported. Backend data migration is required to convert to comma-separated format.`
      );
      return null;
    }

    let parts: string[];

    if (isNewCommaFormat(trimmed)) {
      // Comma-separated format: "654,22,6,-352"
      parts = trimmed.split(',').map((s) => s.trim()).filter(Boolean);
    } else {
      // Single element - check if numeric
      parts = [trimmed];
    }

    if (parts.length === 0) return null;

    // Check if all parts are numeric
    const allNumeric = parts.every((p) => /^-?\d+$/.test(p));

    if (!allNumeric) {
      // Non-numeric format - cannot parse
      console.warn(
        `EntityIdPath: Encountered non-numeric path format: "${path}". ` +
        `This is a legacy format that requires backend migration to comma-separated numeric format.`
      );
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
 * Append an attribute ID to a PathId to create a full EntityIdPath.
 * Since PathId and API format are now both comma-separated, this just appends
 * the negative attribute ID.
 *
 * @param pathId Internal PathId like "654,22,6" (comma-separated entity IDs)
 * @param attributeId Attribute ID to append as negative
 * @returns Full EntityIdPath like "654,22,6,-352"
 */
export function appendAttributeToPath(pathId: string | null | undefined, attributeId: number | null | undefined): string {
  if (!attributeId) {
    return pathId || '';
  }
  
  const negAttr = -Math.abs(attributeId);
  
  if (!pathId) {
    return String(negAttr);
  }
  
  return `${pathId},${negAttr}`;
}

/**
 * @deprecated Use appendAttributeToPath instead. This function exists only for backward compatibility.
 */
export function dotPathToApiFormat(pathId: string | null | undefined, attributeId?: number): string {
  return appendAttributeToPath(pathId, attributeId);
}

/**
 * Parse an API format EntityIdPath and extract the entity path and attribute ID.
 * Since internal PathId and API format are now unified (comma-separated), this
 * returns the entity path in the same comma-separated format.
 *
 * @param apiPath API format path like "654,22,6,-352"
 * @returns Entity path as comma-separated string and extracted attributeId
 * @deprecated Renamed from apiPathToDotFormat. The dotPath field now contains comma-separated format.
 */
export function apiPathToDotFormat(apiPath: string | null | undefined): { dotPath: string; attributeId?: number } {
  const parsed = parseEntityIdPath(apiPath);
  if (!parsed) {
    return { dotPath: '', attributeId: undefined };
  }

  return {
    // Now returns comma-separated format (unified with internal PathId)
    dotPath: parsed.entityIds.join(','),
    attributeId: parsed.attributeId,
  };
}

/**
 * Build a lookup key for wire matching from an EntityIdPath and attribute ID.
 * Used to match transformation attributes with DOM elements.
 *
 * Uses unified comma-separated format for both API paths and internal PathId.
 * Legacy dot-separated formats will trigger a warning and return an empty key (wire will not be drawn).
 *
 * @param entityIdPath The EntityIdPath (comma-separated format)
 * @param attributeId The attribute ID
 * @returns A consistent lookup key string like "654,22,6|352", or empty if legacy format
 */
export function buildAttributeLookupKey(
  entityIdPath: string | null | undefined,
  attributeId: number | null | undefined
): string {
  if (!attributeId) return '';

  // Parse the path to normalize it
  let normalizedPath = '';

  if (entityIdPath) {
    // Check for legacy format first and warn
    if (isLegacyDotFormat(entityIdPath)) {
      // Return empty - wire won't be drawn for legacy format
      return '';
    }

    // Parse to get entity IDs and rebuild as comma-separated
    const parsed = parseEntityIdPath(entityIdPath);
    if (parsed && parsed.entityIds.length > 0) {
      normalizedPath = parsed.entityIds.join(',');
    } else if (!isNewCommaFormat(entityIdPath)) {
      // Single numeric value - use as-is
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
