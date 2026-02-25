import { DialogField } from "../Dialog/Dialog";

const capitalize = (s: string): string => { return s?.length ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }

/** Dev Note: Once we get actual user data we should use that for Contributor and ContributorOrganization */

export const entityCreateFields = (model: any): DialogField[] => {
  return [
    {
      name: "DataModelId",
      type: "number" as const,
      label: "DataModelId",
      hidden: true,
      defaultValue: model?.Id,
    },
    {
      name: "Name",
      type: "text" as const,
      label: "Name",
      required: true,
      pattern: "^[A-Za-z][A-Za-z0-9_]*$",
      patternErr: "Name must start with a letter and contain only letters, numbers, and underscores.",
    },
    {
      name: "UniqueName",
      type: "text" as const,
      label: "Unique Name",
      required: true,
      pattern: "^[A-Za-z][A-Za-z0-9_]*$",
      patternErr: "Unique Name must start with a letter and contain only letters, numbers, and underscores.",
    },
    { name: "Description", type: "text" as const, label: "Description" },
    {
      name: "Use Considerations",
      type: "text" as const,
      label: "Use Considerations",
    },
    {
      name: "Required",
      type: "select" as const,
      label: "Required",
      options: [
        { label: "Yes", value: "Yes" },
        { label: "No", value: "No" },
      ],
      defaultValue: "No",
    },
    {
      name: "Array",
      type: "select" as const,
      label: "Array",
      options: [
        { label: "Yes", value: "Yes" },
        { label: "No", value: "No" },
      ],
      defaultValue: "No",
    },
    { name: "Notes", type: "text" as const, label: "Notes" },
    {
      name: "Contributor",
      type: "text" as const,
      label: "Contributor",
      defaultValue: model?.Contributor,
    },
    {
      name: "ContributorOrganization",
      type: "text" as const,
      label: "Contributor Organization",
      defaultValue: model?.ContributorOrganization,
    },
    { name: "Tags", type: "text" as const, label: "Tags" },
    {
      name: "ActivationDate",
      type: "datetime-local" as const,
      label: "Activation Date",
      defaultValue: new Date().toISOString().slice(0,16),
    },
    {
      name: "DeprecationDate",
      type: "datetime-local" as const,
      label: "Deprecation Date",
    },
  ];
};

export const attributeCreateFields = (model: any, valueSetId: string | number | null = null): DialogField[] => {
  return [
    {
      name: "DataModelId",
      type: "number" as const,
      label: "DataModelId",
      hidden: true,
      defaultValue: model?.Id,
    },
    {
      name: "ValueSetId",
      type: "number" as const,
      label: "ValueSetId",
      hidden: true,
      defaultValue: valueSetId?.toString(),
    },
    {
      name: "Name",
      type: "text" as const,
      label: "Name",
      required: true,
      pattern: "^[A-Za-z][A-Za-z0-9_]*$",
      patternErr: "Name must start with a letter and contain only letters, numbers, and underscores.",
    },
    {
      name: "UniqueName",
      type: "text" as const,
      label: "Unique Name",
      required: true,
      pattern: "^[A-Za-z][A-Za-z0-9_]*$",
      patternErr: "Unique Name must start with a letter and contain only letters, numbers, and underscores.",
    },
    {
      name: "DataType",
      type: "select" as const,
      label: "Data Type",
      required: true,
      placeholder: "Select a Data Type",
      options: [
        { label: "String", value: "string" },
        { label: "Number", value: "number" },
        { label: "Boolean", value: "boolean" },
        { label: "Date", value: "date" },
        { label: "DateTime", value: "datetime" },
      ],
    },
    { name: "Description", type: "text" as const, label: "Description" },
    {
      name: "Use Considerations",
      type: "text" as const,
      label: "Use Considerations",
    },
    {
      name: "Required",
      type: "select" as const,
      label: "Required",
      options: [
        { label: "Yes", value: "Yes" },
        { label: "No", value: "No" },
      ],
      defaultValue: "No",
    },
    {
      name: "Array",
      type: "select" as const,
      label: "Array",
      options: [
        { label: "Yes", value: "Yes" },
        { label: "No", value: "No" },
      ],
      defaultValue: "No",
    },
    { name: "Notes", type: "text" as const, label: "Notes" },
    {
      name: "Contributor",
      type: "text" as const,
      label: "Contributor",
      defaultValue: model?.Contributor,
    },
    {
      name: "ContributorOrganization",
      type: "text" as const,
      label: "Contributor Organization",
      defaultValue: model?.ContributorOrganization,
    },
    {
      name: "ActivationDate",
      type: "datetime-local" as const,
      label: "Activation Date",
      defaultValue: new Date().toISOString().slice(0,16),
    },
    {
      name: "DeprecationDate",
      type: "datetime-local" as const,
      label: "Deprecation Date",
    },
  ];
};

