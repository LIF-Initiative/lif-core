import DataModelSelector from "@/components/DataModelSelector/DataModelSelector";

const DataExtensions: React.FC = () => {
  return (
    <DataModelSelector
      // listTitle="Organization's LIF"
      dataModeltype="OrgLIF"
      routePath="/explore/data-extensions/"
    />
  );
};

export default DataExtensions;
