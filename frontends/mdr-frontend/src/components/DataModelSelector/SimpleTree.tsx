import React, { useMemo, useState, useCallback } from "react";
import { MinusIcon, PlusIcon, Pencil2Icon, TrashIcon, UploadIcon } from "@radix-ui/react-icons";
import "./SimpleTree.css";

/**
 * Core data shape for each node in the tree
 */
export interface SimpleTreeNode {
  id: string | number;
  label: string;
  type: string;
  onClick?: () => void;
  children?: SimpleTreeNode[];
  [key: string]: any; // Allow arbitrary extra fields to flow through
}

/**
 * Props for the SimpleTree component
 */
export interface SimpleTreeProps {
  data: SimpleTreeNode[] | SimpleTreeNode; // accepts a single root or a list of roots
  className?: string;
  headerStr?: string;
  searchFilter?: boolean; // toggles search box
  onAddNew?: () => void; // optional top-level [+]
  onImport?: () => void; // optional top-level import, beside [+]
  importLabel?: string; // the import button's accessible name and tooltip
  initiallyExpandedIds?: Array<string | number>; // nodes expanded on mount
  hideToggleSpacer?: boolean; // if true, hides the expand/collapse toggle buttons
  typeHandlers?: Record<string, (node: SimpleTreeNode) => void>; // static functions per type for label click
}

/**
 * Utility: normalize incoming data to an array of roots
 */
const toArray = (data: SimpleTreeNode[] | SimpleTreeNode): SimpleTreeNode[] =>
  Array.isArray(data) ? data : [data];

/**
 * Utility: compute a flat set of IDs for nodes that have children
 */
const collectExpandableIds = (
  nodes: SimpleTreeNode[],
  out = new Set<string | number>()
): Set<string | number> => {
  for (const n of nodes) {
    if (n.children && n.children.length) out.add(n.id);
    if (n.children) collectExpandableIds(n.children, out);
  }
  return out;
};

/**
 * Filter the tree by a case-insensitive substring match on label.
 * Returns a pruned deep copy of the original nodes where any node is kept
 * if it or any of its descendants match the query.
 */
const filterTree = (nodes: SimpleTreeNode[], query: string): SimpleTreeNode[] => {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;

  const walk = (list: SimpleTreeNode[]): SimpleTreeNode[] =>
    list
      .map((n) => {
        const selfMatch = n.label.toLowerCase().includes(q);
        const kids = n.children ? walk(n.children) : undefined;
        const keep = selfMatch || (kids && kids.length > 0);
        if (!keep) return null;
        return { ...n, children: kids } as SimpleTreeNode;
      })
      .filter(Boolean) as SimpleTreeNode[];

  return walk(nodes);
};

/**
 * Toggle helper for Set-based state
 */
const toggleInSet = <T,>(set: Set<T>, value: T): Set<T> => {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
};

/**
 * Main component
 */