export const valueSetCreateFields = (model: any): DialogField[] => {
  return [
    {
      name: "DataModelId",
      type: "number" as const,
      label: "DataModelId",
      hidden: true,
      defaultValue: model?.Id,
    },
    {
      name: "Name",
      type: "text" as const,
      label: "Name",
      required: true,
      pattern: "^[A-Za-z][A-Za-z0-9_]*$",
      patternErr: "Name must start with a letter and contain only letters, numbers, and underscores.",
    },
    { name: "Description", type: "text" as const, label: "Description" },
    {
      name: "Use Considerations",
      type: "text" as const,
      label: "Use Considerations",
    },
    { name: "Notes", type: "text" as const, label: "Notes" },
    {
      name: "Contributor",
      type: "text" as const,
      label: "Contributor",
      defaultValue: model?.Contributor,
    },
    {
      name: "ContributorOrganization",
      type: "text" as const,
      label: "Contributor Organization",
      defaultValue: model?.ContributorOrganization,
    },
    { name: "Tags", type: "text" as const, label: "Tags" },
    {
      name: "CreationDate",
      type: "datetime-local" as const,
      label: "Creation Date",
      defaultValue: new Date().toISOString().slice(0,16),
      readOnly: true,
    },
    {
      name: "ActivationDate",
      type: "datetime-local" as const,
      label: "Activation Date",
      defaultValue: new Date().toISOString().slice(0,16),
    },
    {
      name: "DeprecationDate",
      type: "datetime-local" as const,
      label: "Deprecation Date",
    },
  ];
};

export const valueCreateFields = (model: any): DialogField[] => {
  return [
    { name: "Value", type: "text" as const, label: "Value", required: true },
    {
      name: "ValueName",
      type: "text" as const,
      label: "Value Name",
      required: true,
      pattern: "^[A-Za-z][A-Za-z0-9_]*$",
      patternErr: "Value Name must start with a letter and contain only letters, numbers, and underscores.",
    },
    { name: "Description", type: "text" as const, label: "Description" },
    {
      name: "Use Considerations",
      type: "text" as const,
      label: "Use Considerations",
    },
    { name: "Source", type: "text" as const, label: "Source" },
    { name: "Notes", type: "text" as const, label: "Notes" },
    {
      name: "Contributor",
      type: "text" as const,
      label: "Contributor",
      defaultValue: model?.Contributor,
    },
    {
      name: "ContributorOrganization",
      type: "text" as const,
      label: "Contributor Organization",
      defaultValue: model?.ContributorOrganization,
    },
    {
      name: "CreationDate",
      type: "datetime-local" as const,
      label: "Creation Date",
      defaultValue: new Date().toISOString().slice(0,16),
      readOnly: true,
    },
    {
      name: "ActivationDate",
      type: "datetime-local" as const,
      label: "Activation Date",
      defaultValue: new Date().toISOString().slice(0,16),
    },
    {
      name: "DeprecationDate",
      type: "datetime-local" as const,
      label: "Deprecation Date",
    },
  ];
};


const sharedAssociationFields = (model: any): DialogField[] => {
  return [
    { name: "Notes", type: "text" as const, label: "Notes", },
    { name: "Contributor", type: "text" as const, label: "Contributor", defaultValue: model?.Contributor, },
    { name: "ContributorOrganization", type: "text" as const, label: "Contributor Organization", defaultValue: model?.ContributorOrganization, },
    { name: "CreationDate", type: "datetime-local" as const, label: "Creation Date", defaultValue: new Date().toISOString().slice(0,16), readOnly: true, },
    { name: "ActivationDate", type: "datetime-local" as const, label: "Activation Date", defaultValue: new Date().toISOString().slice(0,16), },
    { name: "DeprecationDate", type: "datetime-local" as const, label: "Deprecation Date", },
  ];
};

export const entityAssociationFields = (model: any): DialogField[] => {
  return [
    { name: "Placement", type: "select" as const, label: "Placement",
      options: [
        { label: "Embedded", value: "Embedded" },
        { label: "Reference", value: "Reference" },
      ],
      defaultValue: "Embedded",
      help: "Embedded: Child entity is part of the parent entity. Reference: Child entity exists independently and is linked to the parent.",
    },
    { name: "Relationship", type: "text" as const, label: "Relationship",
      help: "Camel Case descriptor of how the child entity relates to the parent entity. Special triggers: 'has' for ---; 'relevant' for ---.",
    },
    // {
    //   name: "ExtensionNotes",
    //   type: "text" as const,
    //   label: "Extension Notes",
    // },
    ...sharedAssociationFields(model),
  ];
};

export const attributeAssociationFields = (model: any): DialogField[] => {
  return sharedAssociationFields(model);
};


export const inclusionEditFields = (model: any): DialogField[] => {
  const ElementTypes: string[] = ['Attribute', 'Entity', 'Constraint', 'Transformation'];
  const LevelsOfAccess: string[] = ['Private', 'Public', 'Internal', 'Restricted'];
  
  return [
    { name: "LevelOfAccess", type: "select" as const, label: "Level Of Access", required: true,
      placeholder: "Select Level Of Access",
      options: LevelsOfAccess.map((la: any) => ({ label: la, value: la })),
    },
    { name: "Queryable", type: "boolean" as const, label: "Queryable", },
    { name: "Modifiable", type: "boolean" as const, label: "Modifiable", },
    { name: "Notes", type: "text" as const, label: "Notes" },
    { name: "Contributor", type: "text" as const, label: "Contributor", defaultValue: model?.Contributor, },
    { name: "ContributorOrganization", type: "text" as const, label: "Contributor Organization", defaultValue: model?.ContributorOrganization, },
    { name: "ActivationDate", type: "datetime-local" as const, label: "Activation Date", defaultValue: new Date().toISOString().slice(0,16), },
    { name: "DeprecationDate", type: "datetime-local" as const, label: "Deprecation Date", },
  ];
};
