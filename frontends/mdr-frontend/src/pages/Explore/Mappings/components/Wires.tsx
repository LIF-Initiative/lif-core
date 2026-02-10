import React from 'react';

export type WirePath = {
  id: string;
  d: string;
  className?: string;
  srcId: number;
  tgtId: number;
  transId?: number;
  srcPathName?: string;
  tgtPathName?: string;
  srcEntityIdPath?: string;
  tgtEntityIdPath?: string;
  srcKey?: string; // PathId|AttrId composite for element registry matching
  tgtKey?: string;
};

export interface WiresProps {
  wirePaths: WirePath[];
  hoveredAttrId?: any; // maintain backward compatibility
  hoveredAttrKey?: string | null;
  selectedTransformationIds: Set<number>;
  selectedWireSourceAttrIds?: Set<number> | null;
  onWireClick: (
    transId: number,
    srcAttrId: number,
    e: React.MouseEvent<SVGPathElement, MouseEvent>
  ) => void;
  onWireDoubleClick: (transId: number, srcAttrId: number) => void;
  onWireMouseDown?: (
    transId: number,
    srcAttrId: number,
    e: React.MouseEvent<SVGPathElement, MouseEvent>
  ) => void;
  dragPath?: string | null;
  reassignPaths?: Array<{ id: string; d: string }>;
  // New: dashed preview paths while detaching selected wires
  detachPaths?: Array<{ srcAttrId: number; d: string }>;
  onEmptyClick?: () => void;
}

const Wires: React.FC<WiresProps> = ({
  wirePaths,
  hoveredAttrId,
  hoveredAttrKey,
  selectedTransformationIds,
  onWireClick,
  onWireDoubleClick,
  onWireMouseDown,
  dragPath,
  reassignPaths = [],
  detachPaths = [],
  onEmptyClick,
  selectedWireSourceAttrIds,
}) => {
  return (
    <svg
      className="mappings-wires mappings-wires--grid"
      onClick={(e) => {
        // If click targets the SVG itself (not a <path>), treat as background click
        const target = e.target as HTMLElement;
        const tag = (target?.tagName || '').toLowerCase();
        if (tag !== 'path') {
          onEmptyClick?.();
        }
      }}
    >
      {wirePaths.map((w) => {
        const highlight = hoveredAttrKey
          ? (w.srcKey === hoveredAttrKey || w.tgtKey === hoveredAttrKey)
          : hoveredAttrId
          ? (w.srcId === hoveredAttrId || w.tgtId === hoveredAttrId)
          : false;
        const transId = w.transId ?? Number(String(w.id).replace('wire-', '').split('-')[0]);
        const selected = selectedTransformationIds.has(transId) && (
          !selectedWireSourceAttrIds || selectedWireSourceAttrIds.size === 0 || selectedWireSourceAttrIds.has(w.srcId)
        );
        const classes = [w.className || 'mappings-wire'];
        if (selected) classes.push('mappings-wire--selected');
        else if (highlight) classes.push('mappings-wire--highlight');
        return (
          <path
            key={w.id}
            d={w.d}
            className={classes.join(' ')}
            data-transformation-id={transId}
            data-source-path={w.srcPathName || ''}
            data-target-path={w.tgtPathName || ''}
            data-source-attr-id={w.srcId}
            data-target-attr-id={w.tgtId}
            data-source-entity-id-path={w.srcEntityIdPath || ''}
            data-target-entity-id-path={w.tgtEntityIdPath || ''}
            onMouseDown={(e) => onWireMouseDown?.(transId, w.srcId, e)}
            onClick={(e) => onWireClick(transId, w.srcId, e)}
            onDoubleClick={() => onWireDoubleClick(transId, w.srcId)}
          />
        );
      })}
      {dragPath && (
        <path
          d={dragPath}
          className="mappings-wire mappings-wire--drag mappings-wire--noevents"
        />
      )}
      {reassignPaths.map((p) => (
        <path
          key={p.id}
          d={p.d}
          className="mappings-wire mappings-wire--drag mappings-wire--noevents"
        />
      ))}
      {detachPaths.map((p, i) => (
        <path
          key={`detach-${p.srcAttrId}-${i}`}
          d={p.d}
          className="mappings-wire mappings-wire--drag mappings-wire--noevents"
          strokeDasharray="4 4"
        />
      ))}
    </svg>
  );
};

export default Wires;