export const SimpleTree: React.FC<SimpleTreeProps> = ({
  data,
  headerStr,
  searchFilter = false,
  onAddNew,
  onImport,
  importLabel = "Import",
  initiallyExpandedIds,
  className,
  hideToggleSpacer = false,
  typeHandlers,
}) => {
  // Normalize data to an array of roots
  const processedRoots = useMemo(() => {
    const roots = toArray(data);
    
    // roots[0] to hide top-level
    return roots[0].children || []; 
  }, [data]);

  // Track expanded nodes by ID
  const defaultExpandable = useMemo(() => collectExpandableIds(processedRoots), [processedRoots]);
  const [expanded, setExpanded] = useState<Set<string | number>>(() => {
    // If initiallyExpandedIds is provided, use it
    if (initiallyExpandedIds) {
      return new Set(initiallyExpandedIds);
    }
    // Otherwise, use default behavior (expand all)
    return new Set(Array.from(defaultExpandable));
  });

  // Simple text query for filtering
  const [query, setQuery] = useState("");

  const filteredRoots = useMemo(() => filterTree(processedRoots, query), [processedRoots, query]);

  const onToggleExpand = useCallback((id: string | number) => {
    setExpanded((prev) => toggleInSet(prev, id));
  }, []);

  // Is every expandable node open?
  const allOpen = useMemo(() => {
    for (const id of defaultExpandable) {
      if (!expanded.has(id)) return false;
    }
    return defaultExpandable.size > 0;
  }, [expanded, defaultExpandable]);

  // Toggle all: open all if any are closed, otherwise close all
  const toggleAll = useCallback(() => {
    setExpanded((prev) => {
      for (const id of defaultExpandable) {
        if (!prev.has(id)) {
          return new Set(defaultExpandable); // open all
        }
      }
      return new Set(); // close all
    });
  }, [defaultExpandable]);

  const onLabelClick = useCallback(
    (node: SimpleTreeNode) => {
      const fn = typeHandlers?.[node.type];
      if (fn) fn(node);
      else console.info(`[SimpleTree] label clicked for ${node.type}#${node.id}`, node);
    },
    [typeHandlers]
  );

  return (
    <div className={"json-tree-wrapper simple-tree" + (className ? ` ${className}` : "")}> 
      <div className="col-head">
        <div className="head-group">
          {onAddNew ? <button className="addNew" onClick={onAddNew} aria-label="Add New"><PlusIcon /></button> : null}
          {onImport ? <button className="addNew importNew" onClick={onImport} aria-label={importLabel} title={importLabel}><UploadIcon /></button> : null}
          {headerStr ? <h2 className="col-title">{headerStr}</h2> : null}
          {searchFilter ? (
            <div className="tree-search">
              <input
                type="text"
                placeholder="Search by Name…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Filter the tree by Name"
              />
            </div>
          ) : null}
        </div>
      </div>

      <div className={`col-body ${hideToggleSpacer ? 'hide-spacers' : ''}`}>
        {!hideToggleSpacer && (
        <div className="col-field-headers" aria-hidden="true">
            <span className="leaf-toggle-spacer">
                <button
                    type="button"
                    className="leaf-toggle-all"
                    aria-label={allOpen ? "Close all nodes" : "Open all nodes"}
                    onClick={toggleAll}
                    title={allOpen ? "Close all" : "Open all"}
                >{allOpen ? <MinusIcon /> : <PlusIcon />}</button>
            </span>
        </div>
        )}
        <div className="tree-root" role="tree" aria-multiselectable={false}>
        {filteredRoots.map((n) => (
            <SimpleTreeModelLeaf
                key={`${n.type}-${n.id}`}
                node={n}
                depth={0}
                expanded={expanded}
                onToggleExpand={onToggleExpand}
                onLabelClick={onLabelClick}
                hideToggleSpacer={hideToggleSpacer}
            />
        ))}
        </div>
      </div>
    </div>
  );
};

export default SimpleTree;

/**
 * Recursive leaf
 */
const SimpleTreeModelLeaf: React.FC<{
  node: SimpleTreeNode;
  depth: number;
  expanded: Set<string | number>;
  onToggleExpand: (id: string | number) => void;
  onLabelClick: (node: SimpleTreeNode) => void;
  hideToggleSpacer?: boolean;
}> = ({
  node,
  depth,
  expanded,
  onToggleExpand,
  onLabelClick,
  hideToggleSpacer = false,
}) => {
  const hasChildren = !!(node.children && node.children.length);
  const isOpen = expanded.has(node.id);
  const dataListItemId = `${node.type}-${node.id}`;

  return (
    <div className={`leaf leaf-${depth}${hasChildren ? ' has-leaves' : ''}${node.noClick ? ' no-click' : ''}`} role="treeitem" aria-expanded={hasChildren ? isOpen : undefined}>
      <div className={`leaf-row leaf-${node.type}`} data-list-item-id={dataListItemId}>
        {/* open/close icon, only if there are children and hideToggleSpacer is false */}
        {hasChildren && !hideToggleSpacer ? (
          <button
            className="leaf-toggle"
            aria-expanded={isOpen}
            aria-label={isOpen ? "Collapse" : "Expand"}
            onClick={() => onToggleExpand(node.id)}
          >
            <span className="caret">▶</span>
          </button>
        ) : (
          <span className="leaf-toggle-spacer" aria-hidden />
        )}

        {/* label & type icon */}
        <div className={`leaf-${node.type} leaf-content`} onDoubleClick={() => onToggleExpand(node.id)}>
          <button
            type="button"
            className="leaf-label-wrap"
            onClick={() => onLabelClick(node)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onLabelClick(node);
              } else if (e.key === 'ArrowRight' && hasChildren && !isOpen) {
                e.preventDefault();
                onToggleExpand(node.id);
              } else if (e.key === 'ArrowLeft' && hasChildren && isOpen) {
                e.preventDefault();
                onToggleExpand(node.id);
              }
            }}
            aria-label={`${node.type}: ${node.label}`}
            title={node.label}
          >
            <span className="leaf-label-ico" aria-hidden />
            <span className="leaf-label">{node.label}</span>
          </button>
        </div>
      </div>

      {/* children */}
      {hasChildren && isOpen && (
        <div role="group">
          {node.children!.map((child) => (
            <SimpleTreeModelLeaf
              key={`${child.type}-${child.id}`}
              node={child}
              depth={Math.min(depth + 1, 5)}
              expanded={expanded}
              onToggleExpand={onToggleExpand}
              onLabelClick={onLabelClick}
              hideToggleSpacer={hideToggleSpacer}
            />
          ))}
        </div>
      )}
    </div>
  );
};

