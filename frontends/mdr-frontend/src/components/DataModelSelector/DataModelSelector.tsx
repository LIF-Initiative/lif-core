import { Box, Dialog } from "@radix-ui/themes";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorToString } from "../../utils/errorUtils";
import { CrudDialog } from "../Dialog/Dialog";
import ModelTree from "../ModelExplorer/ModelExplorer";
import { DataModelCreateFields, DataModelEditFields } from "./CreateFields";
import { SimpleTree, transformData } from "./SimpleTree";

const FileDEBUG = false;
const debugLog = (...args: any[]) => { if (FileDEBUG) console.log(...args); };
const reportError = (...args: any[]) => { console.error(...args); };


import {
  // getModelDetails,
  createDataModel,
  createDataModelFromUpload,
  listModels,
  updateDataModel,
  updateDataModelFromUpload,
} from "../../services/modelService";

interface ExplorePageLayoutProps {
  dataModeltype: string;
  routPath: string;
}

const DataModelSelector: React.FC<ExplorePageLayoutProps> = ({
  dataModeltype,
  routPath,
}) => {
  const navigate = useNavigate();

  const { modelId } = useParams();
  const [models, setModels] = useState<any[]>([]);
  const [selectedModel, setSelectedModel] = useState<any>(null);
  const [modelPath, setModelPath] = useState<any>(routPath);
  // const [modelDetails, setModelDetails] = useState<any>(null);

  const dataModelSelected = async (id: number, extraPath?: string, nav?: boolean) => {
    const path = `${routPath}${id}${extraPath}`;
    const model = models.find((m) => m.Id === id);
    if (!model) {
      console.warn("Model not found for ID:", id);
      return;
    }
    model.urlParam = extraPath;
    setModelPath(path);
    setSelectedModel(model);
    if (nav) { navigate(path); }
  };

  const fetchModels = useCallback(async () => {
    try {
      const allModels = await listModels();
      setModels(allModels);
      if (modelId) {
        const model = allModels.find((m) => m.Id === parseInt(modelId));
        setSelectedModel(model);
      }
    } catch (error) {
      reportError("Error fetching models:", errorToString(error));
    }
  }, [dataModeltype, modelId]);

  const handleLabelClick = (n: any) => {
    if (!n || n.noClick || (!Number(n.id) && !Number(n?.parentId))) {
      debugLog("Ignored node: ", n);
      return;
    }
    let modelId = Number(n?.id) ? n.id : n.parentId;
    let extraPath = ``;
    if (n.type == "OrgLIF") {
      if (n.id === "only") extraPath += "/only";
      else if (n.id === "all") extraPath += "/all";
      else if (n.id === "pub") extraPath += "/public";
      else if (n.id === "ext") extraPath += "/extensions";
      else if (n.id === "part") extraPath += "/partner";
      else extraPath += `/only`; // default to organization only view
    }
    debugLog("handleLabelClick:", n, extraPath);
    dataModelSelected(modelId, extraPath, true);
  };

  const handleCreateModel = async (params: any) => {
    try {
      if (params.Type === "PartnerLIF") {
        params.BaseDataModelId = params.BaseDataModelId ?? 1;
      }
      if (params.File) {
        await createDataModelFromUpload(params);
      } else {
        await createDataModel(params);
      }
      await fetchModels();
    } catch (error) {
      reportError("Error creating model:", errorToString(error));
      throw error;
    }
  };

  const handleEditModel = async (id: number, params: any) => {
    debugLog("handleEditModel:", id, params);
    try {
      delete params.Type; // Type is not editable
      if (params.File) {
        await updateDataModelFromUpload(id, params);
      } else {
        await updateDataModel(id, params);
      }
      await fetchModels();
    } catch (error) {
      reportError("Error updating model:", errorToString(error));
      throw error;
    }
  };

  const handleOnModelEdit = async (id: number, params: any) => {
    const newEditDialog = {
      isEditMode: true,
      title: "Data Model",
      itemToEdit: params,
      fields: DataModelEditFields(params.Type),
      onEdit: handleEditModel,
    };
    debugLog("handleOnModelEdit:", id, newEditDialog);
    setCrudDialog(newEditDialog);
    setIsCreateDialogOpen(true);
  };


  // const handleDeleteModel = async (id: number) => {
  //   try {
  //     await deleteDataModel(id);
  //     await fetchModels();
  //     if (selectedModel?.Id === id) {
  //       setSelectedModel(null);
  //       navigate(routPath);
  //     }
  //   } catch (error) {
  //     reportError("Error deleting model:", errorToString(error));
  //     throw error;
  //   }
  // };


  useEffect(() => {
    if (!modelId && models.length > 0 && dataModeltype !== "BaseLIF") {
      setSelectedModel(null);
      navigate(routPath);
    }
    fetchModels();
  }, [modelId, fetchModels, models.length, dataModeltype, navigate, routPath]);

  useEffect(() => {
    if (models.length > 0 && dataModeltype === "BaseLIF") {
      navigate(`${routPath}${models[0].Id}`);
    }
  }, [models, dataModeltype, navigate, routPath]);


  /** CRUD Dialog functionality */
  const [crudDialog, setCrudDialog] = useState<any>({
    title: '',
    fields: [],
    onCreate: undefined,
    isEditMode: false,
    itemToEdit: null,
    onEdit: undefined
  });
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const handleDialogOpenChange = (open: boolean) => {
    setIsCreateDialogOpen(open);
    if (!open) {
      setCrudDialog({
        title: '',
        fields: [],
        onCreate: undefined,
        isEditMode: false,
        itemToEdit: null,
        onEdit: undefined
      });
    }
  };
  const handleOnAddNew = async () => {
    const baseModel = models.find((m) => m.Type === "BaseLIF");
    let newCrudDialog: any = {
      isEditMode: false,
      title: "Data Model",
      fields: DataModelCreateFields,
      onCreate: handleCreateModel,
    };
    debugLog("handleOnAddNew:", baseModel.Id, newCrudDialog);
    setCrudDialog(newCrudDialog);
    setIsCreateDialogOpen(true);
  };


  const treeData: any = useMemo(() => {
    return models ? transformData(models) : {};
  }, [models]);

  return (
    <Box style={{ height: "100%", width: "100%", }}>
      <Box style={{
        height: "100%", width: "100%",
        display: "grid", gap: "1em",
        gridTemplateColumns: "repeat(3, minmax(400px, 1fr))",
      }}
      >
        <Box className="col-layout column-list">
          <Dialog.Root>
            <SimpleTree
              searchFilter
              headerStr={`Data Model Selector`}
              onAddNew={handleOnAddNew}
              data={treeData}
              initiallyExpandedIds={[17, "iP2"]}
              typeHandlers={{
                BaseLIF: (node: any) => handleLabelClick(node),
                OrgLIF: (node: any) => handleLabelClick(node),
                SourceSchema: (node: any) => handleLabelClick(node),
                PartnerLIF: (node: any) => handleLabelClick(node),
              }}
            />
          </Dialog.Root>

          <CrudDialog
            isOpen={isCreateDialogOpen}
            onOpenChange={handleDialogOpenChange}
            title={crudDialog.title}
            fields={crudDialog.fields}
            onCreate={crudDialog.onCreate}
            isEditMode={!!crudDialog.isEditMode}
            itemToEdit={crudDialog.itemToEdit}
            onEdit={crudDialog.onEdit}
          />
        </Box>
        {selectedModel && (
          <>
            <ModelTree
              key={`${selectedModel.Id}-${selectedModel.updatedAt}-${modelPath}`}
              crud={true}
              model={selectedModel}
              onEditModel={handleOnModelEdit}
              routPath={modelPath}
              ContribUser={"MDRUser"}
              ContribOrg={selectedModel.ContributorOrganization}
            />
          </>
        )}
      </Box>
    </Box>
  );
};

export default DataModelSelector;
