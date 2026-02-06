import { MutableRefObject, useCallback, useEffect, useLayoutEffect, useState } from 'react';
import { buildAttributeLookupKey, apiPathToDotFormat } from '../../../../utils/entityIdPath';

export type WirePath = {
  /** Unique id for SVG keying; now derived from source/target named paths */
  id: string;
  /** SVG path data */
  d: string;
  className?: string;
  /** Numeric source attribute id */
  srcId: number;
  /** Numeric target attribute id */
  tgtId: number;
  /** Transformation id */
  transId?: number;
  /** Dot-delimited named entity + attribute path for source (e.g. Assessment.Organization.name) */
  srcPathName?: string;
  /** Dot-delimited named entity + attribute path for target */
  tgtPathName?: string;
  /** Raw numeric id path for source (EntityIdPath as returned by API) */
  srcEntityIdPath?: string;
  /** Raw numeric id path for target */
  tgtEntityIdPath?: string;
  /** Composite key for stable hover matching */
  srcKey?: string;
  tgtKey?: string;
};

type UseMappingWiresArgs<TTrans> = {
  transformations: TTrans[];
  containerRef: MutableRefObject<HTMLElement | null>;
  wiresSlotRef: MutableRefObject<HTMLElement | null>;
  leftScrollRef: MutableRefObject<HTMLElement | null>;
  rightScrollRef: MutableRefObject<HTMLElement | null>;
  attrElementsLeft: MutableRefObject<Map<string, HTMLElement>>;
  attrElementsRight: MutableRefObject<Map<string, HTMLElement>>;
  recomputeDeps?: any[];
  /**
   * Builder that converts an EntityIdPath (id path) + attribute id into a named path (entity names + attribute name).
   * Should return something like EntityA.EntityB.Attribute.
   */
  pathNameBuilder?: (entityIdPath?: string | null, attributeId?: number | null, side?: 'source' | 'target') => string | null | undefined;
};

export function useMappingWires<TTrans extends { Id: number; TargetAttribute?: any; SourceAttributes?: any }>(
  args: UseMappingWiresArgs<TTrans>
) {
  const {
    transformations,
    containerRef,
    wiresSlotRef,
    leftScrollRef,
    rightScrollRef,
    attrElementsLeft,
    attrElementsRight,
    recomputeDeps = [],
    pathNameBuilder,
  } = args;

  const [wirePaths, setWirePaths] = useState<WirePath[]>([]);

  const computeWires = useCallback(() => {
    const containerRect = (wiresSlotRef.current || containerRef.current)?.getBoundingClientRect();
    if (!containerRect) return;
    const leftScrollRect = leftScrollRef.current?.getBoundingClientRect();
    const rightScrollRect = rightScrollRef.current?.getBoundingClientRect();
    const paths: WirePath[] = [];
    transformations.forEach((t: any) => {
      const sources: any[] = Array.isArray((t as any).SourceAttributes)
        ? ((t as any).SourceAttributes as any[])
        : [];
      const tgtId = t.TargetAttribute?.AttributeId;
      if (!tgtId || sources.length === 0) return;
      // Use buildAttributeLookupKey to normalize EntityIdPath (handles both old dot and new comma formats)
      const tgtKey = buildAttributeLookupKey(t.TargetAttribute?.EntityIdPath, tgtId);
      const rightEl = attrElementsRight.current.get(tgtKey) || attrElementsRight.current.get(String(tgtId));
      if (!rightEl) {
        // Log for debugging when EntityIdPath parsing fails (legacy data or bad format)
        if (t.TargetAttribute?.EntityIdPath) {
          console.warn(`useMappingWires: Could not find element for target path "${t.TargetAttribute?.EntityIdPath}" (key: ${tgtKey}), skipping wire`);
        }
        return;
      }
      const rightDot = rightEl.querySelector<HTMLElement>('.mappings-column__dot--start');
      const rb = (rightDot || rightEl).getBoundingClientRect();
      const endX = rb.left + rb.width / 2 - containerRect.left;
      const endY = rb.top + rb.height / 2 - containerRect.top;
      const tgtPathName = pathNameBuilder?.(t.TargetAttribute?.EntityIdPath, tgtId, 'target') || undefined;
      sources.forEach((srcAttr: any, idx: number) => {
        const srcId = srcAttr?.AttributeId;
        if (!srcId) return;
        // Use buildAttributeLookupKey to normalize EntityIdPath (handles both old dot and new comma formats)
        const srcKey = buildAttributeLookupKey(srcAttr?.EntityIdPath, srcId);
        const leftEl = attrElementsLeft.current.get(srcKey) || attrElementsLeft.current.get(String(srcId));
        if (!leftEl) {
          // Log for debugging when EntityIdPath parsing fails (legacy data or bad format)
          if (srcAttr?.EntityIdPath) {
            console.warn(`useMappingWires: Could not find element for source path "${srcAttr?.EntityIdPath}" (key: ${srcKey}), skipping wire`);
          }
          return;
        }
        const leftDot = leftEl.querySelector<HTMLElement>('.mappings-column__dot--end');
        const lb = (leftDot || leftEl).getBoundingClientRect();
        const startX = lb.left + lb.width / 2 - containerRect.left;
        const startY = lb.top + lb.height / 2 - containerRect.top;
        const dx = endX - startX;
        const c1x = startX + dx * 0.35;
        const c2x = endX - dx * 0.35;
        const path = `M ${startX} ${startY} C ${c1x} ${startY}, ${c2x} ${endY}, ${endX} ${endY}`;
        let className: string | undefined;
        if (
          (leftScrollRect && (startY + containerRect.top < leftScrollRect.top || startY + containerRect.top > leftScrollRect.bottom)) ||
          (rightScrollRect && (endY + containerRect.top < rightScrollRect.top || endY + containerRect.top > rightScrollRect.bottom))
        ) {
          className = 'mappings-wire mappings-wire--offscreen';
        }
        const srcPathName = pathNameBuilder?.(srcAttr?.EntityIdPath, srcId, 'source') || undefined;
        // Compose semantic id: sourceNamedPath->targetNamedPath (fallback to numeric ids if needed)
        const semanticId = `${srcPathName || srcAttr?.EntityIdPath || srcId}->${tgtPathName || t.TargetAttribute?.EntityIdPath || tgtId}`;
        // Ensure uniqueness per transformation+index in case of duplicate semantic pairs
        const id = `wire:${t.Id}:${idx}:${semanticId}`;
  paths.push({ id, d: path, className, srcId, tgtId, transId: t.Id, srcPathName, tgtPathName, srcEntityIdPath: srcAttr?.EntityIdPath, tgtEntityIdPath: t.TargetAttribute?.EntityIdPath, srcKey, tgtKey });
      });
    });
    setWirePaths(paths);
  }, [transformations, attrElementsLeft, attrElementsRight, leftScrollRef, rightScrollRef, wiresSlotRef, containerRef, pathNameBuilder]);

  useLayoutEffect(() => {
    computeWires();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [computeWires, ...recomputeDeps]);

  useEffect(() => {
    const handle = () => computeWires();
    window.addEventListener('resize', handle);
    const ls = leftScrollRef.current;
    const rs = rightScrollRef.current;
    ls?.addEventListener('scroll', handle);
    rs?.addEventListener('scroll', handle);
    return () => {
      window.removeEventListener('resize', handle);
      ls?.removeEventListener('scroll', handle);
      rs?.removeEventListener('scroll', handle);
    };
  }, [computeWires, leftScrollRef, rightScrollRef]);

  return { wirePaths, computeWires };
}

export default useMappingWires;
