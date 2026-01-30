import { Button, Dialog, Flex, Select, TextField, Text, AlertDialog, Spinner, Switch } from "@radix-ui/themes";
import { useState, useEffect, useRef } from "react";
import { errorToString } from "../../utils/errorUtils";
// import { tr } from "@faker-js/faker";
// import { on } from "events";
import './Dialog.css';
import { create } from "domain";

const FileDEBUG = false;
const debugLog = (...args: any[]) => { if(FileDEBUG) console.log(...args); };
const reportError = (...args: any[]) => { console.error(...args); };
const PARTNER_MODEL_TYPE = "PartnerLIF";
const SOURCE_MODEL_TYPE = "SourceSchema";
type InputMode = 'text' | 'search' | 'email' | 'tel' | 'url' | 'none' | 'numeric' | 'decimal';

const isFieldHidden = (
  field: DialogField,
  params: Record<string, any>,
  isEditMode: boolean,
): boolean => {
  if (typeof field.hidden === "function") {
    try {
      return field.hidden(params, { isEditMode });
    } catch (error) {
      reportError("Error evaluating field.hidden:", errorToString(error));
      return false;
    }
  }
  return !!field.hidden;
};


export interface DialogField {
  name: string;
  type: "text" | "number" | "datetime-local" | "select" | "file" | "boolean";
  label: string;
  required?: boolean;
  options?: Array<{ label: string; value: string | number }>;
  defaultValue?: string | number | null;
  value?: string | number | null;
  hidden?: boolean | ((params: any, context: { isEditMode: boolean }) => boolean);
  readOnly?: boolean;
  placeholder?: string;
  help?: string; // potential help text
  accept?: string;
  inputMode?: InputMode;
  pattern?: string;
  patternErr?: string;
}

export interface DialogItem {
  Id?: number;
  Name?: string;
  [key: string]: any;
}


// CRUD DIALOG
interface CrudDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  fields: DialogField[];
  isEditMode: boolean;
  itemToEdit: DialogItem | null;
  onCreate?: (params: any) => Promise<void>;
  onEdit?: (id: number, params: any) => Promise<void>;
  onCreateSuccess?: () => Promise<void>;
}

