import React, {
    useCallback,
    useEffect,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
} from 'react';
import './MappingsView.css';
import {
    getTransformationsForGroup,
    listAllTransformationGroups,
    TransformationData,
    TransformationGroupDetails,
    createTransformation,
    deleteTransformation,
    updateTransformation,
    updateTransformationGroup,
    createTransformationGroup,
    CreateTransformationGroup,
    TranformationGroupData,
    forkTransformationGroup,
    existsTransformationGroup,
    updateTransformationAttributes,
} from '../../../services/transformationsService';
import {
    getModelDetailsWithTree,
    listModels,
    listOrgLifModels,
    generateJsonSchema,
} from '../../../services/modelService';
import { buildDefaultAssignmentExpression } from '../../../utils/jsonataUtils';
import {
    DataModelWithDetailsDTO,
    DataModelWithDetailsWithTree,
    EntityDTO,
    AttributeDTO,
} from '../../../types';
import { Select as RdxSelect, Badge } from '@radix-ui/themes';
import { useNavigate, useParams } from 'react-router-dom';
import type { KeywordSearchItem } from '../../../components/KeywordSearch/KeywordSearch';
import BodyModelColumn from './components/ModelColumn';
import ColumnHeader from './components/ColumnHeader';
import useMappingWires, {
    WirePath as HookWirePath,
} from './hooks/useMappingWires';
import Wires from './components/Wires';
import useSearchItems from './hooks/useSearchItems';
import DeleteTransformationsDialog from './components/DeleteTransformationsDialog';
import ExpressionEditorDialog from './components/ExpressionEditorDialog';
import EditGroupDialog from './components/EditGroupDialog';
import ForkGroupDialog from './components/ForkGroupDialog';
import DetachSourcesDialog from './components/DetachSourcesDialog';
import BulkTransformationsDialog from './components/BulkTransformationsDialog';

interface DisplayTransformationData extends TransformationData {
    SourceEntity?: EntityDTO;
    TargetEntity?: EntityDTO;
}