/**
 * Transform JSON data into SimpleTreeNode format
 */
export const transformData = (data: any): SimpleTreeNode => {
  if (!data?.length) return {} as SimpleTreeNode;

  const modelsBase: any = [];
  const modelsOrg: any = [];
  const modelsSchema: any = [];
  const modelsPartner: any = [];
  data.map((model: any) => {
    switch (model.Type) {
      case "BaseLIF": modelsBase.push(model); break;
      case "OrgLIF": modelsOrg.push(model); break;
      case "SourceSchema": modelsSchema.push(model); break;
      case "PartnerLIF": modelsPartner.push(model); break;
      default: 
        console.error(`Unknown model type: ${model.Type}`);
        return;
    }
  });

  // Create the root model node
  const treeNode: SimpleTreeNode = {
    id: "iH0",
    type: "static",
    label: `Top Node`,
    noClick: true,
    children: [
      {
        id: modelsBase[0]?.Id,
        type: "BaseLIF",
        label: modelsBase[0]?.Name || "Base LIF",
        // data: modelsBase[0] || {},
        children: [],
      },
      {
        id: modelsOrg[0]?.Id,
        type: "OrgLIF",
        label: modelsOrg[0]?.Name || "Organization's LIF",
        // data: modelsOrg[0] || {},
        children: [
          {
            "id": "only",
            "type": "OrgLIF",
            "label": "All of " + (modelsOrg[0]?.Name || "Organization's LIF"),
            // data: modelsOrg[0] || {},
            parentId: modelsOrg[0]?.Id,
          },
          {
            id: "all",
            type: "OrgLIF",
            label: "Base LIF Inclusions",
            // data: modelsOrg[0] || {},
            parentId: modelsOrg[0]?.Id,
          },
          {
            id: "pub",
            type: "OrgLIF",
            label: "Public",
            // data: modelsOrg[0] || {},
            parentId: modelsOrg[0]?.Id,
          },
          {
            id: "ext",
            type: "OrgLIF",
            label: "Extensions",
            // data: modelsOrg[0] || {},
            parentId: modelsOrg[0]?.Id,
          },
          {
            id: "part",
            type: "OrgLIF",
            label: "Partner",
            // data: modelsOrg[0] || {},
            parentId: modelsOrg[0]?.Id,
          },
        ],
      },
      {
        id: "iP1",
        type: "SourceSchema",
        label: "Source Data Models",
        noClick: true,
        children: modelsSchema.map((model: any) => ({
          id: model.Id,
          type: model.Type,
          label: model.Name,
          // data: model,
        })),
      },
      {
        id: "iP2",
        type: "PartnerLIF",
        label: "Partner Models",
        noClick: true,
        children: modelsPartner.map((model: any) => ({
          id: model.Id,
          type: model.Type,
          label: model.Name,
          // data: model,
        })),
      }
    ]
  };

  return treeNode;
};