export const CrudDialog: React.FC<CrudDialogProps> = ({
  isOpen,
  onOpenChange,
  title,
  fields,
  isEditMode,
  itemToEdit,
  onCreate,
  onEdit,
  onCreateSuccess,
}) => {
  const [createParams, setCreateParams] = useState<any>({});
  const [createError, setCreateError] = useState<string | null>(null);
  const [requiredFields, setRequiredFields] = useState<string[]>([]);

  const handleFieldValueChange = (field: DialogField, value: any) => {
    setCreateParams((prev: any) => {
      const nextParams = { ...prev, [field.name]: value };
      if (field.name === "Type" && fields.find(f => f.name === 'BaseDataModelId')) {
        if (value === PARTNER_MODEL_TYPE) {
          nextParams.BaseDataModelId = prev.BaseDataModelId || "1";
        } else if (value === SOURCE_MODEL_TYPE) {
          nextParams.BaseDataModelId = null;
        }
      }
      // # Disabled pattern validation here; now handled on handleCreateOrEdit
      // if (field.pattern && createParams[field.name] && !new RegExp(field.pattern).test(createParams[field.name])) {
      //   setCreateError(`The following fields have invalid values:\n > ${field.patternErr}`);
      // }
      return nextParams;
    });
  };

  const crudDialogRef = useRef<HTMLDivElement>(null);
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  useEffect(() => {
    if (!crudDialogRef?.current) return;
    else crudDialogRef.current.scrollTo({ top: 0, behavior: "smooth" });
  }, [createError]);

  const [disableSubmitData, setDisableSubmitData] = useState<boolean>(true);
  const [disableSubmitForm, setDisableSubmitForm] = useState<boolean>(true);
  const handleCreateOrEdit = async () => {
    const missingFields = requiredFields.filter((f) => !createParams[f]);
    if (missingFields.length) {
      setCreateError(`Please complete all required fields: ${missingFields.join(", ")}`);
      return;
    }

    const regexFields = fields.filter((f) => f.pattern && createParams[f.name] && !new RegExp(f.pattern).test(createParams[f.name]));
    if (regexFields.length) {
      setCreateError(`The following fields have invalid values:\n > ${regexFields.map(f => f.patternErr).join("\n > ")}`);
      return;
    }
  
    setDisableSubmitForm(true);
    if (isEditMode && itemToEdit) {
      try {
        const updatePayload: any = {};
        Object.keys(createParams).forEach((key) => {
          const originalValue = itemToEdit[key];
          const newValue = createParams[key];
          if (newValue !== originalValue) { updatePayload[key] = newValue; }
        });
        fields.filter((f) => isFieldHidden(f, createParams, isEditMode)).forEach((f) => {
          updatePayload[f.name] = f.defaultValue;
        });
        fields.filter((f) => f.type === "datetime-local" && updatePayload[f.name] === "").forEach((f) => {
          updatePayload[f.name] = null;
        });
        if (Object.keys(updatePayload).length > 0 && onEdit) {
          debugLog("onEdit:", itemToEdit.Id!, updatePayload);
          delete updatePayload["CreationDate"]; // do not allow editing CreationDate
          await onEdit(itemToEdit.Id!, updatePayload);
        }
        onOpenChange(false);
      } catch (error) {
        const err = errorToString(error);
        reportError("Error editing item:", err);
        setCreateError(`Server error editing item. Error: ${err}`);
      }
    } else {
      try {
        if (onCreate) {
          await onCreate(createParams);
          onOpenChange(false);
          setCreateParams({});
          if (onCreateSuccess) { await onCreateSuccess(); }
        }
      } catch (error) {
        const err = errorToString(error);
        reportError("Error creating item:", err);
        setCreateError(`Server error creating item. Error: ${err}`);
      }
    }
    setDisableSubmitForm(false);
  };

  const setFieldChecks = () => {
    const reqFields = fields.filter(f => f.required).map(f => f.name);
    debugLog("Required fields:", reqFields);
    setRequiredFields(reqFields);

    if (!isEditMode) {
      const params: any = {};
      fields.forEach((field) => {
        if (field.defaultValue) {
          params[field.name] = field.defaultValue;
        } else if (field.type === "datetime-local" && ['CreationDate', 'ActivationDate'].includes(field.name)) {
          const date = new Date();
          params[field.name] = date.toISOString().slice(0, 16);
        } else if (field.type === 'boolean') {
          params[field.name] = false; // not-null prevention
        }
      });
      debugLog("setFieldChecks() createParams:", params);
      setCreateParams(params);
    }
  };


  useEffect(() => {
    if (isEditMode && itemToEdit) {
      const params: any = {};
      fields.forEach((field) => {
        if (field.type === "datetime-local") {
          const utcDate = itemToEdit[field.name] || field.defaultValue || null;
          if (utcDate) {
            const date = new Date(utcDate as string);
            params[field.name] = date.toISOString().slice(0, 16);
          }
        } else if (field.type === 'boolean') { // not-null prevention
          params[field.name] = !!itemToEdit[field.name] || field.defaultValue || false;
        } else {
          params[field.name] = itemToEdit[field.name] || field.defaultValue || null;
        }
      });
      setCreateParams(params);
    } else if (isOpen) {
      // Run setFieldChecks when dialog opens for creation
      setFieldChecks();
    } else if (!isOpen) {
      setCreateParams({});
      setRequiredFields([]);
      setCreateError(null);
    }
    setDisableSubmitData(false);
    setDisableSubmitForm(false);
  }, [isEditMode, itemToEdit, fields, isOpen]);

  useEffect(() => {
    const missingFields = requiredFields.filter((f) => !createParams[f]);
    setDisableSubmitData(missingFields.length > 0);
  }, [createParams, requiredFields]);

  return (
    <Dialog.Root open={isOpen} onOpenChange={onOpenChange}>
      <Dialog.Content className="dialogCRUD" style={{ maxHeight: "88vh", overflowY: "auto"}}  ref={crudDialogRef}>
        <Dialog.Title>
          {isEditMode
            ? `Editing ${itemToEdit?.Name}`
            : `Create New ${title}`}
        </Dialog.Title>
        <Dialog.Description size="2" mb="4">
          {isEditMode
            ? `Update ${itemToEdit?.Name}'s details`
            : `Add a new ${title?.toLowerCase()} to the system.`
          }
          {createError && (
            <>
              <br /><br />
              <Text color="red" size="2" mb="3" style={{ whiteSpace: "pre-line" }}>
                {createError}
              </Text>
            </>
          )}
        </Dialog.Description>
        

        <Flex direction="column" gap="3">
          {fields
            .filter((field) => !isFieldHidden(field, createParams, isEditMode))
            .map((field) => (
              <label key={field.name}>
                <Text as="div" size="2" mb="1" weight="bold" className={`${field.required ? ('required' + (createParams[field.name] ? '' : '-missing')) : ''}`}>
                  {field.label}
                </Text>
                {field.type === "select" && (
                  <Select.Root
                    value={createParams[field.name] ?? field.defaultValue ?? ""}
                    onValueChange={(value) => handleFieldValueChange(field, value)}
                  >
                    <Select.Trigger placeholder={field.placeholder} />
                    <Select.Content>
                      {field.options?.map((option) => (
                        <Select.Item key={option.value} value={String(option.value)}>
                          {option.label}
                        </Select.Item>
                      ))}
                    </Select.Content>
                  </Select.Root>
                )}
                {field.type === "boolean" && (
                  <Switch
                    checked={createParams[field.name] || field.defaultValue || false}
                    onCheckedChange={(v) => handleFieldValueChange(field, v)}
                  />
                )}
                {field.type === "file" && (
                  <div className="file-upload">
                    <input type="file" className="file-upload__input"
                      ref={(element) => { fileInputRefs.current[field.name] = element; }}
                      id={`file-input-${field.name}`}
                      accept={field.accept}
                      onChange={(e) => {
                        const file = e.target.files?.[0] ?? null;
                        handleFieldValueChange(field, file);
                      }}
                    />
                    <Button type="button"
                      onClick={() => fileInputRefs.current[field.name]?.click()}
                    >
                      {createParams[field.name] ? "Change file" : "Choose file"}
                    </Button>
                    {createParams[field.name] && (
                      <Text size="1" color="gray" className="file-upload__filename">
                        {createParams[field.name] instanceof File
                          ? createParams[field.name].name
                          : String(createParams[field.name])}
                      </Text>
                    )}
                  </div>
                )}
                {(field.type === "text" || field.type === "number" || field.type === "datetime-local") && (
                  <TextField.Root
                    type={field.type}
                    value={createParams[field.name] ?? field.defaultValue ?? ""}
                    placeholder={`Enter ${field.label.toLowerCase()}`}
                    onChange={(e) => handleFieldValueChange(field, e.target.value) }
                    inputMode={field.inputMode}
                    pattern={field.pattern}
                    title={field.patternErr ?? ""}
                    readOnly={field.readOnly || (isEditMode && field.name === "CreationDate")}
                  />
                )}
              </label>
            ))}
        </Flex>

        <Flex gap="3" mt="4" justify="end">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Cancel
            </Button>
          </Dialog.Close>
          <Button onClick={handleCreateOrEdit} disabled={disableSubmitData || disableSubmitForm}>
            {disableSubmitForm ? (<Spinner />) : (isEditMode ? "Save" : "Create")}
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};


// DELETE DIALOG
interface DeleteDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  message?: string;
  onConfirm: () => Promise<void>;
}

