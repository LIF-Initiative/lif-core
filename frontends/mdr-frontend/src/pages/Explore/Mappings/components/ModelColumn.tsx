import React, { useCallback } from 'react';
import type {
    DataModelWithDetailsDTO,
    DataModelWithDetailsWithTree,
    AttributeDTO,
    EntityTreeNode,
} from '../../../../types';
import { extractEntityPath, isNewCommaFormat } from '../../../../utils/entityIdPath';

// Types re-declared locally to avoid tight coupling; import actual interfaces from caller when wiring up
export interface DisplayTransformationDataLike {
    Id: number;
    TargetAttribute?: ({ AttributeId?: number } & Record<string, any>) | null;
    SourceAttributes?: Array<{ AttributeId?: number } & Record<string, any>>;
}

export interface SelectionContextLike {
    selectedTargetAttrId: number | null;
    selectedTargetAttrPath?: string | null;
    setSelectedTargetAttrId: React.Dispatch<
        React.SetStateAction<number | null>
    >;
    setSelectedTargetAttrPath?: React.Dispatch<
        React.SetStateAction<string | null>
    >;
    selectionIndex: number;
    setSelectionIndex: React.Dispatch<React.SetStateAction<number>>;
    selectionAll: boolean;
    setSelectionAll: React.Dispatch<React.SetStateAction<boolean>>;
    selectedTransformationIds: Set<number>;
    setSelectedTransformationIds: React.Dispatch<
        React.SetStateAction<Set<number>>
    >;
    setReassignActive: React.Dispatch<React.SetStateAction<boolean>>;
    setReassignTransformations: React.Dispatch<
        React.SetStateAction<DisplayTransformationDataLike[]>
    >;
    reassignHoverTargetId: number | null;
    reassignHoverTargetPath?: string | null;
    prepareReassign?: (
        e: React.MouseEvent,
        transforms: DisplayTransformationDataLike[]
    ) => void;
    // New: allow parent to control wire source selection set when selecting via target dot
    setSelectedWireSourceAttrIds?: React.Dispatch<React.SetStateAction<Set<number>>>;
}

export interface ModelColumnProps {
    title: string;
    model: DataModelWithDetailsDTO | null;
    modelWithTree?: DataModelWithDetailsWithTree | null;
    query: string;
    onQueryChange: (q: string) => void;
    // Not used inside this body-only component; accept any[] to avoid type coupling
    searchItems?: any[];
    mappedAttrIds: Set<number>;
    side: 'left' | 'right';
    scrollRef: React.RefObject<HTMLDivElement>;
    registerAttrElement: (
        side: 'left' | 'right',
        id: number,
        el: HTMLElement | null,
        entityPath?: string | null
    ) => void;
    onHoverAttr: (key: string | null) => void;
    dragTargetAttrId?: number | null;
    dragTargetPath?: string | null;
    onStartDrag?: (attr: AttributeDTO, entityPath?: string | null) => void;
    onSourceDotDoubleClick?: (attrId: number) => void;
    transformations?: DisplayTransformationDataLike[];
    headerNameNode?: React.ReactNode;
    loading?: boolean;
    disableInteractions?: boolean;
    selectionContext?: Omit<
        SelectionContextLike,
        'setReassignTransformations'
    > & {
        setReassignTransformations: React.Dispatch<React.SetStateAction<any[]>>;
    };
    capOnly?: boolean;
    bodyOnly?: boolean;
}

