import React, { useMemo, useState, useCallback } from "react";
import { MinusIcon, PlusIcon, Pencil2Icon } from "@radix-ui/react-icons";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Checkbox from "@radix-ui/react-checkbox";
import "./TreeModelExplorer.css";

const FileDEBUG = false;
const debugLog = (...args: any[]) => { if(FileDEBUG) console.log(...args); };


// tree node types supported
export type NodeType = "model" | "entity" | "attribute" | "valueSet" | "value";

// core data shape for each node in the tree
export interface TreeNode {
  id: string;
  label: string;
  type: NodeType;
  subtype?: string;
  children?: TreeNode[];
  parentId?: string;
  parentType?: NodeType;
  public?: boolean;
  include?: boolean;
  [key: string]: any;
}

// optional label click handlers keyed by node type
export type typeHandlers = Partial<Record<NodeType, (node: TreeNode, parent: TreeNode | null) => void>>;

// props for the TreeModelExplorer component
export interface TreeModelExplorerProps {
  data: TreeNode[] | TreeNode; // accepts a single root or a list of roots
  searchFilter?: boolean; // toggles search box
  headerString: string;
  onEditModel: () => Promise<void>;
  onAddNew: (a: any) => void;
  onFuncDownload: (a:any, b:any, c:any) => void;
  triggerModal: (node: TreeNode, addKind: string, isSelect?: any) => void;
  triggerCheckbox: (node: TreeNode, field: "pub" | "inc", newVal: boolean) => void;
  initiallyExpandedIds?: Array<string>; // nodes expanded on mount
  typeHandlers?: typeHandlers; // static functions per type for label click
  treeClassName?: string; // optional wrapper class
  showModelAsRoot?: boolean; // new prop to control if model node is shown as top-level
  showPublicToggles?: boolean;
  showInclusionToggles?: boolean;
}


// normalize incoming data to an array of roots
const toArray = (data: TreeNode[] | TreeNode): TreeNode[] => Array.isArray(data) ? data : [data];

// compute a flat set of IDs for nodes that have children
const collectExpandableIds = (nodes: TreeNode[], out = new Set<string>()): Set<string> => {
  for (const n of nodes) {
    if (n.children && n.children.length) out.add(n.leafId); // Changed from n.id to n.leafId
    if (n.children) collectExpandableIds(n.children, out);
  }
  return out;
};

// filter the tree by a case-insensitive substring match on label; returns pruned deep copy
const filterTree = (nodes: TreeNode[], query: string): TreeNode[] => {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  const walk = (list: TreeNode[]): TreeNode[] =>
    list
      .map((n) => {
        const selfMatch = n.label.toLowerCase().includes(q);
        const kids = n.children ? walk(n.children) : undefined;
        const keep = selfMatch || (kids && kids.length > 0);
        if (!keep) return null;
        return { ...n, children: kids } as TreeNode;
      })
      .filter(Boolean) as TreeNode[];

  return walk(nodes);
};

// toggle helper for Set-based state
const toggleInSet = <T,>(set: Set<T>, value: T): Set<T> => {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
};

