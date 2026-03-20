import React, { useCallback, useEffect, useState } from "react";
import { Box, Card, Flex, Separator, Text } from "@radix-ui/themes";
import { useNavigate, useSearchParams } from "react-router-dom";
import { searchAll } from "../../services/searchService";
import { getAttributeEntityAssociationsByAttr } from "../../services/attributesService";
import { trackEvent } from "../../utils/analytics";

const ExploreSearch: React.FC = () => {
    const [params] = useSearchParams();
    const [searchResults, setSearchResults] = useState<any>(null);
    const navigate = useNavigate();

    const fetchSearchResults = async (keyword: string) => {
        trackEvent('search_performed', { search_term: keyword });
        const results = await searchAll(keyword);
        console.log("results", results);
        setSearchResults(results);
    };

    useEffect(() => {
        console.log("params", params);
    }, [params]);

    useEffect(() => {
        if (params.has("keyword")) {
            fetchSearchResults(params.get("keyword") as string);
        }
    }, [params]);

    const handleItemClick = useCallback(async (itemType: string, item: any) => {
        // deep link to the item
        switch(itemType) {
            case "DataModel":{
                if(item.Id === 1) {
                    navigate(`/explore/lif-model`);
                    return;
                }    
                navigate(`/explore/data-models/${item.Id}`);
                break;
            }
            case "Attribute":{
                if(item.ValueSetId) {
                    if(item.DataModelId === 1) {
                        navigate(`/explore/lif-model/value-sets/${item.ValueSetId}/attributes/${item.Id}`);
                        return;
                    }
                    navigate(`/explore/data-models/${item.DataModelId}/value-sets/${item.ValueSetId}/attributes/${item.Id}`);
                } else {
                    // will not have a entity id, pick the first one
                    const associations = await getAttributeEntityAssociationsByAttr(item.Id, false, 1, 10, item.DataModelId);
                    if (associations?.length) {
                        const EntityId = associations[0].EntityId;
                        if(item.DataModelId === 1) {
                            navigate(`/explore/lif-model/entities/${EntityId}`);/* /attributes/${item.Id} */
                            return;
                        }
                        navigate(`/explore/data-models/${item.DataModelId}/entities/${EntityId}`);/* /attributes/${item.Id} */
                        return;
                    }
                    // otherwise there is some kind of critical error
                    console.error("No entity associations found for attribute, deep link failed!", item);
                }
                break;
            }
            case "Entity":{
                if(item.DataModelId === 1) {
                    navigate(`/explore/lif-model/entities/${item.Id}`);
                    return;
                }
                navigate(`/explore/data-models/${item.DataModelId}/entities/${item.Id}`);
                break;
            }
            case "ValueSet":{
                if(item.DataModelId === 1) {
                    navigate(`/explore/lif-model/value-sets/${item.Id}`);
                    return;
                }
                navigate(`/explore/data-models/${item.DataModelId}/value-sets/${item.Id}`);
                break;
            }
            case "ValueSetValue":{
                if(item.DataModelId === 1) {
                    navigate(`/explore/lif-model/value-sets/${item.ValueSetId}/values/${item.Id}`);
                    return;
                }
                navigate(`/explore/data-models/${item.DataModelId}/value-sets/${item.ValueSetId}/values/${item.Id}`);
                break;
            }
            case "TransformationGroup":
                navigate(`/explore/data-mappings/${item.Id}`);
                break;
            case "Transformation":
                navigate(`/explore/data-mappings/${item.TransformationGroupId}`);
                break;
            default:
                break;
        }
    }, [navigate]);

    return (
        <Flex direction="column" gap="2" className="page" style={{ overflowY: "scroll" }}>
            <Flex justify="center" flexGrow="1">
                <Box>
                    <Text as="div" size="4" style={{fontWeight: "bold"}}>Search Results</Text>
                </Box>
            </Flex>
            <Box>
                <Text as="div" size="2">Data Models ({searchResults?.data_models?.length ?? 0}):</Text>
            </Box>
            {searchResults?.data_models?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No data models found.</Text>
                </Box>
            )}
            {searchResults?.data_models?.map((dataModel: any) => (
                <Box key={dataModel.Id}>
                    <Card onClick={() => handleItemClick("DataModel", dataModel)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Name:</Text>
                            <Text as="div" size="2">{dataModel.Name}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Description:</Text>
                            <Text as="div" size="2">{dataModel.Description ?? "No Description Given."}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
            <Separator orientation="horizontal" size="4" />
            <Box>
                <Text as="div" size="2">Attributes ({searchResults?.attributes?.length ?? 0}):</Text>
            </Box>
            {searchResults?.attributes?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No attributes found.</Text>
                </Box>
            )}
            {searchResults?.attributes?.map((attribute: any) => (
                <Box key={attribute.Id}>
                    <Card onClick={() => handleItemClick("Attribute", attribute)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Name:</Text>
                            <Text as="div" size="2">{attribute.Name}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Description:</Text>
                            <Text as="div" size="2">{attribute.Description ?? "No Description Given."}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
            <Separator orientation="horizontal" size="4" />
            <Box>
                <Text as="div" size="2">Entities ({searchResults?.entities?.length ?? 0}):</Text>
            </Box>
            {searchResults?.entities?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No entities found.</Text>
                </Box>
            )}
            {searchResults?.entities?.map((entity: any) => (
                <Box key={entity.Id}>
                    <Card onClick={() => handleItemClick("Entity", entity)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Name:</Text>
                            <Text as="div" size="2">{entity.Name}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Description:</Text>
                            <Text as="div" size="2">{entity.Description ?? "No Description Given."}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
            <Separator orientation="horizontal" size="4" />
            <Box>
                <Text as="div" size="2">Value Sets ({searchResults?.value_sets?.length ?? 0}):</Text>
            </Box>
            {searchResults?.value_sets?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No value sets found.</Text>
                </Box>
            )}
            {searchResults?.value_sets?.map((valueSet: any) => (
                <Box key={valueSet.Id}>
                    <Card onClick={() => handleItemClick("ValueSet", valueSet)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Name:</Text>
                            <Text as="div" size="2">{valueSet.Name}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Description:</Text>
                            <Text as="div" size="2">{valueSet.Description ?? "No Description Given."}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
            <Separator orientation="horizontal" size="4" />
            <Box>
                <Text as="div" size="2">Value Set Values ({searchResults?.value_set_values?.length ?? 0}):</Text>
            </Box>
            {searchResults?.value_set_values?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No value set values found.</Text>
                </Box>
            )}
            {searchResults?.value_set_values?.map((value: any) => (
                <Box key={value.Id}>
                    <Card onClick={() => handleItemClick("ValueSetValue", value)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Value:</Text>
                            <Text as="div" size="2">{value.Value}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Description:</Text>
                            <Text as="div" size="2">{value.Description ?? "No Description Given."}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
            <Separator orientation="horizontal" size="4" />
            <Box>
                <Text as="div" size="2">Mappings ({searchResults?.transformation_groups?.length ?? 0}):</Text>
            </Box>
            {searchResults?.transformation_groups?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No mappings found.</Text>
                </Box>
            )}
            {searchResults?.transformation_groups?.map((mapping: any) => (
                <Box key={mapping.Id}>
                    <Card onClick={() => handleItemClick("TransformationGroup", mapping)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Name:</Text>
                            <Text as="div" size="2">{mapping.Name}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Description:</Text>
                            <Text as="div" size="2">{mapping.Description}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Tags:</Text>
                            <Text as="div" size="2">{mapping.Tags}</Text>
                        </Box>
                        <Box>
                            <Text as="div" size="1" color="gray">Version:</Text>
                            <Text as="div" size="2">{mapping.GroupVersion}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
            <Separator orientation="horizontal" size="4" />
            <Box>
                <Text as="div" size="2">Transformations ({searchResults?.transformations?.length ?? 0}):</Text>
            </Box>
            {searchResults?.transformations?.length === 0 && (
                <Box>
                    <Text as="div" size="1" color="gray">No transformations found.</Text>
                </Box>
            )}
            {searchResults?.transformations?.map((transformation: any) => (
                <Box key={transformation.Id}>
                    <Card onClick={() => handleItemClick("Transformation", transformation)}>
                        <Box>
                            <Text as="div" size="1" color="gray">Name:</Text>
                            <Text as="div" size="2">{transformation.Name}</Text>
                        </Box>
                    </Card>
                </Box>
            ))}
        </Flex>
    );
};

export default ExploreSearch;
