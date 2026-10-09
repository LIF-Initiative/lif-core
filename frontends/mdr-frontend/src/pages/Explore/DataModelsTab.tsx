import DataModelSelector from "@/components/DataModelSelector/DataModelSelector";

const DataModelsTab: React.FC = () => {
  return (
    <DataModelSelector
      dataModeltype="DataModel"
      routePath="/explore/data-models/"
    />
  );
};

export default DataModelsTab;