const ModelColumn: React.FC<ModelColumnProps> = ({
    title,
    model,
    modelWithTree,
    query,
    onQueryChange,
    searchItems,
    mappedAttrIds,
    side,
    scrollRef,
    registerAttrElement,
    onHoverAttr,
    dragTargetAttrId,
    dragTargetPath,
    onStartDrag,
    onSourceDotDoubleClick,
    transformations = [],
    headerNameNode,
    loading,
    disableInteractions,
    selectionContext,
    capOnly,
    bodyOnly,
}) => {
    const items = (model?.Entities ?? []).map((ea) => ({
        entity: ea.Entity,
        attributes: ea.Attributes ?? [],
    }));

    const renderTree = useCallback(
        (nodes: EntityTreeNode[] | undefined) => {
            if (!nodes || !nodes.length) return null;
            return nodes.map((node, idx) => {
                const ewa: any = node.Entity;
                const entityId: number = ewa?.Entity ? ewa.Entity.Id : ewa?.Id;
                const entityName: string = ewa?.Entity
                    ? ewa.Entity.Name
                    : ewa?.Name;
                const attributes: AttributeDTO[] = (ewa?.Attributes ??
                    []) as AttributeDTO[];
                // PathId can repeat for references/reuse; compose a more unique, but stable-enough key per map position
                const entityKey = `${node.PathId || ''}|${entityId}|${idx}`;
                return (
                    <div
                        key={entityKey}
                        className="mappings-entity"
                        data-entity-id={entityId}
                        data-entity-path={node.PathId}
                    >
                        <div className="mappings-entity__header">
                            <span className="mappings-square mappings-square--entity" />
                            <span className="mappings-entity__name">
                                {entityName}
                            </span>
                        </div>
                        <div className="mappings-attributes">
                            {attributes.map((attr) => {
                                // Path-specific mapped check so reused attributes at different paths don't all show as mapped
                                // Use PathId (comma-separated numeric) for matching against API data
                                const currentPath = node.PathId;
                                // Helper to normalize API EntityIdPath for comparison (unified comma format)
                                const normalizeForComparison = (apiPath: string | null | undefined): string => {
                                    if (!apiPath) return '';
                                    if (isNewCommaFormat(apiPath)) {
                                        // Extract entity-only path from EntityIdPath (strips negative attribute suffix)
                                        return extractEntityPath(apiPath);
                                    }
                                    // For legacy name-based paths, we can't match against numeric PathId
                                    // Return the apiPath as-is (it won't match, which is correct behavior)
                                    return apiPath;
                                };
                                let isMapped = false;
                                if (transformations && transformations.length) {
                                    if (side === 'left') {
                                        isMapped = (transformations as any[]).some((t) =>
                                            Array.isArray((t as any).SourceAttributes) &&
                                            (t as any).SourceAttributes.some(
                                                (s: any) => s.AttributeId === attr.Id && normalizeForComparison(s.EntityIdPath) === currentPath
                                            )
                                        );
                                    } else {
                                        isMapped = (transformations as any[]).some((t: any) =>
                                            t.TargetAttribute?.AttributeId === attr.Id &&
                                            normalizeForComparison(t.TargetAttribute?.EntityIdPath) === currentPath
                                        );
                                    }
                                }
                                // Fallback: if no path info available, use provided set
                                if (!currentPath) {
                                    isMapped = mappedAttrIds.has(attr.Id);
                                }
                                const dotClass = isMapped
                                    ? 'mappings-column__dot mappings-column__dot--mapped'
                                    : 'mappings-column__dot mappings-column__dot--unmapped';
                                const inboundWires = (() => {
                                    if (side !== 'right')
                                        return [] as Array<{
                                            trans: DisplayTransformationDataLike;
                                            src: any;
                                        }>;
                                    const inboundTs = (
                                        transformations || []
                                    ).filter(
                                        (t) => {
                                            if (t.TargetAttribute?.AttributeId !== attr.Id) return false;
                                            // Also match entity path so same-AttributeId in different entities don't collide
                                            if (currentPath) {
                                                const tgtEntityIdPath = (t.TargetAttribute as any)?.EntityIdPath;
                                                if (tgtEntityIdPath) {
                                                    return normalizeForComparison(tgtEntityIdPath) === currentPath;
                                                }
                                            }
                                            return true;
                                        }
                                    );
                                    const wires: Array<{
                                        trans: DisplayTransformationDataLike;
                                        src: any;
                                    }> = [];
                                    inboundTs.forEach((t) => {
                                        const sources: any[] = Array.isArray((t as any).SourceAttributes)
                                            ? ((t as any).SourceAttributes as any[])
                                            : [];
                                        sources.forEach((s) => wires.push({ trans: t, src: s }));
                                    });
                                    return wires;
                                })();
                                const dotStart = side === 'right' && !disableInteractions ? (
                                    <span className="mappings-dot-wrapper">
                                        <span
                                            className={`${dotClass} mappings-column__dot--start`}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (!selectionContext) return;
                                                const {
                                                    selectedTargetAttrId, setSelectedTargetAttrId,
                                                    selectedTargetAttrPath, setSelectedTargetAttrPath,
                                                    selectionIndex, setSelectionIndex,
                                                    setSelectionAll,
                                                    setSelectedTransformationIds,
                                                    setSelectedWireSourceAttrIds,
                                                } = selectionContext as any;
                                                const SrcWireLength = inboundWires?.length || 0;
                                                if (!SrcWireLength) return;
                                                const inboundTsUnique = Array.from(new Set(inboundWires.map(w => w.trans.Id)));
                                                // Determine if this is the same target (same attr ID AND same entity path)
                                                const isSameTarget = selectedTargetAttrId === attr.Id &&
                                                    (selectedTargetAttrPath == null || selectedTargetAttrPath === currentPath);
                                                // Shift = select ALL transformations (all wires)
                                                if (e.shiftKey) {
                                                    setSelectedTargetAttrId(attr.Id);
                                                    if (setSelectedTargetAttrPath) setSelectedTargetAttrPath(currentPath || null);
                                                    setSelectionAll(true);
                                                    setSelectionIndex(SrcWireLength);
                                                    setSelectedTransformationIds(new Set(inboundTsUnique));
                                                    if (setSelectedWireSourceAttrIds) {
                                                        const firstTrans = inboundWires[0].trans;
                                                        const allSrcIds = new Set<number>((firstTrans.SourceAttributes || []).map((s: any) => s.AttributeId));
                                                        setSelectedWireSourceAttrIds(allSrcIds);
                                                    }
                                                    return;
                                                }
                                                setSelectionAll(false);
                                                // Initial select or different target: pick first transformation
                                                if (!isSameTarget) {
                                                    setSelectedTargetAttrId(attr.Id);
                                                    if (setSelectedTargetAttrPath) setSelectedTargetAttrPath(currentPath || null);
                                                    setSelectionIndex(0);
                                                    const firstTrans = inboundWires[0].trans;
                                                    setSelectedTransformationIds(new Set([firstTrans.Id]));
                                                    if (setSelectedWireSourceAttrIds) {
                                                        const firstSrc = (firstTrans.SourceAttributes || [])[0];
                                                        setSelectedWireSourceAttrIds(firstSrc?.AttributeId ? new Set([firstSrc.AttributeId]) : new Set());
                                                    }
                                                    return;
                                                }
                                                // Default case: cycle to next transformation (wrap)
                                                const nextIndex = (selectionIndex + 1) % (SrcWireLength+1);
                                                const SelectAllWires = (selectionIndex + 1) == SrcWireLength;
                                                if (SelectAllWires) {
                                                    // Select all wires
                                                    setSelectedTargetAttrId(attr.Id);
                                                    if (setSelectedTargetAttrPath) setSelectedTargetAttrPath(currentPath || null);
                                                    setSelectionAll(true);
                                                    setSelectionIndex(nextIndex);
                                                    setSelectedTransformationIds(new Set(inboundTsUnique));
                                                    if (setSelectedWireSourceAttrIds) {
                                                        const firstTrans = inboundWires[0].trans;
                                                        const allSrcIds = new Set<number>((firstTrans.SourceAttributes || []).map((s: any) => s.AttributeId));
                                                        setSelectedWireSourceAttrIds(allSrcIds);
                                                    }
                                                } else {
                                                    // Select next wire
                                                    setSelectionIndex(nextIndex);
                                                    const nextTrans = inboundWires[nextIndex].trans;
                                                    setSelectedTransformationIds(new Set([nextTrans.Id]));
                                                    if (setSelectedWireSourceAttrIds) {
                                                        const selectedSrc = (nextTrans.SourceAttributes || [])[nextIndex];
                                                        setSelectedWireSourceAttrIds(selectedSrc?.AttributeId ? new Set([selectedSrc.AttributeId]) : new Set());
                                                    }
                                                }

                                            }}
                                            onMouseDown={(e) => {
                                                if (!selectionContext) return;
                                                const { selectionAll, selectedTargetAttrId, selectedTransformationIds, prepareReassign } = selectionContext;
                                                if (side === 'right' && inboundWires.length > 0) {
                                                    let selectedWires: Array<{ trans: DisplayTransformationDataLike; src: any; }> = [];
                                                    if (selectionAll && selectedTargetAttrId === attr.Id) {
                                                        selectedWires = inboundWires;
                                                    } else if (selectedTransformationIds.size) {
                                                        const wire = inboundWires[Math.max(0, selectionContext.selectionIndex)];
                                                        if (wire) selectedWires = [wire];
                                                    } else if (inboundWires.length === 1) {
                                                        selectedWires = [inboundWires[0]];
                                                    }
                                                    if (selectedWires.length) {
                                                        const byTrans = new Map<number, { trans: DisplayTransformationDataLike; moveSources: any[]; }>();
                                                        selectedWires.forEach(({ trans, src }) => {
                                                            const list = byTrans.get(trans.Id) || { trans, moveSources: [] as any[] };
                                                            const payload = { AttributeId: src.AttributeId || src.Id, AttributeType: src.AttributeType || 'Source', EntityIdPath: (src as any)?.EntityIdPath } as any;
                                                            const key = (s: any) => `${s.EntityIdPath || ''}|${s.AttributeId}`;
                                                            if (!list.moveSources.some((s) => key(s) === key(payload))) list.moveSources.push(payload);
                                                            byTrans.set(trans.Id, list);
                                                        });
                                                        const moving = Array.from(byTrans.values()).map(v => ({ ...(v.trans as any), __moveSources: v.moveSources } as any));
                                                        e.preventDefault();
                                                        prepareReassign?.(e, moving);
                                                    }
                                                }
                                            }}
                                        />
                                    </span>
                                ) : null;
                                const dotEnd = (
                                    <span
                                        className={`${dotClass} mappings-column__dot--end`}
                                        onDoubleClick={(e) => {
                                            if (
                                                side === 'left' &&
                                                !disableInteractions &&
                                                onSourceDotDoubleClick
                                            ) {
                                                e.stopPropagation();
                                                onSourceDotDoubleClick(attr.Id);
                                            }
                                        }}
                                    />
                                );
                                return (
                                    <div
                                        key={`${entityKey}|attr|${attr.Id}|${attr.Name}`}
                                        className={`mappings-attr mappings-attr--${side} ${
                                            side === 'right' &&
                                            dragTargetAttrId === attr.Id &&
                                            dragTargetPath === node.PathId
                                                ? 'mappings-attr--drop-target'
                                                : ''
                                        }`}
                                        ref={(el) => {
                                            registerAttrElement(side, attr.Id, el, node.PathId);
                                        }}
                                        data-attr-id={attr.Id}
                                        data-entity-path={node.PathId || ''}
                                        onMouseEnter={() => {
                                            const key = `${node.PathId || ''}|${attr.Id}`;
                                            onHoverAttr(key);
                                        }}
                                        onMouseLeave={() => onHoverAttr(null)}
                                        onMouseDown={(e) => {
                                            if (
                                                side === 'left' &&
                                                onStartDrag
                                            ) {
                                                e.preventDefault();
                                                onStartDrag(attr, node.PathId);
                                            }
                                        }}
                                    >
                                        {side === 'right' ? (
                                            <>
                                                {dotStart}
                                                <span className="mappings-square mappings-square--attribute" />
                                                <span
                                                    className={`mappings-attr__name ${
                                                        selectionContext?.reassignHoverTargetId ===
                                                        attr.Id &&
                                                        (selectionContext?.reassignHoverTargetPath == null ||
                                                         selectionContext?.reassignHoverTargetPath === node.PathId)
                                                            ? 'mappings-attr--drop-target'
                                                            : ''
                                                    }`}
                                                >
                                                    {attr.Name}
                                                </span>
                                            </>
                                        ) : (
                                            <>
                                                <span className="mappings-square mappings-square--attribute" />
                                                <span className="mappings-attr__name">
                                                    {attr.Name}
                                                </span>
                                                {dotEnd}
                                            </>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                        {node.Children && node.Children.length > 0 && (
                            <div className="mappings-entity-children">
                                {renderTree(node.Children)}
                            </div>
                        )}
                    </div>
                );
            });
        },
        [
            mappedAttrIds,
            side,
            transformations,
            disableInteractions,
            selectionContext,
            dragTargetAttrId,
            registerAttrElement,
            onHoverAttr,
            onStartDrag,
            onSourceDotDoubleClick,
        ]
    );

    return (
        <section className="mappings-column">
            {/* Header slot is rendered by parent; keep body composition only */}
            {!capOnly && (
                <div
                    className={`mappings-column__scroll ${
                        side === 'left'
                            ? 'mappings-column__scroll--left-scrollbar'
                            : ''
                    }`}
                    ref={scrollRef}
                >
                    <div className="mappings-column__scroll-inner">
                        {loading && (
                            <div className="mappings-loading">
                                <span className="mappings-spinner" /> Loading{' '}
                                {side === 'left' ? 'source' : 'target'} model…
                            </div>
                        )}
                        {modelWithTree?.EntityTree &&
                        modelWithTree.EntityTree.length > 0
                            ? renderTree(modelWithTree.EntityTree)
                            : items.map(({ entity, attributes }) => (
                                  <div
                                      key={entity.Id}
                                      className="mappings-entity"
                                      data-entity-id={entity.Id}
                                  >
                                      <div className="mappings-entity__header">
                                          <span className="mappings-square mappings-square--entity" />
                                          <span className="mappings-entity__name">
                                              {entity.Name}
                                          </span>
                                      </div>
                                      <div className="mappings-attributes">
                                          {attributes.map(
                                              (attr: AttributeDTO) => {
                                                  const isMapped =
                                                      mappedAttrIds.has(
                                                          attr.Id
                                                      );
                                                  const dotClass = isMapped
                                                      ? 'mappings-column__dot mappings-column__dot--mapped'
                                                      : 'mappings-column__dot mappings-column__dot--unmapped';
                                                  const inboundWires = (() => {
                                                      if (side !== 'right')
                                                          return [] as Array<{
                                                              trans: DisplayTransformationDataLike;
                                                              src: any;
                                                          }>;
                                                      const inboundTs = (
                                                          transformations || []
                                                      ).filter(
                                                          (t) =>
                                                              t.TargetAttribute
                                                                  ?.AttributeId ===
                                                              attr.Id
                                                      );
                                                      const wires: Array<{
                                                          trans: DisplayTransformationDataLike;
                                                          src: any;
                                                      }> = [];
                                                      inboundTs.forEach((t) => {
                                                          const sources: any[] = Array.isArray((t as any).SourceAttributes)
                                                              ? ((t as any).SourceAttributes as any[])
                                                              : [];
                                                          sources.forEach((s) => wires.push({ trans: t, src: s }));
                                                      });
                                                      return wires;
                                                  })();
                                                  const dotStart =
                                                      side === 'right' &&
                                                      !disableInteractions ? (
                                                          <span
                                                              className={`${dotClass} mappings-column__dot--start`}
                                                              onClick={(e) => {
                                                                  e.stopPropagation();
                                                                  if (
                                                                      !selectionContext
                                                                  )
                                                                      return;
                                                                  const {
                                                                      selectedTargetAttrId,
                                                                      setSelectedTargetAttrId,
                                                                      selectionIndex,
                                                                      setSelectionIndex,
                                                                      selectionAll,
                                                                      setSelectionAll,
                                                                      setSelectedTransformationIds,
                                                                  } =
                                                                      selectionContext;
                                                                  if (
                                                                      inboundWires.length ===
                                                                      0
                                                                  )
                                                                      return;
                                                                  const inboundTsUnique =
                                                                      Array.from(
                                                                          new Set(
                                                                              inboundWires.map(
                                                                                  (
                                                                                      w
                                                                                  ) =>
                                                                                      w
                                                                                          .trans
                                                                                          .Id
                                                                              )
                                                                          )
                                                                      );
                                                                  if (
                                                                      inboundWires.length ===
                                                                      1
                                                                  ) {
                                                                      setSelectedTargetAttrId(
                                                                          attr.Id
                                                                      );
                                                                      setSelectionIndex(
                                                                          0
                                                                      );
                                                                      setSelectionAll(
                                                                          false
                                                                      );
                                                                      setSelectedTransformationIds(
                                                                          new Set(
                                                                              [
                                                                                  inboundWires[0]
                                                                                      .trans
                                                                                      .Id,
                                                                              ]
                                                                          )
                                                                      );
                                                                      return;
                                                                  }
                                                                  if (
                                                                      selectedTargetAttrId !==
                                                                      attr.Id
                                                                  ) {
                                                                      setSelectedTargetAttrId(
                                                                          attr.Id
                                                                      );
                                                                      setSelectionIndex(
                                                                          0
                                                                      );
                                                                      setSelectionAll(
                                                                          false
                                                                      );
                                                                      setSelectedTransformationIds(
                                                                          new Set(
                                                                              [
                                                                                  inboundWires[0]
                                                                                      .trans
                                                                                      .Id,
                                                                              ]
                                                                          )
                                                                      );
                                                                      return;
                                                                  }
                                                                  if (
                                                                      selectionAll
                                                                  ) {
                                                                      setSelectionAll(
                                                                          false
                                                                      );
                                                                      setSelectionIndex(
                                                                          0
                                                                      );
                                                                      setSelectedTransformationIds(
                                                                          new Set(
                                                                              [
                                                                                  inboundWires[0]
                                                                                      .trans
                                                                                      .Id,
                                                                              ]
                                                                          )
                                                                      );
                                                                      return;
                                                                  }
                                                                  if (
                                                                      selectionIndex <
                                                                      inboundWires.length -
                                                                          1
                                                                  ) {
                                                                      const next =
                                                                          selectionIndex +
                                                                          1;
                                                                      setSelectionIndex(
                                                                          next
                                                                      );
                                                                      setSelectedTransformationIds(
                                                                          new Set(
                                                                              [
                                                                                  inboundWires[
                                                                                      next
                                                                                  ]
                                                                                      .trans
                                                                                      .Id,
                                                                              ]
                                                                          )
                                                                      );
                                                                  } else {
                                                                      setSelectionAll(
                                                                          true
                                                                      );
                                                                      setSelectedTransformationIds(
                                                                          new Set(
                                                                              inboundTsUnique
                                                                          )
                                                                      );
                                                                  }
                                                              }}
                                                              onMouseDown={(
                                                                  e
                                                              ) => {
                                                                  if (
                                                                      !selectionContext
                                                                  )
                                                                      return;
                                                                  const {
                                                                      selectionAll,
                                                                      selectedTargetAttrId,
                                                                      selectedTransformationIds,
                                                                      prepareReassign,
                                                                  } =
                                                                      selectionContext;
                                                                  if (
                                                                      side ===
                                                                          'right' &&
                                                                      inboundWires.length >
                                                                          0
                                                                  ) {
                                                                      let selectedWires: Array<{
                                                                          trans: DisplayTransformationDataLike;
                                                                          src: any;
                                                                      }> = [];
                                                                      if (
                                                                          selectionAll &&
                                                                          selectedTargetAttrId ===
                                                                              attr.Id
                                                                      ) {
                                                                          selectedWires =
                                                                              inboundWires;
                                                                      } else if (
                                                                          selectedTransformationIds.size
                                                                      ) {
                                                                          const wire =
                                                                              inboundWires[
                                                                                  Math.max(
                                                                                      0,
                                                                                      selectionContext.selectionIndex
                                                                                  )
                                                                              ];
                                                                          if (
                                                                              wire
                                                                          )
                                                                              selectedWires =
                                                                                  [
                                                                                      wire,
                                                                                  ];
                                                                      } else if (
                                                                          inboundWires.length ===
                                                                          1
                                                                      ) {
                                                                          selectedWires =
                                                                              [
                                                                                  inboundWires[0],
                                                                              ];
                                                                      }
                                                                      if (
                                                                          selectedWires.length
                                                                      ) {
                                                                          const byTrans =
                                                                              new Map<
                                                                                  number,
                                                                                  {
                                                                                      trans: DisplayTransformationDataLike;
                                                                                      moveSources: any[];
                                                                                  }
                                                                              >();
                                                                          selectedWires.forEach(
                                                                              ({
                                                                                  trans,
                                                                                  src,
                                                                              }) => {
                                                                                  const list =
                                                                                      byTrans.get(
                                                                                          trans.Id
                                                                                      ) || {
                                                                                          trans,
                                                                                          moveSources:
                                                                                              [] as any[],
                                                                                      };
                                                                                  const payload =
                                                                                      {
                                                                                          AttributeId:
                                                                                              src.AttributeId ||
                                                                                              src.Id,
                                                                                          AttributeType:
                                                                                              src.AttributeType ||
                                                                                              'Source',
                                                                                          EntityIdPath:
                                                                                              (
                                                                                                  src as any
                                                                                              )
                                                                                                  ?.EntityIdPath,
                                                                                      } as any;
                                                                                  const key =
                                                                                      (
                                                                                          s: any
                                                                                      ) =>
                                                                                          `${
                                                                                              s.EntityIdPath ||
                                                                                              ''
                                                                                          }|${
                                                                                              s.AttributeId
                                                                                          }`;
                                                                                  if (
                                                                                      !list.moveSources.some(
                                                                                          (
                                                                                              s
                                                                                          ) =>
                                                                                              key(
                                                                                                  s
                                                                                              ) ===
                                                                                              key(
                                                                                                  payload
                                                                                              )
                                                                                      )
                                                                                  )
                                                                                      list.moveSources.push(
                                                                                          payload
                                                                                      );
                                                                                  byTrans.set(
                                                                                      trans.Id,
                                                                                      list
                                                                                  );
                                                                              }
                                                                          );
                                                                          const moving =
                                                                              Array.from(
                                                                                  byTrans.values()
                                                                              ).map(
                                                                                  (
                                                                                      v
                                                                                  ) =>
                                                                                      ({
                                                                                          ...(v.trans as any),
                                                                                          __moveSources:
                                                                                              v.moveSources,
                                                                                      } as any)
                                                                              );
                                                                          e.preventDefault();
                                                                          prepareReassign?.(
                                                                              e,
                                                                              moving
                                                                          );
                                                                      }
                                                                  }
                                                              }}
                                                          />
                                                      ) : null;
                                                  const dotEnd = (
                                                      <span
                                                          className={`${dotClass} mappings-column__dot--end`}
                                                          onDoubleClick={(
                                                              e
                                                          ) => {
                                                              if (
                                                                  side ===
                                                                      'left' &&
                                                                  !disableInteractions &&
                                                                  onSourceDotDoubleClick
                                                              ) {
                                                                  e.stopPropagation();
                                                                  onSourceDotDoubleClick(
                                                                      attr.Id
                                                                  );
                                                              }
                                                          }}
                                                      />
                                                  );
                                                  return (
                                                      <div
                                                          key={attr.Id}
                                                          className={`mappings-attr mappings-attr--${side} ${
                                                              side ===
                                                                  'right' &&
                                                              dragTargetAttrId ===
                                                                  attr.Id
                                                                  ? 'mappings-attr--drop-target'
                                                                  : ''
                                                          }`}
                                                          ref={(el) =>
                                                              registerAttrElement(
                                                                  side,
                                                                  attr.Id,
                                                                  el
                                                              )
                                                          }
                                                          data-attr-id={attr.Id}
                                                          onMouseEnter={() => {
                                                              const key = `|${attr.Id}`;
                                                              onHoverAttr(key);
                                                          }}
                                                          onMouseLeave={() =>
                                                              onHoverAttr(null)
                                                          }
                                                          onMouseDown={(e) => {
                                                              if (
                                                                  side ===
                                                                      'left' &&
                                                                  onStartDrag
                                                              ) {
                                                                  e.preventDefault();
                                                                  onStartDrag(
                                                                      attr
                                                                  );
                                                              }
                                                          }}
                                                      >
                                                          {side === 'right' ? (
                                                              <>
                                                                  {dotStart}
                                                                  <span className="mappings-square mappings-square--attribute" />
                                                                  <span
                                                                      className={`mappings-attr__name ${
                                                                          selectionContext?.reassignHoverTargetId ===
                                                                          attr.Id &&
                                                                          selectionContext?.reassignHoverTargetPath == null
                                                                              ? 'mappings-attr--drop-target'
                                                                              : ''
                                                                      }`}
                                                                  >
                                                                      {
                                                                          attr.Name
                                                                      }
                                                                  </span>
                                                              </>
                                                          ) : (
                                                              <>
                                                                  <span className="mappings-square mappings-square--attribute" />
                                                                  <span className="mappings-attr__name">
                                                                      {
                                                                          attr.Name
                                                                      }
                                                                  </span>
                                                                  {dotEnd}
                                                              </>
                                                          )}
                                                      </div>
                                                  );
                                              }
                                          )}
                                      </div>
                                  </div>
                              ))}
                        {!items.length && (
                            <div className="mappings-column__no-results">
                                No results
                            </div>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
};

export default ModelColumn;