const MappingsView: React.FC = () => {
    const REASSIGN_DRAG_THRESHOLD = 20;

    // Routing
    const { groupId: groupIdParam } = useParams();
    const navigate = useNavigate();

    // Top-level state
    const [error, setError] = useState<string | null>(null);
    const [groupId, setGroupId] = useState<number>(-1);
    const [group, setGroup] = useState<TransformationGroupDetails | null>(null);
    const [allModels, setAllModels] = useState<
        Array<{ Id: number; Name: string }>
    >([]);
    const [orgLifModels, setOrgLifModels] = useState<
        Array<{ Id: number; Name: string }>
    >([]);
    const [selectedSourceId, setSelectedSourceId] = useState<number | null>(
        null
    );
    const [loadedSourceModelId, setLoadedSourceModelId] = useState<
        number | null
    >(null);
    const [loadedTargetModelId, setLoadedTargetModelId] = useState<
        number | null
    >(null);
    const [selectedTargetId, setSelectedTargetId] = useState<number | null>(
        null
    );
    const [allGroups, setAllGroups] = useState<TranformationGroupData[] | null>(
        null
    );
    const [versionByGroupId, setVersionByGroupId] = useState<
        Record<number, string>
    >({});
    const [transformations, setTransformations] = useState<
        DisplayTransformationData[]
    >([]);
    const [sourceModel, setSourceModel] =
        useState<DataModelWithDetailsWithTree | null>(null);
    const [targetModel, setTargetModel] =
        useState<DataModelWithDetailsWithTree | null>(null);
    // Precomputed search items for each side so header search can work even when model prop is null
    const sourceSearchItems: KeywordSearchItem[] = useSearchItems(sourceModel);
    const targetSearchItems: KeywordSearchItem[] = useSearchItems(targetModel);
    const [sourceLoading, setSourceLoading] = useState(false);
    const [targetLoading, setTargetLoading] = useState(false);
    const [sourceQuery, setSourceQuery] = useState('');
    const [targetQuery, setTargetQuery] = useState('');

    // DOM refs
    const containerRef = useRef<HTMLDivElement | null>(null);
    const leftScrollRef = useRef<HTMLDivElement | null>(null);
    const rightScrollRef = useRef<HTMLDivElement | null>(null);
    const wiresSlotRef = useRef<HTMLDivElement | null>(null);
    // Path-aware attribute element registries: keys are `${EntityIdPath}|${AttributeId}` or just `${AttributeId}` as fallback
    const attrElementsLeft = useRef<Map<string, HTMLElement>>(new Map());
    const attrElementsRight = useRef<Map<string, HTMLElement>>(new Map());

    // Entity + async guards
    const entityByIdRef = useRef<Map<number, EntityDTO>>(new Map());
    const loadSeqRef = useRef(0);

    // Wires and interactions
    const [wirePaths, setWirePaths] = useState<HookWirePath[]>([]);
    const [hoveredAttrKey, setHoveredAttrKey] = useState<string | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [dragSourceAttr, setDragSourceAttr] = useState<AttributeDTO | null>(
        null
    );
    const [dragPath, setDragPath] = useState<string | null>(null);
    const [dragSourcePath, setDragSourcePath] = useState<string | null>(null);
    const [dragTargetAttrId, setDragTargetAttrId] = useState<number | null>(
        null
    );
    const [dragTargetPath, setDragTargetPath] = useState<string | null>(null);
    const [selectedTargetAttrId, setSelectedTargetAttrId] = useState<
        number | null
    >(null);
    const [selectionIndex, setSelectionIndex] = useState(0);
    const [selectionAll, setSelectionAll] = useState(false);
    const [selectedTransformationIds, setSelectedTransformationIds] =
        useState<Set<number>>(new Set());
    const [reassignActive, setReassignActive] = useState(false);
    const [reassignTransformations, setReassignTransformations] = useState<
        DisplayTransformationData[]
    >([]);
    const [reassignPaths, setReassignPaths] = useState<
        Array<{ id: string; d: string }>
    >([]);
    const [reassignHoverTargetId, setReassignHoverTargetId] = useState<
        number | null
    >(null);
    // Multi-wire (per-transformation) selection: store source AttributeIds for the currently selected transformation
    const [selectedWireSourceAttrIds, setSelectedWireSourceAttrIds] = useState<Set<number>>(new Set());
    // Multi-wire detach drag state (supports one or many selected source wires for the single selected transformation)
    const [wireDetachDragging, setWireDetachDragging] = useState<null | { transId: number; srcAttrIds: number[] }>(null);
    // Preview dashed paths while detaching (one per selected source wire)
    const [wireDetachPaths, setWireDetachPaths] = useState<Array<{ srcAttrId: number; d: string }>>([]);
    const pendingReassignRef = useRef<{
        startX: number;
        startY: number;
        transforms: DisplayTransformationData[];
    } | null>(null);

    // Build a default expression path like EntityA.EntityB.Attribute from an EntityIdPath and attribute name
    const buildDirectKeyExpression = useCallback(
        (entityIdPath?: string | null, attributeName?: string | null) => {
            const parts: string[] = [];
            if (entityIdPath) {
                const rawSegs = String(entityIdPath)
                    .split('.')
                    .map((s) => s.trim())
                    .filter(Boolean);
                rawSegs.forEach((seg) => {
                    if (/^\d+$/.test(seg)) {
                        // Numeric entity id
                        const id = parseInt(seg, 10);
                        const ent = entityByIdRef.current.get(id);
                        if (ent?.Name) {
                            parts.push(String(ent.Name));
                        }
                        // If lookup fails, fall back to raw segment (unlikely)
                        else {
                            parts.push(seg);
                        }
                    } else {
                        // Already a PathName token (e.g., 'Assessment', 'offeredByOrganization')
                        parts.push(seg);
                    }
                });
            }
            if (attributeName) {
                // Avoid duplicating final segment if attribute name already equals last path token
                if (parts.length === 0 || parts[parts.length - 1] !== attributeName) {
                    parts.push(String(attributeName));
                }
            }
            return parts.join('.');
        },
        []
    );

    // Dialog state
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [pendingDeleteIds, setPendingDeleteIds] = useState<number[]>([]);
    const [deleting, setDeleting] = useState(false);

    const [exprDialogOpen, setExprDialogOpen] = useState(false);
    const [editGroupOpen, setEditGroupOpen] = useState(false);
    const [forkDialogOpen, setForkDialogOpen] = useState(false);
    const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
    const [editingTransformation, setEditingTransformation] =
        useState<DisplayTransformationData | null>(null);
    const [editingTargetPath, setEditingTargetPath] = useState<string | null>(null);
    const [targetJsonSchema, setTargetJsonSchema] = useState<any | null>(null);
    const [sourceJsonSchema, setSourceJsonSchema] = useState<any | null>(null);
    const [forkBump, setForkBump] = useState<'major' | 'minor'>('major');
    const [forkPreview, setForkPreview] = useState<string>('');
    // Aggregate dialog open state
    const anyDialogOpen = deleteDialogOpen || exprDialogOpen || editGroupOpen || forkDialogOpen || bulkDialogOpen;
    // Detach sources dialog state
    const [detachDialogOpen, setDetachDialogOpen] = useState(false);
    const [pendingDetach, setPendingDetach] = useState<null | { transId: number; srcAttrIds: number[]; willDelete: boolean }>(null);
    const [detaching, setDetaching] = useState(false);

    // Prevent body scroll when a modal dialog is open
    useEffect(() => {
        if (!anyDialogOpen) return;
        const prev = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => {
            document.body.style.overflow = prev;
        };
    }, [anyDialogOpen]);

    const cleanupSelection = useCallback(() => {
        setReassignActive(false);
        setReassignTransformations([]);
        setReassignPaths([]);
        setReassignHoverTargetId(null);
        setSelectedTargetAttrId(null);
        setSelectedTransformationIds(new Set());
        setSelectionAll(false);
    }, []);

    const confirmDelete = useCallback(async () => {
        if (!pendingDeleteIds.length) {
            setDeleteDialogOpen(false);
            return;
        }
        setDeleting(true);
        try {
            await Promise.all(
                pendingDeleteIds.map((id) => deleteTransformation(id))
            );
            setTransformations((prev) =>
                prev.filter((p) => !pendingDeleteIds.includes(p.Id))
            );
            setGroup((prev) =>
                prev
                    ? {
                          ...prev,
                          Transformations: prev.Transformations.filter(
                              (t) => !pendingDeleteIds.includes(t.Id)
                          ),
                      }
                    : prev
            );
        } catch (err) {
            console.error('Failed to delete transformations', err);
        } finally {
            setDeleting(false);
            setDeleteDialogOpen(false);
            setPendingDeleteIds([]);
            cleanupSelection();
        }
    }, [pendingDeleteIds, cleanupSelection]);

    const cancelDelete = useCallback(() => {
        setDeleteDialogOpen(false);
        setPendingDeleteIds([]);
        cleanupSelection();
    }, [cleanupSelection]);

    const openExpressionEditor = useCallback(
        (t: DisplayTransformationData) => {
            setEditingTransformation(t);
            let path: string | null = null;
            try {
                const entityIdPath: string | null | undefined = (t.TargetAttribute as any)?.EntityIdPath || null;
                const attrId = t.TargetAttribute?.AttributeId;
                if (targetModel && entityIdPath && attrId) {
                    // Build entity lookup by id -> name
                    const map = new Map<number, string>();
                    const build = (nodes: any[]) => {
                        nodes.forEach(n => {
                            const ewa: any = n.Entity;
                            const meta = ewa?.Entity?.Id ? ewa.Entity : ewa;
                            if (meta?.Id && meta?.Name) map.set(meta.Id, meta.Name);
                            if (n.Children?.length) build(n.Children);
                        });
                    };
                    if (targetModel.EntityTree) build(targetModel.EntityTree);
                    const idSegments = entityIdPath.split('.').map(s => parseInt(s, 10)).filter(n => !isNaN(n));
                    const entityNames = idSegments.map(id => map.get(id)).filter(Boolean) as string[];
                    // Find attribute name in target model: search in Entities list by attribute id
                    let attrName: string | null = null;
                    if (targetModel.Entities) {
                        for (const ewa of targetModel.Entities) {
                            const found = ewa.Attributes.find(a => a.Id === attrId);
                            if (found) { attrName = found.Name; break; }
                        }
                    }
                    if (entityNames.length && attrName) {
                        path = [...entityNames, attrName].join('.');
                    } else if (attrName) {
                        path = attrName;
                    }
                } else if (t.TargetAttribute?.AttributeId && targetModel?.Entities) {
                    // Fallback: just attribute name
                    for (const ewa of targetModel.Entities) {
                        const found = ewa.Attributes.find(a => a.Id === t.TargetAttribute?.AttributeId);
                        if (found) { path = found.Name; break; }
                    }
                }
            } catch {
                // ignore errors, leave path null
            }
            setEditingTargetPath(path);
            // Build JSON Schema for target model (once per open) if available
            try {
                if (targetModel?.EntityTree) {
                    const schema = generateJsonSchema(targetModel, targetModel.EntityTree);
                    setTargetJsonSchema(schema);
                } else {
                    setTargetJsonSchema(null);
                }
                if (sourceModel?.EntityTree) {
                    const srcSchema = generateJsonSchema(sourceModel, sourceModel.EntityTree);
                    setSourceJsonSchema(srcSchema);
                } else {
                    setSourceJsonSchema(null);
                }
            } catch (e) {
                console.warn('Failed generating target JSON schema', e);
                setTargetJsonSchema(null);
                setSourceJsonSchema(null);
            }
            setExprDialogOpen(true);
        },
        [targetModel, sourceModel]
    );

    const handleExpressionSave = useCallback(
        async (update: {
            expression: string;
            expressionLanguage: string;
            name?: string;
        }) => {
            if (!editingTransformation) return;
            try {
                const updated = await updateTransformation(
                    editingTransformation.Id,
                    {
                        TransformationGroupId: editingTransformation.TransformationGroupId,
                        Expression: update.expression,
                        ExpressionLanguage: update.expressionLanguage as any,
                        Name: update.name || editingTransformation.Name,
                    } as any
                );
                setTransformations((prev) =>
                    prev.map((p) => (p.Id === updated.Id ? { ...p, ...updated } : p))
                );
                setGroup((prev) =>
                    prev
                        ? {
                              ...prev,
                              Transformations: prev.Transformations.map((t) =>
                                  t.Id === updated.Id ? { ...t, ...updated } : t
                              ),
                          }
                        : prev
                );
            } catch (err) {
                console.error('Failed to update transformation expression', err);
            } finally {
                setExprDialogOpen(false);
                setEditingTransformation(null);
            }
        },
        [editingTransformation]
    );

    const handleExpressionCancel = useCallback(() => {
        setExprDialogOpen(false);
        setEditingTransformation(null);
    }, []);

    const scrollAttrIntoView = useCallback(
        (side: 'left' | 'right', attrId: number) => {
            const container =
                side === 'left' ? leftScrollRef.current : rightScrollRef.current;
            const map =
                side === 'left'
                    ? attrElementsLeft.current
                    : attrElementsRight.current;
            if (!container) return;
            const el = map.get(String(attrId));
            if (!el) return;
            const containerRect = container.getBoundingClientRect();
            const elRect = el.getBoundingClientRect();
            const offsetTop = elRect.top - containerRect.top + container.scrollTop;
            const targetScrollTop = Math.max(
                0,
                offsetTop - (container.clientHeight / 2 - elRect.height / 2)
            );
            container.scrollTo({ top: targetScrollTop, behavior: 'smooth' });
        },
        []
    );

    const handleSourceDotDoubleClick = useCallback(
        (sourceAttrId: number) => {
            const first = transformations.find(
                (t) =>
                    (t as any).SourceAttributes?.[0]?.AttributeId === sourceAttrId &&
                    t.TargetAttribute?.AttributeId != null
            );
            if (first?.TargetAttribute?.AttributeId) {
                scrollAttrIntoView('right', first.TargetAttribute.AttributeId);
            }
        },
        [transformations, scrollAttrIntoView]
    );

    const handleWireDoubleClick = useCallback(
        (transformationId: number) => {
            const t = transformations.find((x) => x.Id === transformationId);
            if (!t) return;
            // Keep existing UX of centering the connected attributes
            const srcId = (t as any).SourceAttributes?.[0]?.AttributeId;
            const tgtId = t.TargetAttribute?.AttributeId;
            if (srcId) scrollAttrIntoView('left', srcId);
            if (tgtId) scrollAttrIntoView('right', tgtId);
            // Also open the expression editor on double-click
            openExpressionEditor(t);
        },
        [transformations, scrollAttrIntoView, openExpressionEditor]
    );

    const fetchTransformations = useCallback(async () => {
        if (!allModels?.length) return; // wait for models to load
        const seq = ++loadSeqRef.current;
        if (!groupId || groupId < 0) {
            // If no groupdId but selected source has transformation, go to first matching group
            if (allGroups?.length) {
                const trans = allGroups.find((g) => g.SourceDataModelId === selectedSourceId && g.TargetDataModelId === selectedTargetId);
                const transId = trans?.TransformationGroupId || 0;
                if (transId) { navigate(`/explore/data-mappings/${transId}`); return; }
            }

            // No group selected: clear group and transformations, but ensure models are loaded based on source selection and default target (1)
            if (seq !== loadSeqRef.current) return;
            setGroup(null);
            setTransformations([]);
            const srcId =
                selectedSourceId ?? (allModels.length ? allModels[0]?.Id : null);
            const fallbackTarget =
                selectedTargetId ??
                (orgLifModels.length === 1
                    ? orgLifModels[0]?.Id
                    : orgLifModels[0]?.Id ?? null);
            const tgtId = fallbackTarget ?? null;
            if (!srcId) return;
            if (!tgtId) return;

            const needSrc = loadedSourceModelId !== srcId || !sourceModel;
            const needTgt = loadedTargetModelId !== tgtId || !targetModel;
            let srcDetails: DataModelWithDetailsWithTree | null = sourceModel;
            let tgtDetails: DataModelWithDetailsWithTree | null = targetModel;
            if (needSrc) setSourceLoading(true);
            if (needTgt) setTargetLoading(true);
            if (needSrc && needTgt) {
                const [s, t] = await Promise.all([
                    getModelDetailsWithTree(Number(srcId)),
                    getModelDetailsWithTree(Number(tgtId)),
                ]);
                srcDetails = s;
                tgtDetails = t;
            } else if (needSrc) {
                srcDetails = await getModelDetailsWithTree(Number(srcId));
            } else if (needTgt) {
                tgtDetails = await getModelDetailsWithTree(Number(tgtId));
            }
            if (seq !== loadSeqRef.current) return;
            if (needSrc && srcDetails) {
                setSourceModel(srcDetails);
                setLoadedSourceModelId(srcId);
            }
            if (needTgt && tgtDetails) {
                setTargetModel(tgtDetails);
                setLoadedTargetModelId(tgtId);
            }
            if (needSrc) setSourceLoading(false);
            if (needTgt) setTargetLoading(false);

            // Build entity map for hover/selection consistency
            const entityById = new Map<number, EntityDTO>();
            const addEntities = (model: DataModelWithDetailsWithTree | null) => {
                model?.Entities?.forEach((item) => {
                    if (item?.Entity?.Id != null) {
                        entityById.set(item.Entity.Id, item.Entity);
                    }
                });
            };
            addEntities(srcDetails);
            addEntities(tgtDetails);
            entityByIdRef.current = entityById;
            setError(null);
            return;
        }

        const transformationsResponse = await getTransformationsForGroup(groupId, false);
        if (!transformationsResponse) {
            if (seq !== loadSeqRef.current) return;
            setError('Failed to load transformations');
            setTransformations([]);
            return;
        }

        if (seq !== loadSeqRef.current) return;
        setError(null);
        const groupData = transformationsResponse.data;
        setGroup(groupData);

        // Normalize target model id to default to 1 unless explicitly set by the group
        const effectiveTargetModelId =
            groupData.TargetDataModelId && groupData.TargetDataModelId > 0
                ? groupData.TargetDataModelId
                : selectedTargetId ?? (orgLifModels.length ? orgLifModels[0].Id : 1);

        // Only fetch model details if the Source/Target model IDs changed
        const needSrc = loadedSourceModelId !== groupData.SourceDataModelId || !sourceModel;
        const needTgt = loadedTargetModelId !== effectiveTargetModelId || !targetModel;

        let srcDetails: DataModelWithDetailsWithTree | null = sourceModel;
        let tgtDetails: DataModelWithDetailsWithTree | null = targetModel;

        if (needSrc) setSourceLoading(true);
        if (needTgt) setTargetLoading(true);
        if (needSrc && needTgt) {
            const [s, t] = await Promise.all([
                getModelDetailsWithTree(Number(groupData.SourceDataModelId)),
                getModelDetailsWithTree(Number(effectiveTargetModelId)),
            ]);
            srcDetails = s;
            tgtDetails = t;
        } else if (needSrc) {
            srcDetails = await getModelDetailsWithTree(Number(groupData.SourceDataModelId));
        } else if (needTgt) {
            tgtDetails = await getModelDetailsWithTree(Number(effectiveTargetModelId));
        }
        if (seq !== loadSeqRef.current) return;
        if (needSrc && srcDetails) {
            setSourceModel(srcDetails);
            setLoadedSourceModelId(groupData.SourceDataModelId);
        }
        if (needTgt && tgtDetails) {
            setTargetModel(tgtDetails);
            setLoadedTargetModelId(effectiveTargetModelId);
        }
        if (needSrc) setSourceLoading(false);
        if (needTgt) setTargetLoading(false);

        const entityById = new Map<number, EntityDTO>();
        const addEntities = (model: DataModelWithDetailsWithTree | null) => {
            model?.Entities?.forEach((item) => {
                if (item?.Entity?.Id != null) {
                    entityById.set(item.Entity.Id, item.Entity);
                }
            });
        };
        addEntities(srcDetails);
        addEntities(tgtDetails);
        entityByIdRef.current = entityById;

        // Preserve full multi-source attribute list so a wire can be rendered for each source attribute.
        const transformationData: DisplayTransformationData[] = groupData.Transformations.map((xform) => {
            // Choose first source only for SourceEntity convenience, but keep entire array for rendering
            const firstSrc = (xform as any).SourceAttributes?.[0];
            const sourceEntity = entityById.get(firstSrc?.EntityId);
            const targetEntity = entityById.get(xform.TargetAttribute?.EntityId);
            return {
                ...xform,
                SourceAttributes: (xform as any).SourceAttributes,
                SourceEntity: sourceEntity,
                TargetEntity: targetEntity,
            } as any;
        });
        if (seq !== loadSeqRef.current) return;
        setTransformations(transformationData);
    }, [
        groupId,
        selectedSourceId,
        allModels,
        orgLifModels,
        loadedSourceModelId,
        loadedTargetModelId,
        sourceModel,
        targetModel,
        selectedTargetId,
    ]);

    const getTransformationGroups = async () => {
        const groups = await listAllTransformationGroups();
        if (!groups) {
            console.error('Error fetching data');
            return;
        }
        setAllGroups(groups);
    };

    useEffect(() => {
        if (groupIdParam != null) {
            const id = parseInt(groupIdParam, 10);
            if (!isNaN(id)) {
                setGroupId(id);
                setError(null);
            } else {
                setError('Invalid group ID parameter');
            }
        } else {
            // No param: go to no-group mode (-1)
            setGroupId(-1);
            setError(null);
        }
    }, [groupIdParam]);

    useEffect(() => {
        fetchTransformations();
        getTransformationGroups();
    }, [fetchTransformations]);

    // search items now derived via useSearchItems hook

    // Keep version map updated when current group changes
    useEffect(() => {
        if (!group) return;
        setVersionByGroupId((prev) => ({
            ...prev,
            [group.Id]: group.GroupVersion,
        }));
    }, [group]);

    // When we have group + all groups, ensure we know versions for same source/target pairs
    useEffect(() => {
        const ensurePairVersions = async () => {
            // console.log('Ensuring pair versions for group', group, allGroups);
            if (!group || !allGroups) return;
            const normalize = (id?: number) => (id && id > 0 ? id : 1);
            const pair = allGroups.filter(
                (g) =>
                    g.SourceDataModelId === group.SourceDataModelId &&
                    normalize(g.TargetDataModelId) ===
                        normalize(group.TargetDataModelId)
            );
            const missing = pair
                .map((g) => g.TransformationGroupId)
                .filter((id) => versionByGroupId[id] == null);
            if (!missing.length) return;
            // Fetch details for missing ids in parallel
            const results = await Promise.all(
                missing.map(async (id) => {
                    try {
                        const resp = await getTransformationsForGroup(
                            id,
                            false
                        );
                        return { id, version: resp?.data.GroupVersion } as {
                            id: number;
                            version?: string;
                        };
                    } catch {
                        return { id, version: undefined };
                    }
                })
            );
            setVersionByGroupId((prev) => {
                const next = { ...prev };
                for (const r of results) if (r.version) next[r.id] = r.version;
                return next;
            });
        };
        ensurePairVersions();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [group, allGroups]);

    // Update next-version preview when dialog opens or bump changes
    useEffect(() => {
        const updatePreview = async () => {
            if (!forkDialogOpen || !group) return;
            try {
                const { computeNextVersion } = await import(
                    '../../../services/transformationsService'
                );
                const next = await computeNextVersion(group.Id, forkBump);
                setForkPreview(next);
            } catch {
                setForkPreview('');
            }
        };
        updatePreview();
    }, [forkDialogOpen, forkBump, group]);

    // Generate JSON Schemas proactively when models are loaded so bulk dialog has sample data
    useEffect(() => {
        try {
            if (sourceModel?.EntityTree) {
                const sch = generateJsonSchema(sourceModel, sourceModel.EntityTree);
                setSourceJsonSchema(sch);
            }
        } catch {
            setSourceJsonSchema(null);
        }
        try {
            if (targetModel?.EntityTree) {
                const sch = generateJsonSchema(targetModel, targetModel.EntityTree);
                setTargetJsonSchema(sch);
            }
        } catch {
            setTargetJsonSchema(null);
        }
    }, [sourceModel, targetModel]);

    // Load only SourceSchema models for source dropdown
    useEffect(() => {
        const loadModels = async () => {
            try {
                const data = await listModels({ type: 'SourceSchema' });
                const list = Array.isArray(data)
                    ? (data as any[]).map((m) => ({ Id: m.Id, Name: m.Name }))
                    : [];
                const sorted = list
                    .slice()
                    .sort((a, b) =>
                        String(a.Name || '').localeCompare(String(b.Name || ''))
                    );
                setAllModels(sorted);
                if (selectedSourceId == null && sorted.length) {
                    setSelectedSourceId(sorted[0].Id);
                }
            } catch (e) {
                console.error('Failed to load models', e);
            }
        };
        loadModels();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Load OrgLIF target models
    useEffect(() => {
        const loadTargets = async () => {
            try {
                const data = await listOrgLifModels();
                const list = Array.isArray(data)
                    ? (data as any[]).map((m) => ({ Id: m.Id, Name: m.Name }))
                    : [];
                const sorted = list
                    .slice()
                    .sort((a, b) =>
                        String(a.Name || '').localeCompare(String(b.Name || ''))
                    );
                setOrgLifModels(sorted);
                // Auto-select when single; otherwise keep existing selection or choose first
                if (sorted.length === 1) {
                    setSelectedTargetId(sorted[0].Id);
                } else if (selectedTargetId == null && sorted.length > 0) {
                    setSelectedTargetId(sorted[0].Id);
                }
            } catch (e) {
                console.error('Failed to load OrgLIF target models', e);
            }
        };
        loadTargets();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Keep selected source/target in sync with loaded group
    useEffect(() => {
        if (
            group &&
            group.SourceDataModelId &&
            group.SourceDataModelId !== selectedSourceId
        ) {
            setSelectedSourceId(group.SourceDataModelId);
        }
        if (
            group &&
            group.TargetDataModelId &&
            group.TargetDataModelId > 0 &&
            group.TargetDataModelId !== selectedTargetId
        ) {
            setSelectedTargetId(group.TargetDataModelId);
        }
    }, [group]);

    const latestVersionGroupForPair = useCallback(
        (sourceId: number, targetId: number) => {
            if (!allGroups || !allGroups.length) return null;
            const normalize = (id?: number) => (id && id > 0 ? id : 1);
            const filtered = allGroups.filter(
                (g) =>
                    g.SourceDataModelId === sourceId &&
                    normalize(g.TargetDataModelId) === normalize(targetId)
            );
            if (!filtered.length) return null;
            const parseParts = (v?: string) => {
                const m = String(v || '0.0').match(/(\d+)\.(\d+)/);
                return {
                    major: m ? parseInt(m[1], 10) : 0,
                    minor: m ? parseInt(m[2], 10) : 0,
                };
            };
            const sorted = filtered.slice().sort((a, b) => {
                const va = parseParts(
                    versionByGroupId[a.TransformationGroupId]
                );
                const vb = parseParts(
                    versionByGroupId[b.TransformationGroupId]
                );
                return vb.major - va.major || vb.minor - va.minor;
            });
            return sorted[0] || null;
        },
        [allGroups, versionByGroupId]
    );

    // Count groups for a given source pointing to selected target (default normalize to 1 when absent)
    const countGroupsForSource = useCallback(
        (sourceId: number) => {
            if (!allGroups) return 0;
            const normalize = (id?: number) => (id && id > 0 ? id : 1);
            const targetId = selectedTargetId ?? 1;
            return allGroups.filter(
                (g) =>
                    g.SourceDataModelId === sourceId &&
                    normalize(g.TargetDataModelId) === normalize(targetId)
            ).length;
        },
        [allGroups, selectedTargetId]
    );

    const onChangeSourceModel = useCallback(
        (nextId: number) => {
            // Update selection
            setSelectedSourceId(nextId);
            // Proactively clear stale UI state to avoid partial remnants
            setGroup(null);
            setTransformations([]);
            setWirePaths([]);
            setSourceModel(null);
            setLoadedSourceModelId(null);
            setSourceLoading(true);
            setHoveredAttrKey(null);
            cleanupSelection();

            // Anchor to selected target when switching sources
            const targetId =
                selectedTargetId ??
                (orgLifModels.length ? orgLifModels[0].Id : 1);
            const latest = latestVersionGroupForPair(nextId, targetId);
            if (latest) {
                navigate(
                    `/explore/data-mappings/${latest.TransformationGroupId}`
                );
            } else {
                navigate(`/explore/data-mappings`);
            }
        },
        [
            group,
            latestVersionGroupForPair,
            navigate,
            cleanupSelection,
            selectedTargetId,
            orgLifModels,
        ]
    );

    const onChangeTargetModel = useCallback(
        (nextId: number) => {
            // Update selection
            setSelectedTargetId(nextId);
            // Clear stale UI when switching target
            setGroup(null);
            setTransformations([]);
            setWirePaths([]);
            setTargetModel(null);
            setLoadedTargetModelId(null);
            setTargetLoading(true);
            setHoveredAttrKey(null);
            cleanupSelection();

            const sourceId =
                selectedSourceId ??
                (allModels.length ? allModels[0].Id : undefined);
            if (sourceId) {
                const latest = latestVersionGroupForPair(sourceId, nextId);
                if (latest) {
                    navigate(
                        `/explore/data-mappings/${latest.TransformationGroupId}`
                    );
                    return;
                }
            }
            navigate(`/explore/data-mappings`);
        },
        [
            selectedSourceId,
            allModels,
            latestVersionGroupForPair,
            navigate,
            cleanupSelection,
        ]
    );

    const handleCreateNewMapping = useCallback(async () => {
        const srcId =
            selectedSourceId ?? (allModels.length ? allModels[0]?.Id : null);
        const tgtId =
            selectedTargetId ??
            (orgLifModels.length ? orgLifModels[0]?.Id : null);
        if (!srcId || !tgtId) return;
        try {
            // Determine next free MAJOR version for Source/Target (including deleted groups)
            let major = 1;
            while (true) {
                const ver = `${major}.0`;
                const exists = await existsTransformationGroup(
                    srcId,
                    tgtId,
                    ver,
                    true
                );
                if (!exists?.exists) break;
                major += 1;
                if (major > 999) break; // safety cap
            }
            // Default group name as "SourceModelName_TargetModelName"
            const srcName = (
                allModels.find((m) => m.Id === srcId)?.Name || ''
            ).trim();
            const tgtName = (
                orgLifModels.find((m) => m.Id === tgtId)?.Name || ''
            ).trim();
            const defaultGroupName =
                srcName && tgtName ? `${srcName}_${tgtName}` : '';

            const payload: CreateTransformationGroup = {
                SourceDataModelId: srcId,
                TargetDataModelId: tgtId,
                Name: defaultGroupName,
                GroupVersion: `${major}.0`,
            };
            // Attempt creation; if a race causes a 409, bump major and retry a few times
            let created: any = null;
            for (let attempt = 0; attempt < 5; attempt++) {
                try {
                    created = await createTransformationGroup(payload);
                    break;
                } catch (e: any) {
                    const status = e?.response?.status;
                    if (status === 409) {
                        major += 1;
                        payload.GroupVersion = `${major}.0`;
                        continue;
                    }
                    throw e;
                }
            }
            if (!created) return;
            // Update caches for quick version lookup
            setAllGroups((prev) => {
                const base = prev || [];
                const item: TranformationGroupData = {
                    TransformationGroupId: created.Id,
                    SourceDataModelId: created.SourceDataModelId,
                    SourceDataModelName: created.SourceDataModelName || '',
                    TargetDataModelId: created.TargetDataModelId,
                    TargetDataModelName: created.TargetDataModelName || '',
                } as any;
                return [...base, item];
            });
            setVersionByGroupId((prev) => ({
                ...prev,
                [created.Id]: created.GroupVersion || `${major}.0`,
            }));
            navigate(`/explore/data-mappings/${created.Id}`);
        } catch (e) {
            // Ignored fallback path handled below
        }
    }, [selectedSourceId, allModels, navigate]);

    // Global drag for creating a transform
    useEffect(() => {
        if (!isDragging) return;
        const handleMove = (e: MouseEvent) => {
            if (!isDragging || !dragSourceAttr) return;
            const containerRect = (
                wiresSlotRef.current || containerRef.current
            )?.getBoundingClientRect();
            if (!containerRect) return;
            const srcKey = dragSourcePath
                ? `${dragSourcePath}|${dragSourceAttr.Id}`
                : String(dragSourceAttr.Id);
            const sourceEl = attrElementsLeft.current.get(srcKey);
            if (!sourceEl) return;
            const leftDot =
                sourceEl.querySelector<HTMLElement>(
                    '.mappings-column__dot--end'
                ) || sourceEl;
            const lb = leftDot.getBoundingClientRect();
            const startX = lb.left + lb.width / 2 - containerRect.left;
            const startY = lb.top + lb.height / 2 - containerRect.top;
            const endX = e.clientX - containerRect.left;
            const endY = e.clientY - containerRect.top;
            const dx = endX - startX;
            const c1x = startX + dx * 0.35;
            const c2x = endX - dx * 0.35;
            setDragPath(
                `M ${startX} ${startY} C ${c1x} ${startY}, ${c2x} ${endY}, ${endX} ${endY}`
            );
            const el = document.elementFromPoint(
                e.clientX,
                e.clientY
            ) as HTMLElement | null;
            let node: HTMLElement | null = el;
            let targetId: number | null = null;
            let targetPath: string | null = null;
            while (node) {
                if (
                    node.classList?.contains('mappings-attr') &&
                    node.dataset.attrId
                ) {
                    if (node.classList.contains('mappings-attr--right'))
                        targetId = Number(node.dataset.attrId);
                    targetPath = (node as any).dataset?.entityPath || null;
                    break;
                }
                node = node.parentElement;
            }
            setDragTargetAttrId(targetId);
            setDragTargetPath(targetPath);
        };
        const handleUp = async () => {
            setIsDragging(false);
            setDragPath(null);
            if (dragSourceAttr && dragTargetAttrId && group) {
                try {
                    // Determine Source/Target EntityIdPaths
                    const srcPath =
                        dragSourcePath ??
                        (() => {
                            const ents = sourceModel?.EntityTree ?? [];
                            const stack = [...ents];
                            while (stack.length) {
                                const node = stack.pop()!;
                                // Attribute is reused; check if this entity lists it
                                const ewa = node.Entity as any;
                                const has = (ewa?.Attributes || []).some(
                                    (a: any) => a?.Id === dragSourceAttr.Id
                                );
                                if (has) return node.PathId; // EntityIdPath
                                stack.push(...(node.Children || []));
                            }
                            return undefined;
                        })();
                    const tgtPath =
                        dragTargetPath ??
                        (() => {
                            const ents = targetModel?.EntityTree ?? [];
                            const stack = [...ents];
                            while (stack.length) {
                                const node = stack.pop()!;
                                const ewa = node.Entity as any;
                                const has = (ewa?.Attributes || []).some(
                                    (a: any) => a?.Id === dragTargetAttrId
                                );
                                if (has) return node.PathId;
                                stack.push(...(node.Children || []));
                            }
                            return undefined;
                        })();

                    // Enforce 1 transformation per target (EntityIdPath+AttributeId)
                    const existing = (group.Transformations || []).find((t) => {
                        const tid = t.TargetAttribute?.AttributeId;
                        const tpath =
                            (t.TargetAttribute as any)?.EntityIdPath || null;
                        return (
                            tid === dragTargetAttrId &&
                            String(tpath || '') === String(tgtPath || '')
                        );
                    });

                    if (existing) {
                        // Merge: add source attribute if not present
                        const currentSrcs: any[] = Array.isArray(
                            (existing as any).SourceAttributes
                        )
                            ? ((existing as any).SourceAttributes as any[])
                            : (existing as any).SourceAttributes?.[0]?.AttributeId
                            ? [
                                  {
                                      AttributeId:
                                          (existing as any).SourceAttributes?.[0]?.AttributeId,
                                      AttributeType:
                                          (existing as any).SourceAttributes?.[0]
                                              .AttributeType || 'Source',
                                      EntityIdPath: (
                                          (existing as any).SourceAttributes?.[0] as any
                                      )?.EntityIdPath,
                                      EntityId: (() => {
                                          const p = (
                                              (existing as any).SourceAttributes?.[0] as any
                                          )?.EntityIdPath as string | undefined;
                                          const seg = p
                                              ? String(p).split('.').pop()
                                              : undefined;
                                          const idn = seg
                                              ? Number(seg)
                                              : undefined;
                                          return Number.isFinite(idn as any)
                                              ? (idn as number)
                                              : ((existing as any).SourceAttributes?.[0] as any)?.EntityId;
                                      })(),
                                  },
                              ]
                            : [];
                        const key = (sa: any) =>
                            `${sa.EntityIdPath || ''}|${sa.AttributeId}`;
                        const nextSrcs = [...currentSrcs];
                        const deriveEntityIdForUpdate = (
                            path: string | null | undefined,
                            attrId: number | undefined
                        ): number | undefined => {
                            if (!attrId) return undefined;
                            if (path) {
                                const seg = String(path).split('.').pop();
                                if (seg && /^\d+$/.test(seg)) {
                                    const n = Number(seg);
                                    if (Number.isFinite(n)) return n;
                                }
                            }
                            // Scan source model as fallback
                            const ents = sourceModel?.Entities || [];
                            for (const ewa of ents as any[]) {
                                const found = ewa.Attributes?.find((a: any) => a.Id === attrId);
                                if (found) return ewa.Entity?.Id;
                            }
                            return undefined;
                        };
                        const newSrc = {
                            AttributeId: dragSourceAttr.Id,
                            AttributeType: 'Source',
                            EntityIdPath: srcPath,
                            EntityId: deriveEntityIdForUpdate(srcPath, dragSourceAttr.Id),
                        } as any;
                        if (!nextSrcs.some((s) => key(s) === key(newSrc))) {
                            nextSrcs.push(newSrc);
                        }
                        const updated = await updateTransformationAttributes(
                            existing.Id,
                            {
                                SourceAttributes: nextSrcs,
                            },
                            group.Id
                        );
                        // Update local state
                        setTransformations((prev) => prev.map((p) => (p.Id === existing.Id ? ({ ...p, ...(updated || {}) } as any) : p)));
                        setGroup((prev) =>
                            prev
                                ? {
                                      ...prev,
                                      Transformations: prev.Transformations.map(
                                          (t) =>
                                              t.Id === existing.Id
                                                  ? ({
                                                        ...(updated || t),
                                                    } as any)
                                                  : t
                                      ),
                                  }
                                : prev
                        );
                    } else {
                        // Create new transformation with attributes
                        const deriveEntityId = (
                            path: string | null | undefined,
                            attrId: number | undefined,
                            modelRef: typeof sourceModel | typeof targetModel
                        ): number | undefined => {
                            if (!attrId) return undefined;
                            // 1. Try final numeric segment of path
                            if (path) {
                                const seg = String(path).split('.').pop();
                                if (seg && /^\d+$/.test(seg)) {
                                    const n = Number(seg);
                                    if (Number.isFinite(n)) return n;
                                }
                            }
                            // 2. Scan model for entity containing attribute
                            const ents = modelRef?.Entities || [];
                            for (const ewa of ents as any[]) {
                                const found = ewa.Attributes?.find((a: any) => a.Id === attrId);
                                if (found) return ewa.Entity?.Id; // ewa itself does not expose Id directly
                            }
                            return undefined;
                        };
                        const srcAttrPayload = {
                            AttributeId: dragSourceAttr.Id,
                            AttributeType: 'Source',
                            EntityIdPath: srcPath,
                            EntityId:
                                deriveEntityId(srcPath, dragSourceAttr.Id, sourceModel),
                        } as any;
                        const tgtAttrPayload = {
                            AttributeId: dragTargetAttrId,
                            AttributeType: 'Target',
                            EntityIdPath: tgtPath,
                            EntityId: deriveEntityId(tgtPath, dragTargetAttrId, targetModel),
                        } as any;
                        // Build source & target JSONata paths for naming and default expression
                        const sourcePathExpr = buildDirectKeyExpression(
                            srcPath,
                            dragSourceAttr?.Name || null
                        );
                        const targetAttrName = (() => {
                            if (targetModel?.Entities) {
                                for (const ewa of targetModel.Entities) {
                                    const found = ewa.Attributes.find(
                                        (a) => a.Id === dragTargetAttrId
                                    );
                                    if (found) return found.Name;
                                }
                            }
                            return `Attr_${dragTargetAttrId}`;
                        })();
                        const targetPathExpr = buildDirectKeyExpression(
                            tgtPath,
                            targetAttrName
                        ) || targetAttrName;
                        // Build JSON Schemas (once) and derive default expression using util
                        let srcSchema: any = null;
                        let tgtSchema: any = null;
                        try {
                            if (sourceModel?.EntityTree) srcSchema = generateJsonSchema(sourceModel, sourceModel.EntityTree);
                        } catch { /* ignore */ }
                        try {
                            if (targetModel?.EntityTree) tgtSchema = generateJsonSchema(targetModel, targetModel.EntityTree);
                        } catch { /* ignore */ }
                        const equalityExpr = buildDefaultAssignmentExpression(
                            srcSchema,
                            tgtSchema,
                            sourcePathExpr || '',
                            targetPathExpr || ''
                        ) || (targetPathExpr && sourcePathExpr ? `${targetPathExpr} = ${sourcePathExpr}` : sourcePathExpr || targetPathExpr || '');
                        const created = await createTransformation({
                            TransformationGroupId: group.Id,
                            ExpressionLanguage: 'JSONata',
                            Expression: equalityExpr,
                            Name: targetPathExpr,
                            SourceAttributes: [srcAttrPayload],
                            TargetAttribute: tgtAttrPayload,
                        });
                        const createdWithAttrs: any = {
                            ...created,
                            SourceAttributes: (created as any)
                                ?.SourceAttributes ?? [srcAttrPayload],
                            TargetAttribute:
                                (created as any)?.TargetAttribute ??
                                tgtAttrPayload,
                        };
                        setTransformations((prev) => {
                            const firstSrc = createdWithAttrs.SourceAttributes?.[0];
                            const srcEntity = entityByIdRef.current.get(firstSrc?.EntityId);
                            const tgtEntity = entityByIdRef.current.get(createdWithAttrs.TargetAttribute?.EntityId);
                            return [
                                ...prev,
                                {
                                    ...(createdWithAttrs || {}),
                                    SourceEntity: srcEntity,
                                    TargetEntity: tgtEntity,
                                } as any,
                            ];
                        });
                        setGroup((prev) =>
                            prev
                                ? {
                                      ...prev,
                                      Transformations: [
                                          ...prev.Transformations,
                                          created as any,
                                      ],
                                  }
                                : prev
                        );
                    }
                } catch (err) {
                    console.error('Failed to create transformation', err);
                }
            }
            setDragSourceAttr(null);
            setDragSourcePath(null);
            setDragTargetAttrId(null);
            setDragTargetPath(null);
        };
        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp, { once: true });
        return () => {
            window.removeEventListener('mousemove', handleMove);
            window.removeEventListener('mouseup', handleUp);
        };
    }, [isDragging, dragSourceAttr, dragTargetAttrId, group]);

    // Multi-wire detach drag (remove one or more selected sources from a transformation)
    useEffect(() => {
        if (!wireDetachDragging) return;
        const { transId, srcAttrIds } = wireDetachDragging;
        // Defensive: ensure uniqueness (prevents duplicate dashed paths if drag started during a transient multi-select state)
        const uniqueSrcAttrIds = Array.from(new Set(srcAttrIds));
        const transformation = transformations.find(t => t.Id === transId);
        if (!transformation) return;
        const containerRect = (wiresSlotRef.current || containerRef.current)?.getBoundingClientRect();
        if (!containerRect) return;

        const computeStart = (srcAttrId: number) => {
            const srcEntry = (transformation as any).SourceAttributes?.find((s: any) => s.AttributeId === srcAttrId);
            const srcKey = srcEntry?.EntityIdPath ? `${srcEntry.EntityIdPath}|${srcAttrId}` : String(srcAttrId);
            const leftEl = attrElementsLeft.current.get(srcKey) || attrElementsLeft.current.get(String(srcAttrId));
            const leftDot = leftEl?.querySelector<HTMLElement>('.mappings-column__dot--end') || leftEl || null;
            const lb = leftDot?.getBoundingClientRect();
            const startX = lb ? lb.left + lb.width / 2 - containerRect.left : 0;
            const startY = lb ? lb.top + lb.height / 2 - containerRect.top : 0;
            return { startX, startY };
        };

        const handleMove = (e: MouseEvent) => {
            const endX = e.clientX - containerRect.left;
            const endY = e.clientY - containerRect.top;
            const newPaths: Array<{ srcAttrId: number; d: string }> = [];
            uniqueSrcAttrIds.forEach(srcAttrId => {
                const { startX, startY } = computeStart(srcAttrId);
                const dx = endX - startX;
                const c1x = startX + dx * 0.35;
                const c2x = endX - dx * 0.35;
                // Avoid duplicate entries for same srcAttrId (shouldn't happen, but guard)
                if (!newPaths.some(p => p.srcAttrId === srcAttrId)) {
                    newPaths.push({ srcAttrId, d: `M ${startX} ${startY} C ${c1x} ${startY}, ${c2x} ${endY}, ${endX} ${endY}` });
                }
            });
            setWireDetachPaths(newPaths);
        };

        const handleUp = async (e: MouseEvent) => {
            // If no movement happened (no path drawn) treat as a normal click selection.
            if (wireDetachPaths.length === 0) {
                setWireDetachDragging(null);
                setWireDetachPaths([]);
                return;
            }
            // Determine if dropped over a target attribute; if so ignore (future reassignment maybe)
            const dropEl = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
            let overRightAttr = false;
            let node: HTMLElement | null = dropEl;
            while (node) {
                if (node.classList?.contains('mappings-attr') && node.classList.contains('mappings-attr--right')) { overRightAttr = true; break; }
                node = node.parentElement;
            }
            if (!overRightAttr) {
                const originalList: any[] = Array.isArray((transformation as any).SourceAttributes) ? [...(transformation as any).SourceAttributes] : [];
                const remaining = originalList.filter(s => !uniqueSrcAttrIds.includes(s.AttributeId));
                const willDelete = remaining.length === 0;
                setPendingDetach({ transId, srcAttrIds: uniqueSrcAttrIds, willDelete });
                setDetachDialogOpen(true);
            } else {
                // Cancel drag if dropped on target side (no action now)
                setWireDetachDragging(null);
                setWireDetachPaths([]);
            }
        };

        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp, { once: true });
        return () => {
            window.removeEventListener('mousemove', handleMove);
            window.removeEventListener('mouseup', handleUp);
        };
    }, [wireDetachDragging, wireDetachPaths, transformations, sourceModel, group]);

    const confirmDetachSources = useCallback(async () => {
        if (!pendingDetach) return;
        const { transId, srcAttrIds, willDelete } = pendingDetach;
        const transformation = transformations.find(t => t.Id === transId);
        if (!transformation) return;
        setDetaching(true);
        try {
            if (willDelete) {
                await deleteTransformation(transformation.Id);
                setTransformations(prev => prev.filter(p => p.Id !== transformation.Id));
                setGroup(prev => prev ? { ...prev, Transformations: prev.Transformations.filter(t => t.Id !== transformation.Id) } : prev);
                setSelectedTransformationIds(prev => { const next = new Set(prev); next.delete(transformation.Id); return next; });
                setSelectedWireSourceAttrIds(new Set());
            } else {
                const originalList: any[] = Array.isArray((transformation as any).SourceAttributes) ? [...(transformation as any).SourceAttributes] : [];
                const remaining = originalList.filter(s => !srcAttrIds.includes(s.AttributeId));
                const withEntityIds = remaining.map(r => {
                    if (r.EntityId) return r;
                    const p = r.EntityIdPath as string | undefined;
                    let eid: number | undefined;
                    if (p) {
                        const seg = p.split('.').pop();
                        if (seg && /^\d+$/.test(seg)) eid = Number(seg);
                    }
                    if (!eid && sourceModel?.Entities) {
                        for (const ewa of sourceModel.Entities as any[]) {
                            const found = ewa.Attributes?.find((a: any) => a.Id === r.AttributeId);
                            if (found) { eid = ewa.Entity?.Id; break; }
                        }
                    }
                    return { ...r, EntityId: eid };
                });
                const updated = await updateTransformationAttributes(transformation.Id, { SourceAttributes: withEntityIds }, group?.Id);
                setTransformations(prev => prev.map(p => p.Id === transformation.Id ? ({ ...p, ...(updated || {} ) } as any) : p));
                setGroup(prev => prev ? { ...prev, Transformations: prev.Transformations.map(t => t.Id === transformation.Id ? ({ ...(updated || t) } as any) : t) } : prev);
                setSelectedWireSourceAttrIds(prev => { const next = new Set(prev); srcAttrIds.forEach(id => next.delete(id)); return next; });
            }
        } catch (err) {
            console.error('Failed to detach source attributes', err);
        } finally {
            setDetaching(false);
            setDetachDialogOpen(false);
            setPendingDetach(null);
            setWireDetachDragging(null);
            setWireDetachPaths([]);
        }
    }, [pendingDetach, transformations, sourceModel, group]);

    // Reassign drag listeners
    useEffect(() => {
        if (!reassignActive) return;
        const handleMove = (e: MouseEvent) => {
            if (!(e.buttons & 1)) {
                const evt = new MouseEvent('mouseup');
                window.dispatchEvent(evt);
                return;
            }
            if (!reassignActive || reassignTransformations.length === 0) return;
            const containerRect = (
                wiresSlotRef.current || containerRef.current
            )?.getBoundingClientRect();
            if (!containerRect) return;
            const cursorX = e.clientX - containerRect.left;
            const cursorY = e.clientY - containerRect.top;
            const newPaths: Array<{ id: string; d: string }> = [];
            reassignTransformations.forEach((t) => {
                const srcAttr: any =
                    (t as any).SourceAttributes?.[0];
                const srcId = srcAttr?.AttributeId;
                if (!srcId) return;
                const srcKey = srcAttr?.EntityIdPath
                    ? `${srcAttr.EntityIdPath}|${srcId}`
                    : String(srcId);
                const leftEl = attrElementsLeft.current.get(srcKey);
                if (!leftEl) return;
                const leftDot =
                    leftEl.querySelector<HTMLElement>(
                        '.mappings-column__dot--end'
                    ) || leftEl;
                const lb = leftDot.getBoundingClientRect();
                const startX = lb.left + lb.width / 2 - containerRect.left;
                const startY = lb.top + lb.height / 2 - containerRect.top;
                const dx = cursorX - startX;
                const c1x = startX + dx * 0.35;
                const c2x = cursorX - dx * 0.35;
                newPaths.push({
                    id: `reassign-${t.Id}`,
                    d: `M ${startX} ${startY} C ${c1x} ${startY}, ${c2x} ${cursorY}, ${cursorX} ${cursorY}`,
                });
            });
            setReassignPaths(newPaths);
            const el = document.elementFromPoint(
                e.clientX,
                e.clientY
            ) as HTMLElement | null;
            let node: HTMLElement | null = el;
            let targetId: number | null = null;
            while (node) {
                if (
                    node.classList?.contains('mappings-attr') &&
                    node.dataset.attrId
                ) {
                    if (node.classList.contains('mappings-attr--right'))
                        targetId = Number(node.dataset.attrId);
                    break;
                }
                node = node.parentElement;
            }
            setReassignHoverTargetId(targetId);
        };
        const handleUp = async () => {
            const droppingOnTarget =
                !!reassignHoverTargetId &&
                reassignHoverTargetId !== selectedTargetAttrId;
            if (droppingOnTarget) {
                // Determine target path from DOM or tree
                const targetAttrEl = rightScrollRef.current?.querySelector(
                    `[data-attr-id="${reassignHoverTargetId}"]`
                ) as HTMLElement | null;
                const tgtPathFromDom =
                    targetAttrEl?.dataset?.entityPath || null;
                const tgtPath =
                    tgtPathFromDom ??
                    (() => {
                        const ents = targetModel?.EntityTree ?? [];
                        const stack = [...ents];
                        while (stack.length) {
                            const node = stack.pop()!;
                            const ewa = node.Entity as any;
                            const has = (ewa?.Attributes || []).some(
                                (a: any) => a?.Id === reassignHoverTargetId
                            );
                            if (has) return node.PathId;
                            stack.push(...(node.Children || []));
                        }
                        return undefined;
                    })();

                const results: Array<TransformationData | null> = [];
                for (const t of reassignTransformations) {
                    try {
                        const firstSrc: any = (t as any).SourceAttributes?.[0];
                        // Check if a transformation already exists for this target (id+path)
                        const existing = (group?.Transformations || []).find(
                            (et) => {
                                const tid = et.TargetAttribute?.AttributeId;
                                const tpath =
                                    (et.TargetAttribute as any)?.EntityIdPath ||
                                    null;
                                return (
                                    tid === reassignHoverTargetId &&
                                    String(tpath || '') ===
                                        String(tgtPath || '')
                                );
                            }
                        );
                        if (existing) {
                            // Merge source
                            const currentSrcs: any[] = Array.isArray(
                                (existing as any).SourceAttributes
                            )
                                ? ((existing as any).SourceAttributes as any[])
                                : (existing as any).SourceAttributes?.[0]?.AttributeId
                                ? [
                                      {
                                          AttributeId:
                                              (existing as any).SourceAttributes?.[0]
                                                  .AttributeId,
                                          AttributeType:
                                              (existing as any).SourceAttributes?.[0]
                                                  .AttributeType || 'Source',
                                          EntityIdPath: (
                                              (existing as any).SourceAttributes?.[0] as any
                                          )?.EntityIdPath,
                                      },
                                  ]
                                : [];
                            const key = (sa: any) =>
                                `${sa.EntityIdPath || ''}|${sa.AttributeId}`;
                            const merged = [...currentSrcs];
                            const newSrc = {
                                AttributeId: firstSrc?.AttributeId || firstSrc?.Id,
                                AttributeType: firstSrc?.AttributeType || 'Source',
                                EntityIdPath: (firstSrc as any)?.EntityIdPath,
                                EntityId: (() => {
                                    const p = (firstSrc as any)?.EntityIdPath as string | undefined;
                                    if (p) {
                                        const seg = p.split('.').pop();
                                        if (seg && /^\d+$/.test(seg)) {
                                            const n = Number(seg);
                                            if (Number.isFinite(n)) return n;
                                        }
                                    }
                                    // fallback search target/source model
                                    const searchModels = [sourceModel, targetModel];
                                    for (const m of searchModels) {
                                        const ents = m?.Entities || [];
                                        for (const ewa of ents as any[]) {
                                            const found = ewa.Attributes?.find((a: any) => a.Id === (firstSrc?.AttributeId || firstSrc?.Id));
                                            if (found) return ewa.Entity?.Id;
                                        }
                                    }
                                    return undefined;
                                })(),
                            } as any;
                            if (
                                newSrc.AttributeId &&
                                !merged.some((s) => key(s) === key(newSrc))
                            ) {
                                merged.push(newSrc);
                            }
                            const updated =
                                await updateTransformationAttributes(
                                    existing.Id,
                                    {
                                        SourceAttributes: merged.map((s: any) => {
                                            if (s.EntityId) return s;
                                            const p = s.EntityIdPath as string | undefined;
                                            let eid: number | undefined;
                                            if (p) {
                                                const seg = p.split('.').pop();
                                                if (seg && /^\d+$/.test(seg)) {
                                                    const n = Number(seg);
                                                    if (Number.isFinite(n)) eid = n;
                                                }
                                            }
                                            if (!eid) {
                                                const attrId = s.AttributeId;
                                                const searchModels = [sourceModel];
                                                for (const m of searchModels) {
                                                    const ents = m?.Entities || [];
                                                    for (const ewa of ents as any[]) {
                                                        const found = ewa.Attributes?.find((a: any) => a.Id === attrId);
                                                        if (found) { eid = ewa.Entity?.Id; break; }
                                                    }
                                                    if (eid) break;
                                                }
                                            }
                                            return { ...s, EntityId: eid };
                                        }),
                                    },
                                    group?.Id
                                );
                            await deleteTransformation(t.Id);
                            // Update local state: remove old t and update existing
                            setTransformations((prev) => {
                                const filtered = prev.filter(
                                    (p) => p.Id !== t.Id
                                );
                                return filtered.map((p) =>
                                    p.Id === existing.Id
                                        ? ({ ...(updated || p) } as any)
                                        : p
                                );
                            });
                            setGroup((prev) =>
                                prev
                                    ? {
                                          ...prev,
                                          Transformations:
                                              prev.Transformations.filter(
                                                  (x) => x.Id !== t.Id
                                              ).map((x) =>
                                                  x.Id === existing.Id
                                                      ? ({
                                                            ...(updated || x),
                                                        } as any)
                                                      : x
                                              ),
                                      }
                                    : prev
                            );
                            results.push(updated as any);
                        } else {
                            // Create new and delete old
                            const srcAttrPayload =
                                firstSrc?.AttributeId || firstSrc?.Id
                                    ? {
                                          AttributeId:
                                              firstSrc.AttributeId ||
                                              firstSrc.Id,
                                          AttributeType:
                                              firstSrc.AttributeType ||
                                              'Source',
                                          EntityIdPath: (firstSrc as any)
                                              ?.EntityIdPath,
                                          EntityId: (() => {
                                              const p = (firstSrc as any)
                                                  ?.EntityIdPath as
                                                  | string
                                                  | undefined;
                                              const seg = p
                                                  ? String(p).split('.').pop()
                                                  : undefined;
                                              const idn = seg
                                                  ? Number(seg)
                                                  : undefined;
                                              return Number.isFinite(idn as any)
                                                  ? (idn as number)
                                                  : (firstSrc as any)?.EntityId;
                                          })(),
                                      }
                                    : undefined;
                            const deriveEntityId = (
                                path: string | null | undefined,
                                attrId: number | undefined,
                                modelRef: typeof sourceModel | typeof targetModel
                            ): number | undefined => {
                                if (!attrId) return undefined;
                                if (path) {
                                    const seg = String(path).split('.').pop();
                                    if (seg && /^\d+$/.test(seg)) {
                                        const n = Number(seg);
                                        if (Number.isFinite(n)) return n;
                                    }
                                }
                                const ents = modelRef?.Entities || [];
                                for (const ewa of ents as any[]) {
                                    const found = ewa.Attributes?.find((a: any) => a.Id === attrId);
                                    if (found) return ewa.Entity?.Id;
                                }
                                return undefined;
                            };
                            const tgtAttrPayload = {
                                AttributeId: reassignHoverTargetId!,
                                AttributeType: 'Target',
                                EntityIdPath: tgtPath,
                                EntityId: deriveEntityId(
                                    tgtPath,
                                    reassignHoverTargetId!,
                                    targetModel
                                ),
                            } as any;
                            // Build source & target JSONata paths for naming and default expression on reassignment create
                            const srcAttrName =
                                (firstSrc as any)?.AttributeName ||
                                (firstSrc as any)?.Name ||
                                undefined;
                            const sourcePathExpr = buildDirectKeyExpression(
                                (firstSrc as any)?.EntityIdPath,
                                srcAttrName || null
                            );
                            const targetAttrName = (() => {
                                if (targetModel?.Entities) {
                                    for (const ewa of targetModel.Entities) {
                                        const found = ewa.Attributes.find(
                                            (a) =>
                                                a.Id ===
                                                reassignHoverTargetId
                                        );
                                        if (found) return found.Name;
                                    }
                                }
                                return `Attr_${reassignHoverTargetId}`;
                            })();
                            const targetPathExpr =
                                buildDirectKeyExpression(
                                    tgtPath,
                                    targetAttrName
                                ) || targetAttrName;
                            let srcSchema: any = null;
                            let tgtSchema: any = null;
                            try {
                                if (sourceModel?.EntityTree) srcSchema = generateJsonSchema(sourceModel, sourceModel.EntityTree);
                            } catch { /* ignore */ }
                            try {
                                if (targetModel?.EntityTree) tgtSchema = generateJsonSchema(targetModel, targetModel.EntityTree);
                            } catch { /* ignore */ }
                            const equalityExpr = buildDefaultAssignmentExpression(
                                srcSchema,
                                tgtSchema,
                                sourcePathExpr || '',
                                targetPathExpr || ''
                            ) || (targetPathExpr && sourcePathExpr ? `${targetPathExpr} = ${sourcePathExpr}` : sourcePathExpr || targetPathExpr || '');
                            const created = await createTransformation({
                                TransformationGroupId:
                                    t.TransformationGroupId,
                                ExpressionLanguage:
                                    (t.ExpressionLanguage as any) || 'JSONata',
                                Expression: equalityExpr,
                                Name: targetPathExpr,
                                SourceAttributes: srcAttrPayload
                                    ? [srcAttrPayload]
                                    : undefined,
                                TargetAttribute: tgtAttrPayload,
                            });
                            const createdWithAttrs: any = {
                                ...created,
                                SourceAttributes:
                                    (created as any)?.SourceAttributes ??
                                    (srcAttrPayload
                                        ? [srcAttrPayload]
                                        : undefined),
                                TargetAttribute:
                                    (created as any)?.TargetAttribute ??
                                    tgtAttrPayload,
                            };
                            await deleteTransformation(t.Id);
                            setTransformations((prev) => {
                                const filtered = prev.filter(
                                    (p) => p.Id !== t.Id
                                );
                                return [
                                    ...filtered,
                                    { ...(createdWithAttrs || {}) } as any,
                                ];
                            });
                            setGroup((prev) =>
                                prev
                                    ? {
                                          ...prev,
                                          Transformations: [
                                              ...prev.Transformations.filter(
                                                  (x) => x.Id !== t.Id
                                              ),
                                              createdWithAttrs as any,
                                          ],
                                      }
                                    : prev
                            );
                            results.push(createdWithAttrs as any);
                        }
                    } catch (err) {
                        console.error('Failed to reassign transformation', err);
                        results.push(null);
                    }
                }
            } else {
                if (
                    reassignHoverTargetId == null &&
                    reassignTransformations.length &&
                    !wireDetachDragging &&
                    !pendingDetach
                ) {
                    const ids = reassignTransformations.map((t) => t.Id);
                    setPendingDeleteIds(ids);
                    setDeleteDialogOpen(true);
                    setSelectedTransformationIds(new Set(ids));
                } else {
                    cleanupSelection();
                }
            }
            // Always exit reassign mode and clear dashed overlays
            setReassignActive(false);
            setReassignPaths([]);
            setReassignHoverTargetId(null);
            pendingReassignRef.current = null;
        };
        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp, { once: true });
        return () => {
            window.removeEventListener('mousemove', handleMove);
            window.removeEventListener('mouseup', handleUp);
        };
    }, [
        reassignActive,
        reassignTransformations,
        reassignHoverTargetId,
        selectedTargetAttrId,
    cleanupSelection,
    wireDetachDragging,
    pendingDetach,
    ]);

    // Safety: whenever reassign mode turns off, clear dashed overlays
    useEffect(() => {
        if (!reassignActive) {
            setReassignPaths([]);
            setReassignHoverTargetId(null);
        }
    }, [reassignActive]);

    // Threshold activation for reassign drag
    useEffect(() => {
        if (reassignActive) {
            pendingReassignRef.current = null;
            return;
        }
        const handleMove = (e: MouseEvent) => {
            if (!pendingReassignRef.current) return;
            if (!(e.buttons & 1)) {
                pendingReassignRef.current = null;
                return;
            }
            const { startX, startY, transforms } = pendingReassignRef.current;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (Math.sqrt(dx * dx + dy * dy) >= REASSIGN_DRAG_THRESHOLD) {
                setReassignActive(true);
                setReassignTransformations(transforms);
                pendingReassignRef.current = null;
            }
        };
        const handleUp = () => {
            pendingReassignRef.current = null;
        };
        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp, { once: true });
        return () => {
            window.removeEventListener('mousemove', handleMove);
            window.removeEventListener('mouseup', handleUp);
        };
    }, [reassignActive]);

    const registerAttrElement = useCallback(
        (
            side: 'left' | 'right',
            id: number,
            el: HTMLElement | null,
            entityPath?: string | null
        ) => {
            const map =
                side === 'left'
                    ? attrElementsLeft.current
                    : attrElementsRight.current;
            const idKey = String(id);
            const pathKey = entityPath ? `${entityPath}|${idKey}` : null;
            if (el) {
                if (pathKey) {
                    // Use only the path-scoped key to avoid collisions for reused attributes
                    map.set(pathKey, el);
                } else {
                    map.set(idKey, el);
                }
            } else {
                if (pathKey) {
                    map.delete(pathKey);
                } else {
                    map.delete(idKey);
                }
            }
        },
        []
    );

    // Build attribute name lookup maps for faster path name building
    const sourceAttrNameById = useMemo(() => {
        const map = new Map<number, string>();
        (sourceModel?.Entities || []).forEach((ewa) => {
            (ewa.Attributes || []).forEach((a) => {
                if (a?.Id != null) map.set(a.Id, a.Name);
            });
        });
        return map;
    }, [sourceModel]);
    const targetAttrNameById = useMemo(() => {
        const map = new Map<number, string>();
        (targetModel?.Entities || []).forEach((ewa) => {
            (ewa.Attributes || []).forEach((a) => {
                if (a?.Id != null) map.set(a.Id, a.Name);
            });
        });
        return map;
    }, [targetModel]);

    const pathNameBuilder = useCallback(
        (entityIdPath?: string | null, attributeId?: number | null, side?: 'source' | 'target') => {
            if (!attributeId) return null;
            const nameMap = side === 'target' ? targetAttrNameById : sourceAttrNameById;
            const attrName = nameMap.get(attributeId) || null;
            return buildDirectKeyExpression(entityIdPath, attrName);
        },
        [sourceAttrNameById, targetAttrNameById, buildDirectKeyExpression]
    );

    const { wirePaths: hookWirePaths } = useMappingWires({
        transformations: transformations as any,
        containerRef: containerRef as any,
        wiresSlotRef: wiresSlotRef as any,
        leftScrollRef: leftScrollRef as any,
        rightScrollRef: rightScrollRef as any,
        attrElementsLeft,
        attrElementsRight,
        recomputeDeps: [sourceModel, targetModel, sourceQuery, targetQuery],
        pathNameBuilder,
    });
    useEffect(() => setWirePaths(hookWirePaths), [hookWirePaths]);

    const formatShortDate = (iso?: string) => {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        const mm = d.getMonth() + 1;
        const dd = d.getDate();
        const yy = d.getFullYear().toString().slice(-2);
        return `${mm}-${dd}-${yy}`;
    };

    const onForkVersion = useCallback(async () => {
        if (!group) return;
        try {
            const forked = await forkTransformationGroup(group, forkBump);
            // Update local state to the new group
            setGroup(forked);
            setTransformations(
                (forked.Transformations || []).map((t) => ({
                    ...t,
                    SourceEntity: entityByIdRef.current.get(
                        (t as any).SourceAttributes?.[0]?.EntityId
                    ),
                    TargetEntity: entityByIdRef.current.get(
                        t.TargetAttribute?.EntityId
                    ),
                }))
            );
            // Update in-memory group list and version map without repulling
            setAllGroups((prev) => {
                const base = prev || [];
                const item = {
                    TransformationGroupId: forked.Id,
                    SourceDataModelId: forked.SourceDataModelId,
                    SourceDataModelName:
                        forked.SourceDataModelName ||
                        group.SourceDataModelName ||
                        '',
                    TargetDataModelId: forked.TargetDataModelId,
                    TargetDataModelName:
                        forked.TargetDataModelName ||
                        group.TargetDataModelName ||
                        '',
                } as TranformationGroupData;
                // avoid duplicates
                if (
                    base.some(
                        (g) =>
                            g.TransformationGroupId ===
                            item.TransformationGroupId
                    )
                )
                    return base;
                return [...base, item];
            });
            setVersionByGroupId((prev) => ({
                ...prev,
                [forked.Id]: forked.GroupVersion,
            }));
            // Navigate to new group's URL
            navigate(`/explore/data-mappings/${forked.Id}`);
        } catch (e) {
            console.error('Failed to fork transformation group', e);
        }
    }, [group, forkBump, navigate]);

    const samePairGroups = useMemo(() => {
        if (!group || !allGroups) return [] as TranformationGroupData[];
        const normalize = (id?: number) => (id && id > 0 ? id : 1);
        const currentSourceId = group.SourceDataModelId;
        const currentTargetId = normalize(group.TargetDataModelId as any);
        return allGroups.filter(
            (g) =>
                g.SourceDataModelId === currentSourceId &&
                normalize(g.TargetDataModelId as any) === currentTargetId
        );
    }, [group, allGroups]);

    const onEditDetails = useCallback(() => {
        if (!group) return;
        setEditGroupOpen(true);
    }, [group]);


    /** Add dynamic keyboard listener for trigger wire deletion */
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (selectedTransformationIds.size < 1) return;
            if (e.key === 'Delete' || e.key === 'Backspace') {
                e.preventDefault();
                const transIds = Array.from(selectedTransformationIds);
                if (selectedWireSourceAttrIds.size > 0 && selectedTransformationIds.size === 1) { // If specific source wires selected, detach
                    const transId = transIds[0];
                    const srcAttrIds = Array.from(selectedWireSourceAttrIds);
                    const transformation = transformations.find(t => t.Id === transId);
                    if (transformation) {
                        const originalList: any[] = Array.isArray((transformation as any).SourceAttributes) 
                            ? [...(transformation as any).SourceAttributes] : [];
                        const remaining = originalList.filter(s => !srcAttrIds.includes(s.AttributeId));
                        const willDelete = remaining.length === 0;
                        setPendingDetach({ transId, srcAttrIds, willDelete });
                        setDetachDialogOpen(true);
                        return;
                    }
                } // Otherwise delete entire transformations
                setPendingDeleteIds(transIds);
                setDeleteDialogOpen(true);
            }
        };
        if (selectedTransformationIds.size < 1) return; // Only add listener when wires are selected
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedTransformationIds, selectedWireSourceAttrIds, transformations]);


    return (
        <div
            className="page-content mappings-view"
            ref={containerRef}
            onMouseDownCapture={(e) => {
                // Start detach only if mousedown originated on a dot element and a single wire is selected
                if (wireDetachDragging || isDragging || reassignActive) return; // don't overlap drags
                const target = e.target as HTMLElement | null;
                if (!target) return;
                if (!target.classList.contains('mappings-column__dot')) return; // only dots
                if (selectedTransformationIds.size !== 1 || selectedWireSourceAttrIds.size === 0) return; // need at least one selected source wire
                // Ascend to attr container for metadata
                let node: HTMLElement | null = target;
                let attrId: number | null = null;
                let isLeft = false;
                while (node) {
                    if (node.classList?.contains('mappings-attr')) {
                        attrId = node.dataset.attrId ? Number(node.dataset.attrId) : null;
                        isLeft = node.classList.contains('mappings-attr--left');
                        break;
                    }
                    node = node.parentElement;
                }
                if (!attrId) return;
                const transId = Array.from(selectedTransformationIds)[0];
                const transformation = transformations.find(t => t.Id === transId);
                if (!transformation) return;
                // Must match selected source wire: if left, attrId must equal selected source; if right, transformation must include selected source
                let selectedSrcIds = Array.from(selectedWireSourceAttrIds);
                const hasAnySelected = (transformation as any).SourceAttributes?.some((s: any) => selectedSrcIds.includes(s.AttributeId));
                if (isLeft) {
                    if (!selectedSrcIds.includes(attrId)) return; // only allow starting from a selected source dot
                    // If user clicked a single source dot, constrain preview to that one even if multiple were temporarily selected
                    selectedSrcIds = [attrId];
                } else {
                    if (!hasAnySelected) return; // target side but transformation lacks selected sources
                }
                // Initiate multi-wire detach drag
                e.preventDefault();
                setWireDetachDragging({ transId, srcAttrIds: selectedSrcIds });
                setWireDetachPaths([]);
            }}
            onClick={(e) => {
                const target = e.target as HTMLElement | null;
                if (!target) return;
                // Ignore clicks on wires (handled separately)
                if ((target as any).tagName?.toLowerCase() === 'path') return;
                // Ignore clicks inside interactive areas
                if (
                    target.closest(
                        '.mappings-attr, .mappings-entity, .mappings-group-header, .mappings-source-select, .mappings-column__search-wrap, .mappings-select-item-row, [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper]'
                    )
                )
                    return;
                // Clear selection on background click
                setSelectedTransformationIds(new Set());
                setSelectionAll(false);
                setSelectedTargetAttrId(null);
                setSelectionIndex(0);
                setReassignActive(false);
                pendingReassignRef.current = null;
                setSelectedWireSourceAttrIds(new Set());
            }}
            onWheel={(e) => {
                if (anyDialogOpen) return; // disable background scroll while modal open
                const delta = e.deltaY;
                const bounds = containerRef.current?.getBoundingClientRect();
                if (!bounds) return;
                const leftRect = leftScrollRef.current?.getBoundingClientRect();
                const rightRect =
                    rightScrollRef.current?.getBoundingClientRect();
                if (leftRect && rightRect) {
                    const distLeft = Math.abs(
                        e.clientX - (leftRect.left + leftRect.width)
                    );
                    const distRight = Math.abs(e.clientX - rightRect.left);
                    const target =
                        distLeft <= distRight
                            ? leftScrollRef.current
                            : rightScrollRef.current;
                    target?.scrollBy({ top: delta });
                }
            }}
        >
            {error && <div className="error-message">{error}</div>}
            <div className="mappings-grid">
                <div className="mappings-cap-left">
                    <ColumnHeader
                        side="left"
                        title={sourceModel?.DataModel?.Name || 'Source'}
                        scrollRef={leftScrollRef}
                        searchItems={sourceSearchItems}
                        query={sourceQuery}
                        onQueryChange={setSourceQuery}
                        headerNameNode={(() => {
                            const selected = allModels.find(
                                (m) => m.Id === selectedSourceId
                            );
                            const selectedCount = selected
                                ? countGroupsForSource(selected.Id)
                                : 0;
                            return (
                                <RdxSelect.Root
                                    value={
                                        selectedSourceId != null
                                            ? String(selectedSourceId)
                                            : undefined
                                    }
                                    onValueChange={(v) =>
                                        onChangeSourceModel(Number(v))
                                    }
                                >
                                    <RdxSelect.Trigger
                                        className="mappings-source-select"
                                        title="Select source data model"
                                    >
                                        <span>
                                            {selected?.Name || 'Select source'}
                                        </span>
                                        {selectedCount > 0 && (
                                            <Badge
                                                variant="soft"
                                                color="gray"
                                                className="mappings-source-trigger-count"
                                            >
                                                {selectedCount}
                                            </Badge>
                                        )}
                                    </RdxSelect.Trigger>
                                    <RdxSelect.Content>
                                        {allModels.map((m) => {
                                            const count = countGroupsForSource(
                                                m.Id
                                            );
                                            return (
                                                <RdxSelect.Item
                                                    key={m.Id}
                                                    value={String(m.Id)}
                                                >
                                                    <div className="mappings-select-item-row">
                                                        <span>{m.Name}</span>
                                                        {count > 0 && (
                                                            <Badge
                                                                variant="soft"
                                                                color="gray"
                                                            >
                                                                {count}
                                                            </Badge>
                                                        )}
                                                    </div>
                                                </RdxSelect.Item>
                                            );
                                        })}
                                    </RdxSelect.Content>
                                </RdxSelect.Root>
                            );
                        })()}
                    />
                </div>
                {group && groupId >= 0 ? (
                    <div
                        className="mappings-group-header"
                        role="region"
                        aria-label="Mapping group"
                    >
                        {/* Row 1: Name + edit action */}
                        <div className="mappings-group-header__row1">
                            <div
                                className="mappings-group-header__name"
                                title={group.Name || ''}
                            >
                                {(() => {
                                    const name = (group.Name || '').trim();
                                    if (name) return name;
                                    const src = group.SourceDataModelName || '';
                                    const tgt = group.TargetDataModelName || '';
                                    const combined = `${src}_${tgt}`.trim();
                                    return combined || 'Untitled Mapping Group';
                                })()}
                            </div>
                            <div className="mappings-group-header__actions">
                                <button
                                    type="button"
                                    className="mappings-icon-btn"
                                    title="Edit details"
                                    onClick={onEditDetails}
                                >
                                    ✎
                                </button>
                                <button
                                    type="button"
                                    className="mappings-icon-btn mappings-icon-btn--bulk"
                                    title="Bulk edit transformations"
                                    onClick={() => setBulkDialogOpen(true)}
                                >
                                    ⇱
                                </button>
                            </div>
                        </div>

                        {/* Row 2: Source → Target + version */}
                        <div className="mappings-group-header__row2">
                            <span className="mappings-group-header__source">
                                {group.SourceDataModelName ||
                                    sourceModel?.DataModel?.Name ||
                                    'Source'}
                            </span>
                            <span
                                className="mappings-group-header__arrow"
                                aria-hidden
                            >
                                →
                            </span>
                            <span className="mappings-group-header__target">
                                {group.TargetDataModelName ||
                                    targetModel?.DataModel?.Name ||
                                    'Target'}
                            </span>
                            {samePairGroups.length <= 1 ? (
                                <span className="mappings-badge">
                                    v{group.GroupVersion}
                                </span>
                            ) : (
                                <select
                                    className="mappings-version-select"
                                    value={group.Id}
                                    onChange={(e) => {
                                        const nextId = Number(e.target.value);
                                        if (
                                            !Number.isNaN(nextId) &&
                                            nextId !== group.Id
                                        ) {
                                            navigate(
                                                `/explore/data-mappings/${nextId}`
                                            );
                                        }
                                    }}
                                    title="Select version"
                                >
                                    {samePairGroups
                                        .slice()
                                        .sort((a, b) => {
                                            const va =
                                                versionByGroupId[
                                                    a.TransformationGroupId
                                                ] || '0.0';
                                            const vb =
                                                versionByGroupId[
                                                    b.TransformationGroupId
                                                ] || '0.0';
                                            const [amj, ami] = va
                                                .split('.')
                                                .map(
                                                    (n) => parseInt(n, 10) || 0
                                                );
                                            const [bmj, bmi] = vb
                                                .split('.')
                                                .map(
                                                    (n) => parseInt(n, 10) || 0
                                                );
                                            return bmj - amj || bmi - ami;
                                        })
                                        .map((g) => (
                                            <option
                                                key={g.TransformationGroupId}
                                                value={g.TransformationGroupId}
                                            >
                                                v
                                                {versionByGroupId[
                                                    g.TransformationGroupId
                                                ] || '?'}
                                            </option>
                                        ))}
                                </select>
                            )}
                            <button
                                type="button"
                                className="mappings-fork-btn"
                                title="Fork to new version"
                                onClick={() => setForkDialogOpen(true)}
                            >
                                ⎘ Fork
                            </button>
                        </div>

                        {/* Row 3: Status badges */}
                        <div className="mappings-group-header__row3">
                            {(() => {
                                const now = new Date();
                                const parse = (s?: string) => {
                                    if (!s) return undefined;
                                    const d = new Date(s);
                                    return isNaN(d.getTime()) ? undefined : d;
                                };
                                const act = parse(group.ActivationDate);
                                const dep = parse(group.DeprecationDate);
                                const MS_PER_DAY = 24 * 60 * 60 * 1000;
                                const isAfterOrEqual = (a: Date, b: Date) =>
                                    a.getTime() >= b.getTime();
                                const isBefore = (a: Date, b: Date) =>
                                    a.getTime() < b.getTime();
                                const inNext7Days = (d?: Date) =>
                                    !!d &&
                                    d.getTime() - now.getTime() <=
                                        7 * MS_PER_DAY &&
                                    d.getTime() > now.getTime();
                                const isActivated =
                                    !!act && isAfterOrEqual(now, act);
                                const activatesSoon =
                                    inNext7Days(act) && isBefore(now, act!);
                                const isDeprecated =
                                    !!dep && isAfterOrEqual(now, dep);
                                const deprecatesSoon =
                                    isActivated && inNext7Days(dep);

                                const badges: Array<{
                                    label: string;
                                    kind:
                                        | 'active'
                                        | 'soon'
                                        | 'deprecated'
                                        | 'inactive';
                                }> = [];
                                if (isDeprecated) {
                                    badges.push({
                                        label: 'Deprecated',
                                        kind: 'deprecated',
                                    });
                                } else if (isActivated) {
                                    badges.push({
                                        label: 'Active',
                                        kind: 'active',
                                    });
                                    if (deprecatesSoon)
                                        badges.push({
                                            label: 'Deprecates Soon',
                                            kind: 'soon',
                                        });
                                } else if (activatesSoon) {
                                    badges.push({
                                        label: 'Activates Soon',
                                        kind: 'soon',
                                    });
                                } else {
                                    badges.push({
                                        label: 'Inactive',
                                        kind: 'inactive',
                                    });
                                }
                                return badges.map((b, i) => (
                                    <span
                                        key={`${b.label}-${i}`}
                                        className={`status-badge status-badge--${b.kind}`}
                                    >
                                        {b.label}
                                    </span>
                                ));
                            })()}
                        </div>
                    </div>
                ) : (
                    <div
                        className="mappings-group-header"
                        role="region"
                        aria-label="No mapping selected"
                    >
                        <div className="mappings-group-header__row2">
                            <span className="mappings-group-header__source">
                                {allModels.find(
                                    (m) =>
                                        m.Id ===
                                        (selectedSourceId ?? allModels[0]?.Id)
                                )?.Name ||
                                    sourceModel?.DataModel?.Name ||
                                    'Source'}
                            </span>
                            <span
                                className="mappings-group-header__arrow"
                                aria-hidden
                            >
                                →
                            </span>
                            <span className="mappings-group-header__target">
                                {targetModel?.DataModel?.Name || 'Target'}
                            </span>
                            <button
                                type="button"
                                className="mappings-fork-btn"
                                title="Create new mapping"
                                onClick={handleCreateNewMapping}
                            >
                                + Create
                            </button>
                        </div>
                    </div>
                )}
                <div className="mappings-cap-right">
                    <ColumnHeader
                        side="right"
                        title={targetModel?.DataModel?.Name || 'Target'}
                        scrollRef={rightScrollRef}
                        searchItems={targetSearchItems}
                        query={targetQuery}
                        onQueryChange={setTargetQuery}
                        headerNameNode={(() => {
                            const selected = orgLifModels.find(
                                (m) => m.Id === selectedTargetId
                            );
                            if (!orgLifModels.length) return 'Target';
                            if (orgLifModels.length === 1)
                                return selected?.Name || orgLifModels[0].Name;
                            return (
                                <RdxSelect.Root
                                    value={
                                        selectedTargetId != null
                                            ? String(selectedTargetId)
                                            : undefined
                                    }
                                    onValueChange={(v) =>
                                        onChangeTargetModel(Number(v))
                                    }
                                >
                                    <RdxSelect.Trigger
                                        className="mappings-source-select"
                                        title="Select target OrgLIF model"
                                    >
                                        <span>
                                            {selected?.Name || 'Select target'}
                                        </span>
                                    </RdxSelect.Trigger>
                                    <RdxSelect.Content>
                                        {orgLifModels.map((m) => (
                                            <RdxSelect.Item
                                                key={m.Id}
                                                value={String(m.Id)}
                                            >
                                                <div className="mappings-select-item-row">
                                                    <span>{m.Name}</span>
                                                </div>
                                            </RdxSelect.Item>
                                        ))}
                                    </RdxSelect.Content>
                                </RdxSelect.Root>
                            );
                        })()}
                    />
                </div>
                <div className="mappings-body-left">
                    <BodyModelColumn
                        title={sourceModel?.DataModel?.Name || 'Source'}
                        model={sourceModel}
                        modelWithTree={sourceModel}
                        query={sourceQuery}
                        onQueryChange={setSourceQuery}
                        searchItems={sourceSearchItems}
                        mappedAttrIds={
                            new Set<number>(
                                transformations
                                    .map((t) => (t as any).SourceAttributes?.[0]?.AttributeId)
                                    .filter(
                                        (id): id is number =>
                                            typeof id === 'number'
                                    )
                            )
                        }
                        side="left"
                        scrollRef={leftScrollRef}
                        registerAttrElement={registerAttrElement}
                        onHoverAttr={setHoveredAttrKey}
                        dragTargetAttrId={groupId < 0 ? null : dragTargetAttrId}
                        dragTargetPath={groupId < 0 ? null : dragTargetPath}
                        onStartDrag={(attr, entityPath) => {
                            if (groupId < 0) return; // disable drag when no group
                            setDragSourceAttr(attr);
                            setDragSourcePath(entityPath || null);
                            setIsDragging(true);
                        }}
                        onSourceDotDoubleClick={handleSourceDotDoubleClick}
                        transformations={transformations}
                        loading={sourceLoading}
                        disableInteractions={groupId < 0}
                        selectionContext={{
                            selectedTargetAttrId, setSelectedTargetAttrId,
                            selectionIndex, setSelectionIndex,
                            selectionAll, setSelectionAll,
                            selectedTransformationIds, setSelectedTransformationIds,
                            setSelectedWireSourceAttrIds,
                            setReassignActive,
                            setReassignTransformations:
                                setReassignTransformations as any,
                            reassignHoverTargetId,
                            prepareReassign: (
                                e: React.MouseEvent,
                                transforms: any[]
                            ) => {
                                pendingReassignRef.current = {
                                    startX: e.clientX,
                                    startY: e.clientY,
                                    transforms: transforms as any,
                                };
                            },
                        }}
                        bodyOnly
                    />
                </div>
                <div className="mappings-body-right">
                    <BodyModelColumn
                        title={targetModel?.DataModel?.Name || 'Target'}
                        model={targetModel}
                        modelWithTree={targetModel}
                        query={targetQuery}
                        onQueryChange={setTargetQuery}
                        searchItems={targetSearchItems}
                        mappedAttrIds={
                            new Set<number>(
                                transformations
                                    .map((t) => t.TargetAttribute?.AttributeId)
                                    .filter(
                                        (id): id is number =>
                                            typeof id === 'number'
                                    )
                            )
                        }
                        side="right"
                        scrollRef={rightScrollRef}
                        registerAttrElement={registerAttrElement}
                        onHoverAttr={setHoveredAttrKey}
                        dragTargetAttrId={groupId < 0 ? null : dragTargetAttrId}
                        dragTargetPath={groupId < 0 ? null : dragTargetPath}
                        transformations={transformations}
                        loading={targetLoading}
                        disableInteractions={groupId < 0}
                        selectionContext={{
                            selectedTargetAttrId, setSelectedTargetAttrId,
                            selectionIndex, setSelectionIndex,
                            selectionAll, setSelectionAll,
                            selectedTransformationIds, setSelectedTransformationIds,
                            setSelectedWireSourceAttrIds,
                            setReassignActive,
                            setReassignTransformations:
                                setReassignTransformations as any,
                            reassignHoverTargetId,
                            prepareReassign: (
                                e: React.MouseEvent,
                                transforms: any[]
                            ) => {
                                pendingReassignRef.current = {
                                    startX: e.clientX,
                                    startY: e.clientY,
                                    transforms: transforms as any,
                                };
                            },
                        }}
                        bodyOnly
                    />
                </div>
                <div
                    className="mappings-wires-slot"
                    ref={wiresSlotRef}
                    onClick={() => {
                        // Deselect when clicking empty space within the wires area
                        setSelectedTransformationIds(new Set());
                        setSelectionAll(false);
                        setSelectedTargetAttrId(null);
                        setSelectionIndex(0);
                        setReassignActive(false);
                        pendingReassignRef.current = null;
                        setSelectedWireSourceAttrIds(new Set());
                    }}
                >
                    <Wires
                        wirePaths={wirePaths as any}
                        hoveredAttrKey={hoveredAttrKey}
                        selectedTransformationIds={selectedTransformationIds}
                        selectedWireSourceAttrIds={selectedWireSourceAttrIds}
                        dragPath={dragPath || undefined}
                        reassignPaths={reassignPaths}
                        detachPaths={wireDetachPaths}
                        onEmptyClick={() => {
                            setSelectedTransformationIds(new Set());
                            setSelectionAll(false);
                            setSelectedTargetAttrId(null);
                            setSelectionIndex(0);
                            setReassignActive(false);
                            pendingReassignRef.current = null;
                            setSelectedWireSourceAttrIds(new Set());
                        }}
                        onWireClick={(transId, srcAttrId, e) => {
                            e.stopPropagation();
                            const t = transformations.find((x) => x.Id === transId);
                            if (!t) return;
                            const tgtAttrId = t.TargetAttribute?.AttributeId ?? null;

                            // Shift+click on any wire = select all wires (sources) for this transformation
                            if (e.shiftKey) {
                                const allSrcIds = new Set<number>(
                                    ((t as any).SourceAttributes || []).map((s: any) => s.AttributeId)
                                );
                                setSelectedWireSourceAttrIds(allSrcIds);
                                setSelectedTransformationIds(new Set([transId]));
                                setSelectedTargetAttrId(tgtAttrId);
                                setSelectionAll(false);
                                if (tgtAttrId) {
                                    const inbound = transformations.filter((x) => x.TargetAttribute?.AttributeId === tgtAttrId);
                                    const idx = inbound.findIndex((x) => x.Id === t.Id);
                                    if (idx >= 0) setSelectionIndex(idx); else setSelectionIndex(0);
                                } else setSelectionIndex(0);
                                setReassignActive(false);
                                pendingReassignRef.current = null;
                                return;
                            }

                            // Ctrl/meta click: toggle within same transformation; if different transformation or different target, reset to just this wire
                            if (e.ctrlKey || e.metaKey) {
                                const currentTransId = Array.from(selectedTransformationIds)[0];
                                const sameTransformation = selectedTransformationIds.size === 1 && currentTransId === transId;
                                // Enforce single target scope: if previous selection had a different target attribute, reset
                                const prevTgtAttrId = selectedTargetAttrId;
                                const differentTarget = prevTgtAttrId != null && tgtAttrId != null && prevTgtAttrId !== tgtAttrId;
                                if (!sameTransformation || differentTarget) {
                                    setSelectedTransformationIds(new Set([transId]));
                                    setSelectedTargetAttrId(tgtAttrId);
                                    setSelectedWireSourceAttrIds(new Set([srcAttrId]));
                                } else {
                                    setSelectedWireSourceAttrIds((prev) => {
                                        const next = new Set(prev);
                                        if (next.has(srcAttrId)) next.delete(srcAttrId); else next.add(srcAttrId);
                                        return next;
                                    });
                                }
                                setSelectionAll(false);
                                if (tgtAttrId) {
                                    const inbound = transformations.filter((x) => x.TargetAttribute?.AttributeId === tgtAttrId);
                                    const idx = inbound.findIndex((x) => x.Id === t.Id);
                                    if (idx >= 0) setSelectionIndex(idx); else setSelectionIndex(0);
                                } else setSelectionIndex(0);
                                setReassignActive(false);
                                pendingReassignRef.current = null;
                                return;
                            }

                            // Plain click: single wire selection (reset)
                            setSelectedWireSourceAttrIds(new Set([srcAttrId]));
                            setSelectedTransformationIds(new Set([transId]));
                            setSelectedTargetAttrId(tgtAttrId);
                            setSelectionAll(false);
                            if (tgtAttrId) {
                                const inbound = transformations.filter((x) => x.TargetAttribute?.AttributeId === tgtAttrId);
                                const idx = inbound.findIndex((x) => x.Id === t.Id);
                                if (idx >= 0) setSelectionIndex(idx); else setSelectionIndex(0);
                            } else setSelectionIndex(0);
                            setReassignActive(false);
                            pendingReassignRef.current = null;
                        }}
                        onWireDoubleClick={(transId, _srcAttrId) => handleWireDoubleClick(transId)}
                    />
                </div>
            </div>
            {/* Extracted dialogs */}
            <DeleteTransformationsDialog
                open={deleteDialogOpen}
                count={pendingDeleteIds.length}
                busy={deleting}
                onCancel={cancelDelete}
                onConfirm={confirmDelete}
                onOpenChange={setDeleteDialogOpen}
            />
            <ExpressionEditorDialog
                open={exprDialogOpen}
                transformation={editingTransformation}
                onOpenChange={(o) => {
                    if (!o) handleExpressionCancel();
                    else setExprDialogOpen(o);
                }}
                onSave={handleExpressionSave}
                onCancel={handleExpressionCancel}
                sourceModel={sourceModel}
                targetPath={editingTargetPath}
                targetJsonSchema={targetJsonSchema}
            />
            <EditGroupDialog
                open={editGroupOpen}
                group={group}
                onOpenChange={setEditGroupOpen}
                onCancel={() => setEditGroupOpen(false)}
                onSave={async (updates) => {
                    if (!group) return;
                    try {
                        const updated = await updateTransformationGroup(group.Id, updates);
                        setGroup((prev) => (prev ? { ...prev, ...(updated || {}), ...updates } : prev));
                    } finally {
                        setEditGroupOpen(false);
                    }
                }}
            />
            <ForkGroupDialog
                open={forkDialogOpen}
                forkBump={forkBump}
                preview={forkPreview}
                currentVersion={group?.GroupVersion}
                onOpenChange={setForkDialogOpen}
                onChangeBump={(b) => setForkBump(b)}
                onCancel={() => setForkDialogOpen(false)}
                onFork={async () => {
                    setForkDialogOpen(false);
                    await onForkVersion();
                }}
            />
            <DetachSourcesDialog
                open={detachDialogOpen}
                count={pendingDetach?.srcAttrIds.length || 0}
                willDeleteTransformation={pendingDetach?.willDelete || false}
                busy={detaching}
                onCancel={() => { if (!detaching) { setDetachDialogOpen(false); setPendingDetach(null); setWireDetachDragging(null); setWireDetachPaths([]); } }}
                onConfirm={() => { if (!detaching) confirmDetachSources(); }}
                onOpenChange={(o) => { if (!o) { setDetachDialogOpen(false); setPendingDetach(null); } else setDetachDialogOpen(o); }}
            />
            <BulkTransformationsDialog
                open={bulkDialogOpen}
                group={group}
                transformations={transformations}
                onOpenChange={setBulkDialogOpen}
                onClose={() => setBulkDialogOpen(false)}
                sourceSchema={sourceJsonSchema}
                targetSchema={targetJsonSchema}
                onSaved={() => { // refresh group + transformations after bulk deletes
                    fetchTransformations();
                }}
            />
        </div>
    );
};

// Inline ModelColumn removed; now using BodyModelColumn and ColumnHeader components

export default MappingsView;