// main TreeModelExplorer component
export const TreeModelExplorer: React.FC<TreeModelExplorerProps> = (props) => {
  const {
    data,
    showModelAsRoot = false,
    searchFilter = false,
    headerString,
    onEditModel,
    onAddNew,
    onFuncDownload,
    triggerModal,
    triggerCheckbox,
    initiallyExpandedIds,
    typeHandlers,
    treeClassName,
    showPublicToggles = false,
    showInclusionToggles = false,
  } = props;
  const [modelNode, setModelNode] = useState<TreeNode | null>(null);
  const [openApiPublicOnly, setOpenApiPublicOnly] = React.useState(false);
  const [checkA, setCheckA] = useState<Record<string | number, boolean>>({});
  const [checkB, setCheckB] = useState<Record<string | number, boolean>>({});
  const [query, setQuery] = useState("");
  
  const TOGGLE_ALL_NODE_LIMIT = 10000; // max nodes to allow "toggleAll"

  // Normalize data to an array of roots
  const processedRoots = useMemo(() => {
    const roots = toArray(data);
    setModelNode(roots && roots.length === 1 ? roots[0] : null);
    if (!showModelAsRoot && roots.length === 1 && roots[0].type === "model" && roots[0].children) {
      return roots[0].children;
    }
    return roots;
  }, [data, showModelAsRoot]);

  // Collect all node types present in the tree
  const nodeTypesInTree = useMemo(() => {
    const collectTypes = (nodes: TreeNode[]): Set<NodeType> => {
      const types = new Set<NodeType>();
      const traverse = (nodeList: TreeNode[]) => {
        nodeList.forEach(node => {
          types.add(node.type);
          if (node.children) traverse(node.children);
        });
      };
      traverse(nodes);
      return types;
    };
    return collectTypes(processedRoots);
  }, [data]);

  const defaultExpandable = useMemo(() => collectExpandableIds(processedRoots), [processedRoots]);
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(initiallyExpandedIds ?? Array.from(defaultExpandable))
  );

  // Unique ids for checkbox column headers (avoid collisions across multiple trees)
  const headerIds = useMemo(() => {
    const suffix = Math.random().toString(36).slice(2, 8);
    return { pub: `chkhead-public-${suffix}`, inc: `chkhead-include-${suffix}` };
  }, []);

  const filteredRoots = useMemo(() => filterTree(processedRoots, query), [processedRoots, query]);

  const onToggleExpand = useCallback((leafId: string) => {
    setExpanded((prev) => toggleInSet(prev, leafId));
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
        if (!prev.has(id)) return new Set(defaultExpandable); // open all
      }
      return new Set(); // close all
    });
  }, [defaultExpandable]);

  const pathToNode = (n: TreeNode): TreeNode[] => {
    const parents: TreeNode[] = [n];
    let current = n;
    while (current.parentId) {
      const parent = findNodeById(processedRoots, current.parentLeafId, current.attrLeafId);
      if (parent) {
        parents.push(parent);
        current = parent;
      } else break;
    }
    // debugLog("Path to node:", n, "is", parents);
    return parents.reverse();
  };
  const findNodeById = (nodes: TreeNode[], leafId: string, attrLeafId?: string): TreeNode | null => {
    for (const n of nodes) {
      if (attrLeafId && n.type === 'valueSet') {
        if (n.leafId === leafId && n.parentLeafId === attrLeafId) return n;
      } else if (n.leafId === leafId) return n;
      if (n.children) {
        const found = findNodeById(n.children, leafId, attrLeafId);
        if (found) return found;
      }
    }
    return null;
  };

  const onLabelClick = useCallback((node: TreeNode) => {
    // debugLog('Clicked node:', node, '; Parents:', pathToNode(node));
    const fn = typeHandlers?.[node.type];
    const pNode = node.parentLeafId ? findNodeById(processedRoots, node.parentLeafId, node.attrLeafId) : null;
      if (fn) {
        fn(node, pNode);
      }
      else debugLog(`[TreeModelExplorer] unhandled label clicked for ${node.type}#${node.id}`, node);
    },
    [typeHandlers]
  );

  return (
    <div className={"json-tree-wrapper tree-model-explorer" + (treeClassName ? ` ${treeClassName}` : "")}> 
      <div className="col-head">
        <div className="head-group">
          <h2 className="col-title" style={{display: "flex", alignItems: "center", gap: "8px"}}>
            <div>{headerString || "Tree View"}</div>
            <div style={{ marginLeft: "auto", display: "flex", gap: "12px" }}>
              <div className="actions">
                <button onClick={() => onEditModel()} aria-label="Edit Model"><Pencil2Icon /></button>
                <button onClick={() => onAddNew(modelNode)} aria-label="Add Top Entity"><PlusIcon /></button>
              </div>
            </div>
          </h2>
          {searchFilter && (
            <div className="tree-search">
              <input
                type="text"
                placeholder="Search by Name…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Filter the tree by Name"
              />
            </div>
          )}
        </div>
      </div>
      <div className="col-body thin">
        <div className="legend" aria-hidden="true">
          {Array.from(nodeTypesInTree).map(type => (
            <span key={type} className="legend-item">
              <span className={`legend-ico ${type}`}></span>
              <span className="legend-label">{type}</span>
            </span>
          ))}
        </div>

        {onFuncDownload ? (
        <div className="col-head-inner">
          <div className="openapi-dl">
            <span className="openapi-dl-header">Download OpenAPI Schema:</span>
            <button type="button" className="openapi-dl-btn" title={`Full MDR OpenAPI schema for ${modelNode?.label}`}
              onClick={() => onFuncDownload(modelNode?.id, 'full', openApiPublicOnly)}
            >MDR</button>
            <button type="button" className="openapi-dl-btn" title={`Standard OpenAPI schema for ${modelNode?.label}`}
              onClick={() => onFuncDownload(modelNode?.id, 'bare', openApiPublicOnly)}
            >Standard</button>
            {['OrgLIF'].includes(modelNode?.subtype ?? '') && (
            <label htmlFor="openapi-dl-pub" className="openapi-dl-pub" title={`Only include elements marked as public?`}>
              <input type="checkbox" id="openapi-dl-pub" checked={openApiPublicOnly}
                onChange={e => setOpenApiPublicOnly(e.target.checked)} /> Public only?
            </label>
            )}
          </div>
        </div>
        ) : (<hr />)}

        <div className="col-body-inner">
          <div className="col-field-headers">
            <span className="leaf-toggle-spacer">
            {TOGGLE_ALL_NODE_LIMIT > modelNode?.nodeCount && (
              <button
                type="button"
                className="leaf-toggle-all"
                aria-label={allOpen ? "Close all nodes" : "Open all nodes"}
                onClick={toggleAll}
                title={allOpen ? "Close all" : "Open all"}
              >{allOpen ? <MinusIcon /> : <PlusIcon />}</button>
            )}
            </span>
            <span />
            {!showInclusionToggles && showPublicToggles && (
              <><span className="col-chkhead"></span></>
            )}
            {showPublicToggles && (
              <span id={headerIds.pub} className="col-chkhead">{showPublicToggles ? "Pub" : ""}</span>
            )}
            {showInclusionToggles && (
              <span id={headerIds.inc} className="col-chkhead">{showInclusionToggles ? "Inc" : ""}</span>
            )}
            <span />
          </div>
          <div className="tree-root" role="tree" aria-multiselectable={false}>
            {filteredRoots.map((n: any, idx: number) => (
              <TreeModelLeaf
                key={`${n.type}-${n.id}-${n.parentType}-${n.parentId}_${idx}`}
                node={n}
                depth={0}
                expanded={expanded}
                onToggleExpand={onToggleExpand}
                onLabelClick={onLabelClick}
                triggerModal={triggerModal}
                triggerCheckbox={triggerCheckbox}
                checkA={checkA}
                checkB={checkB}
                setCheckA={setCheckA}
                setCheckB={setCheckB}
                headerIds={headerIds}
                modelNode={modelNode}
                showPublicToggles={showPublicToggles}
                showInclusionToggles={showInclusionToggles}
                isRefOrRefChild={n.isRef}
                pathToNode={pathToNode}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TreeModelExplorer;

// recursive TreeModelLeaf compoent
const TreeModelLeaf: React.FC<{
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggleExpand: (leafId: string) => void;
  onLabelClick: (node: TreeNode) => void;
  triggerModal: (node: TreeNode, addKind: string, isSelect?: any) => void;
  triggerCheckbox: (node: TreeNode, field: "pub" | "inc", newVal: boolean) => void;
  checkA: Record<string | number, boolean>;
  checkB: Record<string | number, boolean>;
  setCheckA: React.Dispatch<React.SetStateAction<Record<string | number, boolean>>>;
  setCheckB: React.Dispatch<React.SetStateAction<Record<string | number, boolean>>>;
  headerIds: { pub: string; inc: string };
  modelNode: TreeNode | null;
  showPublicToggles?: boolean;
  showInclusionToggles?: boolean;
  isRefOrRefChild?: boolean;
  pathToNode: (n: TreeNode) => TreeNode[];
}> = ({
  node,
  depth,
  expanded,
  onToggleExpand,
  onLabelClick,
  triggerModal,
  triggerCheckbox,
  checkA,
  checkB,
  setCheckA,
  setCheckB,
  headerIds,
  modelNode,
  showPublicToggles,
  showInclusionToggles,
  isRefOrRefChild,
  pathToNode,
}) => {
  const hasChildren = !!(node.children && node.children.length);
  const isOpen = expanded.has(node.leafId);
  const dataListItemId = `${node.type}-${node.id}-${Math.random().toString(36).slice(2, 8)}`;
  const disableInc = modelNode?.baseModel && node.inModel && !node.inBase;

  const getNKey = (childNode: TreeNode) => {
    const trimType = (str: string) => str === "valueSet" ? "vs" : str.charAt(0);
    const id = childNode.leafId || "u";
    const type: string = trimType(childNode.type || "u");
    const pId = childNode.parentLeafId || "u";
    const pType: string = trimType(childNode.parentType || "u");
    return `${type}-${id}-${pType}-${pId}`;
  }

  if (isRefOrRefChild) {
    showPublicToggles = false;
    showInclusionToggles = false;
  }

  return (
    <div className={`leaf leaf-depth-${depth} ${hasChildren ? 'has-leaves' : ''} ${isRefOrRefChild ? 'part-ref' : ''}`} role="treeitem" aria-expanded={hasChildren ? isOpen : undefined}>
      <div className={`leaf-row leaf-${node.type}`} data-list-item-id={dataListItemId}>
        {hasChildren ? (
          <button
            className="leaf-toggle"
            aria-expanded={isOpen}
            aria-label={isOpen ? "Collapse" : "Expand"}
            onClick={() => {
              // debugLog("toggleNode:", node);
              onToggleExpand(node.leafId);
            }}
          >
            <span className="caret">▶</span>
          </button>
        ) : (
          <span className="leaf-toggle-spacer" aria-hidden />
        )}

        <div className={`leaf-${node.type} leaf-content`} onDoubleClick={() => onToggleExpand(node.leafId)}>
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
                onToggleExpand(node.leafId);
              } else if (e.key === 'ArrowLeft' && hasChildren && isOpen) {
                e.preventDefault();
                onToggleExpand(node.leafId);
              }
            }}
            aria-label={`${node.type}: ${node.label}`}
            title={node.label}
          >
            <span className="leaf-label-ico" aria-hidden />
            <span className="leaf-label">{node.label}</span>
          </button>
        </div>

        {((!["entity", "attribute"].includes(node.type)) || !showPublicToggles) && (
        <>
          <span className="leaf-cbx"></span>
        </>
        )}
        {((!["entity", "attribute"].includes(node.type)) || !showInclusionToggles) && (
        <>
          <span className="leaf-cbx"></span>
        </>
        )}
        {["entity", "attribute"].includes(node.type) && showPublicToggles && (
        <>
          <Checkbox.Root
            id={`pub-${dataListItemId}`}
            checked={!!node.public}
            onCheckedChange={(v) => {
              node.public = Boolean(v); // Update the node property directly
              setCheckA((prev) => ({ ...prev, [node.id]: Boolean(v) })); // Also update the local state
              triggerCheckbox(node, "pub", Boolean(v));
            }}
            className="leaf-chk"
            aria-label="Public"
            aria-describedby={headerIds.pub}
            disabled={!node.include}
          >
            <Checkbox.Indicator className="leaf-chk-ind">✓</Checkbox.Indicator>
          </Checkbox.Root>
        </>
        )}
        {["entity", "attribute"].includes(node.type) && showInclusionToggles && (
        <>
          <Checkbox.Root
            id={`inc-${dataListItemId}`}
            checked={!!node.include}
            onCheckedChange={(v) => {            
              node.include = Boolean(v); // Update the node property directly
              setCheckB((prev) => ({ ...prev, [node.id]: Boolean(v) })); // Also update the local state
              if (!v) { // unset Public, but avoid triggerCheckbox(node, "pub", false)
                node.public = false;
                setCheckA((prev) => ({ ...prev, [node.id]: false }));
              }
              triggerCheckbox(node, "inc", Boolean(v));
            }}
            className="leaf-chk"
            aria-label="Include"
            aria-describedby={headerIds.inc}
            disabled={disableInc}
          >
            <Checkbox.Indicator className="leaf-chk-ind">✓</Checkbox.Indicator>
          </Checkbox.Root>
        </>
        )}

        <div className="leaf-actions">
          {!isRefOrRefChild && (!["attribute", "value"].includes(node.type)  || (node.type === "attribute" && !node.hasValueSet)) && (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button className="menu-trigger" aria-label="Open node menu">⋮</button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content className="menu-content" sideOffset={4}>
              { ["model", "entity"].includes(node.type) && (
              <>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "entity")}>
                  New Entity
                </DropdownMenu.Item>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "entity", pathToNode(node).filter(n => n.type === 'entity'))}>
                  + Existing Entity
                </DropdownMenu.Item>
              </>
              )}
              { ["entity"].includes(node.type) && (
              <>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "attribute")}>
                  New Attribute
                </DropdownMenu.Item>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "attribute", true)}>
                  + Existing Attribute
                </DropdownMenu.Item>
              </>
              )}
              { ["attribute"].includes(node.type) && !node.hasValueSet && (
              <>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "valueSet")}>
                  New Value Set
                </DropdownMenu.Item>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "valueSet", true)}>
                  + Existing Value Set
                </DropdownMenu.Item>
              </>
              )}
              { ["valueSet"].includes(node.type) && (
              <>
                <DropdownMenu.Item className="menu-item" onSelect={() => triggerModal(node, "value", false)}>
                  New Value
                </DropdownMenu.Item>
              </>
              )}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          )}
        </div>
      </div>

      {hasChildren && isOpen && (
        <div role="group">
          {node.children!.map((n: any, idx: number) => (
            <TreeModelLeaf
              key={`${getNKey(n)}_${idx}`}
              node={n}
              depth={depth + 1}
              expanded={expanded}
              onToggleExpand={onToggleExpand}
              onLabelClick={onLabelClick}
              triggerModal={triggerModal}
              triggerCheckbox={triggerCheckbox}
              checkA={checkA}
              checkB={checkB}
              setCheckA={setCheckA}
              setCheckB={setCheckB}
              headerIds={headerIds}
              modelNode={modelNode}
              showPublicToggles={showPublicToggles}
              showInclusionToggles={showInclusionToggles}
              isRefOrRefChild={n.isRef || isRefOrRefChild}
              pathToNode={pathToNode}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// transform JSON data into TreeNode format
export const transformData = (data: any, baseData?: any): TreeNode => {
  if (!data?.DataModel?.Id) return {} as TreeNode;
  if (!baseData?.DataModel?.Id) baseData = {};  

  let i: number = 0;
  const AutoSort = baseData;
  const IncludeOrphanValueSets = false;
  const DMContribOrg = data.DataModel.ContributorOrganization;
  const EAs: any[] = [...(baseData?.EntityAssociations || []), ...(data?.EntityAssociations || [])];
  const EAAs: any[] = [...(baseData?.AttributeAssociations || []), ...(data?.AttributeAssociations || [])];

  const entityLabel = (o: any, a?: any) => (!o ? o : {
    ...o, nodeLabel: o?.Name || "—", Attributes: (a?.length ? a : [])
  });

  const map2Console = (m: Map<string, any>) => {
    return Array.from(m.values()).map(e => ({
      Id: e.Id,
      UniqueName: e.UniqueName,
      Attributes: e.Attributes?.length || 0,
      ParentEntities: e.ParentEntities?.map((parent: any) => parent.Id).join(", ") || 0,
      ChildEntities: e.ChildEntities?.map((child: any) => child.Id).join(", ") || 0
    }));
  };


  debugLog("--- Tree Data Transformation ---");
  const modelId = data.DataModel.Id;
  const modelNode: TreeNode = { // Create the root model node
    leafId: `model_${++i}`,
    id: modelId,
    type: "model",
    subtype: data.DataModel.Type,
    label: data.DataModel.Name,
    children: [],
    public: false,
    include: false,
    parentId: undefined,
    parentType: undefined,
    baseModel: baseData?.DataModel?.Id || undefined,
  };
  const allChildren: TreeNode[] = [];


  let iVS = 0;
  let iVal = 0;
  const valueSetNodesMap = new Map<string, TreeNode>();
  // First, process ValueSets to create a lookup map
  const buildValueSetNodeMap = (d: any, isBase?: boolean) => {
    const vsets = d?.ValueSets || [];
    vsets?.forEach((vs: any) => {
      const vsId = vs?.ValueSet?.Id;
      if (!valueSetNodesMap.has(vsId)) {
        const valueSetNode: TreeNode = {
          leafId: `vs_${++iVS}`,
          id: vsId,
          type: "valueSet",
          label: vs.ValueSet.Name,
          children: [],
          parentId: modelNode.id,
          parentType: "model",
          parentLeafId: modelNode.leafId,
          inBase: !!isBase,
          inModel: !isBase,
        };
        // map set values
        const values = vs.Values || [];
        const valueNodes: TreeNode[] = values
          .filter((valueItem: any) => valueItem.ValueName)
          .map((valueItem: any) => ({
            leafId: `val_${++iVal}`,
            id: valueItem.Id,
            type: "value" as NodeType,
            label: valueItem.Value,
            parentId: vsId,
            parentType: "valueSet",
            parentLeafId: valueSetNode.leafId,
            inBase: !!isBase,
            inModel: !isBase,
          }));
        if (AutoSort) valueNodes.sort((a, b) => a.label.localeCompare(b.label));
        valueSetNode.children = valueNodes;
        valueSetNodesMap.set(vsId, valueSetNode);
      } else {
        const vsNode: any = valueSetNodesMap.get(vsId);
        if (isBase) vsNode.inBase = true;
        else vsNode.inModel = true;
        // merge values
        const values = vs.Values || [];
        const valueNodes: TreeNode[] = values
          .filter((valueItem: any) => valueItem.ValueName)
          .forEach((valueItem: any) => {
            const idx = vsNode.children.findIndex((child: TreeNode) => child.id === valueItem.Id);
            if (idx !== -1) { // should always be true, but just in case
              if (isBase) vsNode.children[idx].inBase = true;
              else vsNode.children[idx].inModel = true;
            } else {
              const valueNode: TreeNode = {
                leafId: `val_${++iVal}`,
                id: valueItem.Id,
                type: "value" as NodeType,
                label: valueItem.Value,
                parentId: vsNode.id,
                parentType: "valueSet",
                parentLeafId: vsNode.leafId,
                inBase: !!isBase,
                inModel: !isBase,
              };
              vsNode.children.push(valueNode);
            }
          });
        if (AutoSort) vsNode.children.sort((a: TreeNode, b: TreeNode) => a.label.localeCompare(b.label));
      }
    });
  }
  buildValueSetNodeMap(data, false);
  if (baseData) buildValueSetNodeMap(baseData, true);
  i += iVS + iVal;

  const entityMap = new Map<string, any>();
  // Built entityMap
  const buildEntityMap = (d: any, isBase?: boolean) => {
    const entities = d?.Entities || [];
    entities.filter((me: any) => me.Entity.UniqueName && me.Entity.UniqueName.length > 0).forEach((me: any) => {
      const ent = entityMap.get(me.Entity.UniqueName);
      if (!ent) {
        const entity = entityLabel(me.Entity, me.Attributes);
        const uniqueParentIds = new Set();
        const ParentEntities = (me.ParentEntities ?? [])
          .filter((parent: any) => {
            if (uniqueParentIds.has(parent.Id)) return false;
            uniqueParentIds.add(parent.Id);
            return true;
          })
          .map(entityLabel);
        const uniqueChildIds = new Set();
        const ChildEntities = (me.ChildEntities ?? [])
          .filter((c: any) => {
            const cMapName = `${c.Placement === "Reference" ? c.Relationship + 'Ref' : ''}${c.UniqueName}`;
            if (uniqueChildIds.has(cMapName)) return false;
            uniqueChildIds.add(cMapName);
            return true;
          })
          .map(entityLabel);
        entityMap.set(entity.UniqueName, {
          ...entity,
          ParentEntities,
          ChildEntities,
          Attributes: entity.Attributes ?? [],
          inBase: !!isBase,
          inModel: !isBase,
        });
      } else {
        if (isBase) ent.inBase = true;
        else ent.inModel = true;
        // merge any missing attributes, parents, children
        const attrMap = new Map(ent.Attributes.map((a: any) => [a.Id, a]));
        (me.Attributes ?? []).forEach((a: any) => attrMap.set(a.Id, a));
        ent.Attributes = Array.from(attrMap.values());
        const parentMap = new Map(ent.ParentEntities.map((p: any) => [p.Id, p]));
        (me.ParentEntities ?? []).map(entityLabel).forEach((p: any) => parentMap.set(p.Id, p));
        ent.ParentEntities = Array.from(parentMap.values());
        const childMap = new Map(ent.ChildEntities.map((c: any) => 
          [`${c.Placement === "Reference" ? c.Relationship + 'Ref' : ''}${c.UniqueName}`, c]
        ));
        (me.ChildEntities ?? []).map(entityLabel).forEach((c: any) => {
          const cMapName = `${c.Placement === "Reference" ? c.Relationship + 'Ref' : ''}${c.UniqueName}`;
          childMap.set(cMapName, c);
        });
        ent.ChildEntities = Array.from(childMap.values());
      }
    });
    debugLog(`entityMap (${isBase ? 'w/ base' : 'model only'}):`, map2Console(entityMap));
  };
  buildEntityMap(data, false);
  if (baseData) buildEntityMap(baseData, true);

  const parentMap = new Map<string, any>();
  const parent404 = new Map<string, any>();
  // Build parentMap (top-level entities)
  debugLog("data.EntityAssociations:", EAs.length);
  entityMap.forEach((objE: any) => {
    const childAssocs = EAs.filter((ea: any) => ea.ChildEntityId === objE.Id);
    const isTopLevel = objE.ParentEntities.length === 0
      || childAssocs.every((ea: any) => ea.Placement === 'Reference');
    // debugLog(` - Entity#${objE.Id} has ${objE.ParentEntities?.length} parents and ${childAssocs.length} childAssocs, thus isTopLevel = ${isTopLevel}`);
    if (isTopLevel) parentMap.set(objE.UniqueName, objE);
  });
  debugLog("parentMap:", map2Console(parentMap));
  entityMap.forEach((objE: any) => {
    objE.ParentEntities.forEach((parent: any) => {
      if (!parentMap.has(parent.UniqueName)) {
        parent404.set(parent.Id, parent);
      } else {
        const parentEntity = parentMap.get(parent.UniqueName);
        if (!parentEntity.ChildEntities) parentEntity.ChildEntities = [];
        const childAlreadyExists = parentEntity.ChildEntities.some(
          (child: any) => child.UniqueName === objE.UniqueName
        );
        if (!childAlreadyExists) parentEntity.ChildEntities.push(objE);
      }
    });
  });
  if (parent404.size) debugLog(" > not found in map:", map2Console(parent404));


  let iEnt = 0;
  let iAttr = 0;
  const entityTree = Array.from(parentMap.values()) || [];
  let maxRecursion = 0;
  // Convert the processed entities to TreeNodes
  const entityNodes: TreeNode[] = entityTree.map((topEntity: any) => {
    const eIncluded = data.Inclusions?.find((inc: any) => inc.ElementType === "Entity" && inc.IncludedElementId === topEntity.Id && inc.ExtDataModelId === modelId) || null;
    const entityNode: TreeNode = {
      leafId: `ent_${++iEnt}`,
      id: topEntity.Id,
      type: "entity" as NodeType,
      subtype: topEntity.Extension
        ? (topEntity.ContributorOrganization !== DMContribOrg ? "partner" : "extension")
        : undefined,
      label: topEntity.nodeLabel,
      public: !!eIncluded?.Id && eIncluded?.LevelOfAccess === "Public",
      include: !!eIncluded?.Id,
      parentId: modelNode.id,
      parentType: "model",
      parentLeafId: modelNode.leafId,
      inBase: topEntity.inBase,
      inModel: topEntity.inModel,
      hasAssocId: false,
      hasIncId: eIncluded?.Id,
      isRef: false,
      children: [],
    };

    let children: TreeNode[] = [];
    const buildAttributes = (e: any, eNode: TreeNode): TreeNode[] | undefined => {
      if (e?.Attributes && Array.isArray(e.Attributes)) {
        const isReference = eNode.isRef;
        const attributeNodes: TreeNode[] = e.Attributes
          .filter((a: any) => a?.Name && (!isReference || a.Required === "Yes"))
          .map((a: any) => {
            const aAssoc = EAAs.find((eaa: any) => eaa.EntityId === e.Id && eaa.AttributeId === a.Id)?.Id || false;
            const aIncluded = data.Inclusions?.find((inc: any) => inc.ElementType === "Attribute" 
              && inc.IncludedElementId === a.Id && inc.ExtDataModelId === modelId) || null;
            const attributeNode: TreeNode = {
              leafId: `attr_${++iAttr}`,
              id: a.Id,
              type: "attribute" as NodeType,
              subtype: a.Extension
                ? (a.ContributorOrganization !== DMContribOrg ? "partner" : "extension")
                : undefined,
              label: a.Name,
              public: !!aIncluded?.Id && aIncluded?.LevelOfAccess === "Public",
              include: !!aIncluded?.Id,
              parentId: e.Id,
              parentType: "entity",
              parentLeafId: eNode.leafId,
              hasValueSet: !!a.ValueSetId,
              inBase: e.inBase,
              inModel: e.inModel,
              isRef: isReference ? "c" : false,
              hasAssocId: aAssoc,
              hasIncId: aIncluded?.Id,
              children: [],
            };
            // Check if this attribute has a ValueSetId and link the corresponding ValueSet
            if (a.ValueSetId && valueSetNodesMap.has(a.ValueSetId)) {
              const linkedValueSet = valueSetNodesMap.get(a.ValueSetId);
              if (linkedValueSet) {
                // Create a copy of the valueSet with updated parent info
                const valueSetCopy: TreeNode = {
                  ...linkedValueSet,
                  parentId: attributeNode.id,
                  parentType: "attribute",
                  parentLeafId: attributeNode.leafId,
                  isRef: isReference ? "c" : false,
                  children: (linkedValueSet.children || []).map((v: TreeNode) => ({
                    ...v,
                    attrLeafId: attributeNode.leafId,
                    isRef: isReference ? "c" : false, // c = child of reference and never used in label
                  })),
                };
                attributeNode.children = [valueSetCopy];
              }
            }
            return attributeNode;
          });
        return attributeNodes.filter((c: any) => c?.id);
      } // end e?.Attributes.map
      return;
    }; // buildAttributes(entity)

    const buildChildren = (e: any, pNode: TreeNode, p?: number[], d?: number): TreeNode[] | undefined => {
      p = p || []; // parent list;
      p.push(e?.Id);
      d = d || 1; // depth
      if (d! > 25) { // DEV Note: may want to remove this completely
        ++maxRecursion;
        // if (FileDEBUG) console.warn('>> Max recursion depth reached, stopping:', p);
        return;
      }
      if (e?.ChildEntities && Array.isArray(e.ChildEntities)) {
        const childEntityLabel = (c: any): string => {
          const nodeLabel = c.nodeLabel;
          const rel = (c.Relationship || "") + "Ref";
          if (c.Placement !== "Reference") return nodeLabel;
          else if (rel.startsWith("has") || rel.startsWith("relevant")) return nodeLabel;
          else return `${rel}${nodeLabel}`;
        }

        const childrenNodes: TreeNode[] = e.ChildEntities
          .filter((c: any) => c?.Name) // Only include attributes with Name
          .map((c: any) => {
            if (p.includes(c?.Id)) {
              // debugLog("> Recursion detected, skipping child entity:", c.Id, p);
              return; // prevents recursion (happens!)
            } else {
              const eAssoc = EAs.find((ea: any) => ea.ParentEntityId === e.Id && ea.ChildEntityId === c.Id
                && ea.Relationship === c.Relationship && ea.Placement === c.Placement)?.Id || false;
              const cIncluded = data.Inclusions?.find((inc: any) => inc.ElementType === "Entity" 
                && inc.IncludedElementId === c.Id && inc.ExtDataModelId === modelId) || null;
              const fullChildEntity = entityMap.get(c.UniqueName);
              const isReference = c.Placement === "Reference";
              const childNode: TreeNode = {
                leafId: `ent_${++iEnt}`,
                id: c.Id,
                type: "entity" as NodeType,
                subtype: c.Extension
                  ? (c.ContributorOrganization !== DMContribOrg ? "partner" : "extension")
                  : undefined,
                label: childEntityLabel(c),
                public: !!cIncluded?.Id && cIncluded?.LevelOfAccess === "Public",
                include: !!cIncluded?.Id,
                parentId: e.Id,
                parentType: "entity",
                parentLeafId: pNode.leafId,
                inBase: pNode.inBase,
                inModel: pNode.inModel,
                isRef: isReference ? c.Relationship + "Ref" : false, // string for relationship, else false
                hasAssocId: eAssoc,
                hasIncId: cIncluded?.Id,
                children: [],
              };
              const cAttrs = buildAttributes(fullChildEntity, childNode) || [];
              const cEnts = isReference ? [] : buildChildren(fullChildEntity, childNode, [...p], d + 1) || [];
              if (AutoSort) {
                cAttrs.sort((a, b) => a.label.localeCompare(b.label));
                cEnts.sort((a, b) => a.label.localeCompare(b.label));
              }
              childNode.children = [...cEnts, ...cAttrs];
              return childNode;
            }
          });
        return childrenNodes.filter((c: any) => c?.id);
      }
      return;
    }; // buildChildren(entity, depth?)

    const eEnts = buildChildren(topEntity, entityNode) || [];
    const eAttrs = buildAttributes(topEntity, entityNode) || []; // top-level entity, thus ignore Attribute.Required
    if (AutoSort) {
      eEnts.sort((a, b) => a.label.localeCompare(b.label));
      eAttrs.sort((a, b) => a.label.localeCompare(b.label));
    }
    children = [...eEnts, ...eAttrs];
    entityNode.children = children;
    return entityNode;
  }) // end entityTree.map
  debugLog("entityNodes:", entityNodes);
  if (maxRecursion) debugLog('Max recursion depth reached:', maxRecursion);
  i += iEnt + iAttr;
  allChildren.push(...entityNodes);


  // Add standalone ValueSets (those not linked to any attributes)
  const linkedValueSetIds = new Set<string>();
  // Collect all linked ValueSet IDs from the entity tree
  const collectLinkedValueSets = (nodes: TreeNode[]) => {
    nodes.forEach(node => {
      if (node.type === "valueSet") {
        linkedValueSetIds.add(node.id);
      }
      if (node.children) {
        collectLinkedValueSets(node.children);
      }
    });
  };
  collectLinkedValueSets(allChildren);

  if (IncludeOrphanValueSets) { // Add standalone ValueSets?
    const standaloneValueSets = Array.from(valueSetNodesMap.values())
    .filter(valueSetNode => !linkedValueSetIds.has(valueSetNode.id))
    .map(valueSetNode => ({
      ...valueSetNode,
      parentId: modelNode.id,
      parentType: "model" as NodeType,
      parentLeafId: modelNode.leafId,
    }));
    debugLog("< Including orphan ValueSets", standaloneValueSets.length);
    allChildren.push(...standaloneValueSets);
  }

  // Sort alphabetically by label
  if (AutoSort) {
    allChildren.sort((a, b) => a.label.localeCompare(b.label));
  }
  modelNode.children = allChildren;

  // Final node count (if too many, disable open/close all)
  const countNodes = (node: TreeNode): number => {
    let count = 1;
    if (node.children) count += node.children.reduce((sum, child) => sum + countNodes(child), 0);
    return count;
  };
  modelNode.nodeCount = countNodes(modelNode);
  debugLog(`[TreeNode Breakdown] Unique: ${i}, Entities: ${iEnt}, Attributes: ${iAttr}, ValueSets: ${iVS}, Values: ${iVal}, Showing: ${modelNode.nodeCount}`);

  return modelNode;
};
