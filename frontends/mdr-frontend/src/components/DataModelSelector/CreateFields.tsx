const BaseLIF = 'BaseLIF';
const OrgLIF = 'OrgLIF';
const SourceSchema = 'SourceSchema';
const PartnerLIF = 'PartnerLIF';
const Model_Types: string[] = [BaseLIF, OrgLIF, SourceSchema, PartnerLIF];

const Model_States: string[] = ['Draft', 'Work_In_Progress', 'Published', 'Active', 'Inactive'];

const dataModelFields = (
  modelType?: string,
  isEditMode: boolean = false,
  typeOptions: string[] = Model_Types,
) => {
  const invalidType = !modelType || !Model_Types.includes(modelType);
  if (invalidType && modelType) { console.warn(`Invalid model.Type "${modelType}" is not in Model_Types:`, Model_Types); }
  const useTypeSelect = !isEditMode || invalidType;
  return [
    { name: "Name", type: "text" as const, label: "Name", required: true, },
    {
      name: "Type", label: "Type", required: true,
      ...(useTypeSelect
        ? {
          type: "select" as const,
          placeholder: "Select a Model Type",
          options: typeOptions.map((m: string) => ({ label: m, value: m })),
          ...(modelType && !invalidType ? { defaultValue: modelType } : {})
        }
        : {
          type: "text" as const,
          defaultValue: modelType,
          readOnly: true,
        }
      )
    },
    {
      name: "BaseDataModelId",
      label: "Base Data Model ID",
      type: "number" as const,
      placeholder: "Enter the Base Data Model ID",
      inputMode: "numeric",
      pattern: "[0-9]*",
      defaultValue: modelType === PartnerLIF ? "1" : undefined,
      readOnly: isEditMode,
      hidden: (params: any, context?: { isEditMode: boolean }) => {
        if (context?.isEditMode) return false; // always show in edit mode
        return params?.Type === SourceSchema || params?.Type === BaseLIF;
      },
    },
    { name: "Description", type: "text" as const, label: "Description", },
    { name: "Notes", type: "text" as const, label: "Notes", },
    { name: "UseConsiderations", type: "text" as const, label: "Use Considerations", },
    { name: "Tags", type: "text" as const, label: "Tags", },
    { name: "DataModelVersion", type: "text" as const, label: "Version", defaultValue: "1.0", },
    {
      name: "State", label: "State", type: "select" as const, defaultValue: "Draft",
      options: Model_States.map((m: string) => ({ label: m, value: m, })),
    },
    { name: "Contributor", type: "text" as const, label: "Contributor", },
    { name: "ContributorOrganization", type: "text" as const, label: "Contributor Organization", },
    { name: "CreationDate", type: "datetime-local" as const, label: "Creation Date", defaultValue: new Date().toISOString().slice(0, 16), hidden: true, },
    { name: "ActivationDate", type: "datetime-local" as const, label: "Activation Date", defaultValue: new Date().toISOString().slice(0, 16), },
    { name: "DeprecationDate", type: "datetime-local" as const, label: "Deprecation Date", },
    { name: "File", type: "file" as const, label: "Upload MDR Full OpenAPI Schema File", accept: ".json" }
  ];
};


export const DataModelCreateFields = dataModelFields(undefined, false, [SourceSchema, PartnerLIF]);

export const DataModelEditFields = (modelType: string) => dataModelFields(modelType, true);