export const DeleteDialog: React.FC<DeleteDialogProps> = ({
  isOpen,
  onClose,
  title,
  message,
  onConfirm,
}) => {
  const handleDelete = async () => {
    try {
      await onConfirm();
      onClose();
    } catch (error) {
      const err = errorToString(error);
      reportError("Error deleting item:", err);
    }
  };

  return (
    <AlertDialog.Root open={isOpen} onOpenChange={() => onClose()}>
      <AlertDialog.Content className="dialogDelete" style={{ maxWidth: "450px" }}>
        <AlertDialog.Title>{title || "Delete Item"}</AlertDialog.Title>
        <AlertDialog.Description size="2">
          {message || "Are you sure you want to delete this item?"}
          <br/><br/>This action cannot be undone.
        </AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray">Cancel</Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button variant="solid" color="red" onClick={handleDelete}>Yes, I'm sure</Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};


// SIMPLE ALERT DIALOG
interface SimpleAlertDialogProps {
  title: string;
  message: string;
  isOpen: boolean;
  onClose: () => void;
};

export const SimpleAlertDialog: React.FC<SimpleAlertDialogProps> = ({
  title,
  message,
  isOpen,
  onClose,
}) => {
  const handleOK = async () => { onClose(); };
  return (
    <AlertDialog.Root open={isOpen} onOpenChange={() => onClose()}>
      <AlertDialog.Content className="dialogAlert" style={{ maxWidth: "450px" }}>
        <AlertDialog.Title>{title}</AlertDialog.Title>
        <AlertDialog.Description size="2">{message}</AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Action>
            <Button variant="solid" color="green" onClick={handleOK}>OK</Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
};


// SELECT DIALOG
interface SelectDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  type: string;
  itemList: any[];
  itemToEdit: DialogItem;
  fields: DialogField[];
  onEdit: (id: number, selected: any, params: any) => Promise<void>;
}

export const SelectDialog: React.FC<SelectDialogProps> = ({
  isOpen,
  onOpenChange,
  type,
  itemList,
  itemToEdit,
  fields,
  onEdit,
}) => {
  const [createParams, setCreateParams] = useState<any>({});
  const [itemSelected, setItemSelected] = useState<any>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<boolean>(false);
  const [disableSubmitForm, setDisableSubmitForm] = useState<boolean>(true);

  const updateCreateParams = (key: string, value: any) => {
    setCreateParams((prev: any) => ({ ...prev, [key]: value, }));
  };

  const selectDialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!triggerError || !selectDialogRef?.current) return;
    selectDialogRef.current.scrollTo({ top: 0, behavior: "smooth" });
    setTriggerError(false);
  }, [formError, triggerError]);

  const handleEdit = async () => {
    setDisableSubmitForm(true);
    if (!itemSelected) {
      setFormError(`Please select an item to proceed.`);
      setTriggerError(true);
    } else {
      try {
        debugLog("onEdit:", itemToEdit.Id!, itemSelected, createParams);
        await onEdit(itemToEdit.Id!, itemSelected, createParams);
        onOpenChange(false);
      } catch (error) {
        const err = errorToString(error);
        reportError("Error editing item:", err);
        setFormError(`Server error editing item. Error: ${err}`);
        setTriggerError(true);
      }
    }
    setDisableSubmitForm(false);
  };

  useEffect(() => {
    if (itemToEdit && fields) { // on dialog open, set intial values
      const params: any = {};
      fields.forEach((field: any) => { params[field.name] = field.defaultValue || null; });
      setCreateParams(params);
    } else if (!isOpen) { // on dialog close, reset values
      setCreateParams({});
      setFormError(null);
      setItemSelected(null);
      setDisableSubmitForm(false);
    }
  }, [itemToEdit, fields, isOpen]);

  return (
    <Dialog.Root open={isOpen} onOpenChange={onOpenChange}>
      <Dialog.Content className="dialogSelect" style={{ maxHeight: "88vh", overflowY: "auto"}}  ref={selectDialogRef}>
        <Dialog.Title>
          Update {itemToEdit?.Name}
        </Dialog.Title>
        <Dialog.Description size="2" mb="4">
          Select the {type} to associate with {itemToEdit?.Name}.
          {formError && (<><br /><br /><Text color="red" size="2" mb="3">{formError}</Text></>)}
        </Dialog.Description>
        
        <Flex direction="column" gap="3">
          <label key="select-item-label">
            <Text as="div" size="2" mb="1" weight="bold" className={'required'}>
              {type} Selection
            </Text>
            <Select.Root
              value={itemSelected ?? ""}
              onValueChange={(value) => setItemSelected(value)}
            >
              <Select.Trigger placeholder={`Select ${type}`} />
              <Select.Content>
              {itemList?.map((opt) => (
                <Select.Item key={opt.Id} value={opt.Id}>
                  {opt.Name}{opt.UniqueName ? ` (${opt.UniqueName})` : ''} - Id#{opt.Id}
                </Select.Item>
              ))}
              </Select.Content>
            </Select.Root>
          </label>
          {fields
            .filter((field) => !field.hidden)
            .map((field) => (
              <label key={field.name}>
                <Text as="div" size="2" mb="1" weight="bold" className={`${field.required ? ('required' + (createParams[field.name] ? '' : '-missing')) : ''}`}>
                  {field.label}
                </Text>
                {field.type === "select" && (
                  <Select.Root
                    value={createParams[field.name] ?? field.defaultValue ?? ""}
                    onValueChange={(value) => updateCreateParams(field.name, value)}
                  >
                    <Select.Trigger placeholder={field.placeholder} />
                    <Select.Content>
                      {field.options?.map((option) => (
                        <Select.Item key={option.value} value={String(option.value)}>
                          {option.label}
                        </Select.Item>
                      ))}
                    </Select.Content>
                  </Select.Root>
                )}
                {field.type === "boolean" && (
                  <Switch
                    checked={createParams[field.name] || field.defaultValue || false}
                    onCheckedChange={(v) => updateCreateParams(field.name, v)}
                  />
                )}
                {(field.type === "text" || field.type === "number" || field.type === "datetime-local") && (
                  <TextField.Root type="text"
                    value={createParams[field.name] ?? field.defaultValue ?? ""}
                    placeholder={`Enter ${field.label.toLowerCase()}`}
                    onChange={(e) => updateCreateParams(field.name, e.target.value) }
                  />
                )}
              </label>
            ))}
        </Flex>

        <Flex gap="3" mt="4" justify="end">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Cancel
            </Button>
          </Dialog.Close>
          <Button onClick={handleEdit} disabled={!itemSelected || disableSubmitForm}>
            {disableSubmitForm ? (<Spinner />) : "Save"}
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};


export default { CrudDialog, DeleteDialog, SimpleAlertDialog, SelectDialog };
