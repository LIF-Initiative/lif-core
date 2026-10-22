import "./LifModel.css";
import DataModelSelector from "@/components/DataModelSelector/DataModelSelector";

const LifModel: React.FC = () => {
  return (
    <DataModelSelector
      // sidebar={<ObjectDetails object={modelDetails} />}
      dataModeltype="LIF"
      routePath="/explore/lif-model/"
    />
  );
};

export default LifModel;
