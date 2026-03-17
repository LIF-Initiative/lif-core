import React from 'react';

interface FileInputProps {
  id: string;
  label?: string;
  description?: string;
  placeholder?: string;
  accept?: string;
  disabled?: boolean;
  onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
}

const FileInput: React.FC<FileInputProps> = ({
  id,
  label,
  description,
  placeholder = "Choose a file…",
  accept,
  disabled = false,
  onChange,
}) => {
  return (
    <div className="file-input">
      {label && (<>        
          <label htmlFor={id} className="file-input__label">{label}</label>{" "}
      </>)}
      <input
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={onChange}
        className="file-input__input"
        placeholder={placeholder}
      />
      {description && (<>
        <br/>
        <div className="file-input__description">{description}</div>
      </>)}
    </div>
  );
};

export default FileInput;