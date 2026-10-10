import { useMemo } from "react";
import type { KeywordSearchItem } from "@/components/KeywordSearch/KeywordSearch";
import type { DataModelWithDetailsDTO } from "@/types";

/**
 * Build KeywordSearchItem[] from a DataModelWithDetailsDTO.
 * Includes one entity item per entity and one item per attribute.
 */
export default function useSearchItems(
  model: DataModelWithDetailsDTO | null
): KeywordSearchItem[] {
  return useMemo(() => {
    if (!model?.Entities?.length) return [];
    return model.Entities.flatMap((ea) => {
      const entityItem: KeywordSearchItem = {
        id: `entity-${ea.Entity.Id}`,
        label: String(ea.Entity.Name || ''),
        kind: 'entity',
        scrollId: ea.Entity.Id,
      };
      const attrItems: KeywordSearchItem[] = (ea.Attributes ?? []).map((a) => ({
        id: a.Id,
        label: String(a.Name || ''),
        kind: 'attribute',
        scrollId: a.Id,
      }));
      return [entityItem, ...attrItems];
    });
  }, [model]);
}
