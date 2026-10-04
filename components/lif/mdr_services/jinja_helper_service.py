import json
import re
from typing import List

from lif.mdr_sql_model.core import DataModel, Entity, EntityPlacementType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import pandas as pd
from lif.mdr_utils.logger_config import get_logger


logger = get_logger(__name__)


async def get_all_entity_data_frame(session: AsyncSession):
    entity_query = select(Entity.Id, Entity.Name).where(Entity.Deleted == False)
    execution = await session.execute(entity_query)
    result = execution.fetchall()
    column_names = result[0]._fields if result else []
    df_entity = pd.DataFrame(result, columns=column_names)
    return df_entity


async def get_complete_entity_tree(rows, df_entity, distinctEntityIds: List[int] = None):
    tree = {}
    top_level_parents = []
    parent_id_list = []
    child_id_list = []
    for row in rows:
        parent = row[0]
        child = row[1]
        if parent not in parent_id_list:
            parent_id_list.append(parent)
        if distinctEntityIds and child in distinctEntityIds:
            if child not in child_id_list:
                child_id_list.append(child)
            if parent in tree:
                tree[parent].append(child)
            else:
                tree[parent] = [child]
        if not distinctEntityIds:
            if child not in child_id_list:
                child_id_list.append(child)
            if parent in tree:
                tree[parent].append(child)
            else:
                tree[parent] = [child]

    top_level_parents = [p for p in parent_id_list if p not in child_id_list]

    logger.info(f"tree : {tree}")
    logger.info(f"parent_id_list : {parent_id_list}")
    logger.info(f"child_id_list : {child_id_list}")
    logger.info(f"top_level_parents : {top_level_parents}")

    tree_with_entity_names = {}
    for parent, child_list in tree.items():
        parent_entity_name = (df_entity[df_entity["Id"] == parent])["Name"].unique().tolist()[0]
        # logger.info(f"parent_entity_name : {parent_entity_name}")
        if isinstance(child_list, list) and len(child_list) > 0:
            tree_with_entity_names[parent_entity_name] = []
            for child_entity_id in child_list:
                child_entity_name = (df_entity[df_entity["Id"] == child_entity_id])["Name"].unique().tolist()[0]
                # logger.info(f"child_entity_name : {child_entity_name}")
                tree_with_entity_names[parent_entity_name].append(child_entity_name)
    logger.info(f"tree_with_entity_names : {tree_with_entity_names}")

    top_level_entity_names = []
    for entity_id in top_level_parents:
        parent_entity_name = (df_entity[df_entity["Id"] == entity_id])["Name"].unique().tolist()[0]
        top_level_entity_names.append(parent_entity_name)
    logger.info(f"top_level_entity_names : {top_level_entity_names}")

    return tree, parent_id_list, child_id_list, top_level_parents, tree_with_entity_names, top_level_entity_names


async def extend_subtree(main_tree, initial_subtree, entities):
    # Create a reverse mapping from child to parent
    parent_map = {}
    for parent, children in main_tree.items():
        for child in children:
            parent_map[child] = parent

    # Function to add parent and filtered children to the subtree
    def add_to_subtree(subtree, node):
        if node in parent_map:
            parent = parent_map[node]
            if parent not in subtree:
                # Filter children to only include those in the entities list
                filtered_children = [child for child in main_tree[parent] if child in entities]
                subtree[parent] = filtered_children

    # Extend the subtree
    for entity in entities:
        add_to_subtree(initial_subtree, entity)

    return initial_subtree


async def get_data_model_id_by_name_and_version(session: AsyncSession, name: str, version: str) -> int:
    query = select(DataModel.Id).where(
        DataModel.Name == name, DataModel.DataModelVersion == version, DataModel.Deleted == False
    )
    result = await session.execute(query)
    data_model_id = result.scalar()

    return data_model_id


async def find_ancestors(tree, child, inter_entity_placement=None):
    logger.info(" ########## in find_ancestors ########## ")
    # Create a reverse mapping from child to parent
    parent_map = {}
    for parent, children in tree.items():
        logger.info(f"parent: {parent}")
        logger.info(f"children: {children}")
        for c in children:
            if inter_entity_placement:
                if c in inter_entity_placement:
                    if (
                        inter_entity_placement[c]["ParentEntityId"] == parent
                        and inter_entity_placement[c]["Placement"] == EntityPlacementType.Reference
                    ):
                        # If the child is a reference in parent then do not put that child in parent map.
                        continue
            parent_map[c] = parent

    logger.info(f"parent_map: {parent_map}")
    # List to store the ancestors
    ancestors = []

    # Trace back from the child to the root, collecting ancestors
    while child in parent_map:
        parent = parent_map[child]
        ancestors.append(parent)
        child = parent
    # logger.info(f"Ancestors before reverse {ancestors}")

    # Reversing list to get the main root entity as the first element and so on..
    ancestors.reverse()

    # logger.info(f"Ancestors after reverse {ancestors}")

    return ancestors


# async def create_entity_v2(entity_id, children=None):
#     entity = {
#         "id": entity_id,
#         "type": "Entity",
#         "obj_type": "array",
#         "data_model": "LIF",
#         "attributes": []
#     }
#     if children:
#         entity["children"] = children
#     return entity

# # Recursive function to build the tree structure
# async def build_tree(tree, root):
#     if root not in tree:
#         return await create_entity_v2(root)

#     children = [await build_tree(tree, child) for child in tree[root]]
#     return await create_entity_v2(root, children)


async def create_entity_v2(entity_id, children=None, parent=None, inter_entity_placement=None):
    logger.info("In create_entity_v2 ")
    logger.info(f"entity_id : {entity_id}")
    logger.info(f"children : {children}")
    logger.info(f"inter_entity_placement : {inter_entity_placement}")

    entity = {
        "id": entity_id,
        "type": "Entity",
        "target_entity_obj_type": "array",
        "data_model": "LIF",
        "attributes": [],
        "children": [],
    }
    if children:
        entity["children"] = children

    if inter_entity_placement and entity_id in inter_entity_placement:
        if inter_entity_placement[entity_id]["ParentEntityId"] == parent:
            logger.info("Entity is in placement list..")
            entity["Relationship"] = inter_entity_placement[entity_id]["Relationship"]
            entity["Placement"] = inter_entity_placement[entity_id]["Placement"]

    return entity


# Recursive function to build the tree structure
async def build_tree(tree, root, parent=None, inter_entity_placement=None):
    logger.info(" In build_tree ------")
    logger.info(f"tree : {tree}")
    logger.info(f"root : {root}")
    logger.info(f"inter_entity_placement : {inter_entity_placement}")
    if root not in tree:
        return await create_entity_v2(root, parent=parent, inter_entity_placement=inter_entity_placement)

    # children =[]
    # for child in tree[root]:
    #     if inter_entity_placement and root in inter_entity_placement:
    #         if child == inter_entity_placement[root]["ChildEntityId"]:
    #             children.append(build_tree(tree, child, inter_entity_placement[root]))
    #     else:
    #         children.append(build_tree(tree, child))

    children = [await build_tree(tree, child, root, inter_entity_placement) for child in tree[root]]
    return await create_entity_v2(root, children, parent=parent, inter_entity_placement=inter_entity_placement)


async def create_get_mapping_v3(
    mapping_json,
    target_entity_id,
    target_expression,
    target_attribute_name,
    source_attribute_name,
    source_entity_name,
    tree_for_target_df,
    target_attribute_data_type,
    is_target_attribute_array,
    is_target_entity_array,
    source_attribute_data_type,
    is_source_attribute_array,
    is_source_entity_array,
    inter_entity_placement,
):
    logger.info(" ... In create_get_mapping_v3 ...")
    logger.info(f"target_entity_id : {target_entity_id}")
    # logger.info(f"mapping_json : {mapping_json}")
    logger.info(f"target_attribute_name : {source_attribute_name}")
    # logger.info(f"source_entity_name : {source_entity_name}")

    logger.info(f"source_attribute_name : {source_attribute_name}")
    logger.info(f"source_entity_name : {source_entity_name}")
    ancestors = await find_ancestors(
        tree_for_target_df, target_entity_id, inter_entity_placement=inter_entity_placement
    )
    logger.info(f"ancestors : {ancestors}")
    if len(ancestors) > 0:
        # For child entities
        ancestors.append(target_entity_id)  # appending target_entity_id to get the final JSON
        logger.info(f" updated ancestors : {ancestors}")
        target_json = mapping_json[ancestors[0]]
        target_found = False
        if len(ancestors) > 1:
            for ancestor in ancestors:
                logger.info(f"ancestor : {ancestor}")
                for child in target_json["children"]:
                    if child["id"] == ancestor:
                        target_json = child
                        target_found = True
                        break
    else:
        # For root level entity
        target_json = mapping_json[target_entity_id]

    logger.info(f"target_json : {target_json}")

    target_attribute_json = None
    target_attribute_found = False
    for attribute in target_json["attributes"]:
        for key, value_dict in attribute.items():
            if target_attribute_name == key:
                target_attribute_json = value_dict
                target_attribute_found = True

    if not target_attribute_found:
        attribute_json = {}
        attribute_json[target_attribute_name] = []
        target_json["attributes"].append(attribute_json)
        target_attribute_json = attribute_json[target_attribute_name]

    source_mapping_data = {}
    # source_mapping_data[target_attribute_name] = {}

    # Assuming : default attribute object type is array for target
    if not is_target_attribute_array or is_target_attribute_array == "Yes":
        source_mapping_data["target_attribute_obj_type"] = "array"
    else:
        source_mapping_data["target_attribute_obj_type"] = "object"

    # Assuming : default attribute data type as string for target
    if target_attribute_data_type:
        source_mapping_data["target_attribute_data_type"] = target_attribute_data_type
    else:
        source_mapping_data["target_attribute_data_type"] = "xsd:string"

    # Assuming : default attribute object type is array for source
    if not is_source_attribute_array or is_source_attribute_array == "Yes":
        source_mapping_data["source_attribute_obj_type"] = "array"
    else:
        source_mapping_data["source_attribute_obj_type"] = "object"

    # Assuming : default attribute data type as string for source
    if source_attribute_data_type:
        source_mapping_data["source_attribute_data_type"] = source_attribute_data_type
    else:
        source_mapping_data["source_attribute_data_type"] = "xsd:string"

    # Assuming : default entity object type is array for source
    if not is_source_entity_array or is_source_entity_array == "Yes":
        source_mapping_data["source_entity_obj_type"] = "array"
    else:
        source_mapping_data["source_entity_obj_type"] = "object"

    source_mapping_data["source_entity"] = source_entity_name
    source_mapping_data["source_attribute"] = source_attribute_name
    source_mapping_data["expression"] = target_expression

    logger.info(f"source_mapping_data : {source_mapping_data}")

    target_attribute_json.append(source_mapping_data)
    # target_json['attributes'].append(target_attribute_json)

    # Assuming : default entity object type is array
    if not is_target_entity_array or is_target_entity_array == "Yes":
        target_json["target_entity_obj_type"] = "array"
    else:
        target_json["target_entity_obj_type"] = "Object"


async def create_children_jinja(child_json, sources_dict, jinja_dict, df_entity, first_level=False):
    logger.info(" ..... In create_children_jinja_v2 .... ")
    logger.info(f"child_json : {child_json}")
    logger.info(f"sources_dict : {sources_dict}")
    logger.info(f"jinja_dict : {jinja_dict}")
    # logger.info(f"parent_table_details : {parent_table_details}")
    # logger.info(f"tree_for_target_df : {tree_for_target_df}")
    # logger.info(f"jinja_dict : {jinja_dict}")

    # if parent_entity_name in tree_with_entity_names:
    #     for child_entity_name in tree_with_entity_names[parent_entity_name]:
    data_type = child_json["target_entity_obj_type"]
    child_entity_name = (df_entity[df_entity["Id"] == child_json["id"]])["Name"].unique().tolist()[0]
    logger.info(f"child_entity_name : {child_entity_name}")
    if "Relationship" in child_json:
        child_entity_name = child_json["Relationship"] + child_entity_name

    if isinstance(jinja_dict, list):
        dict_data = jinja_dict[0]
    else:
        dict_data = jinja_dict
    if not first_level:
        if data_type == "array":
            dict_data[child_entity_name] = []
            obj = {}
        else:
            dict_data[child_entity_name] = {}

    logger.info(f"dict_data : {dict_data}")
    # if "Placement" in child_json and child_json['Placement'] == 'Reference':
    #     logger.info("This is reference..")
    #     return sources_dict

    for attribute in child_json["attributes"]:
        logger.info(f"attribute : {attribute}")
        for target_attribute_name, attribute_mapping_list in attribute.items():
            multi_value_map = False
            if len(attribute_mapping_list) > 1:
                target_attribute_obj_type = "array"
                array_value = []
                multi_value_map = True
            #     "Identifier": [
            #     {
            #       "identifier": "{{credentialSubject.achievement.creator.id}}"
            #     }{% if credentialSubject.achievement.creator.otherIdentifier != None and credentialSubject.achievement.creator.otherIdentifier.identifier != None %},{% endif %}
            #     {% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}
            #     {
            #       "identifier": "{{otherIdentifier.identifier}}",
            #       "identifierType": "{{otherIdentifier.identifierType}}"
            #     }{% if not loop.last %},{% endif %}
            #     {% endfor %}
            #   ],
            for index, attribute_mapping in enumerate(attribute_mapping_list):
                logger.info(f"target_attribute_name : {target_attribute_name}")
                logger.info(f"attribute_mapping : {attribute_mapping}")
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                # check if

                if source_entity not in sources_dict:
                    sources_dict[source_entity] = f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
                # source_value = source_entity+"."+ re.sub(r'[.\n: ]', '', source_attribute)
                source_value = await create_attribute_jinja(
                    attribute_mapping=attribute_mapping, target_attribute_name=target_attribute_name
                )
                if multi_value_map:
                    if index == 0:
                        multi_mapping_template = f"{{{target_attribute_name}:{source_value}}}"
                    else:
                        multi_mapping_template = (
                            f'{{% if {source_entity} != None and {source_attribute} != None %}},{{% endif %}}{{% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}} \
                                                    {{"{target_attribute_name}": "{{{{{source_value}}}}}" \
                                                    }}{{% if not loop.last %}},{{% endif %}}{{% endfor %}}'
                        )
                    array_value.append(multi_mapping_template)

            if multi_value_map:
                source_value = array_value
            if first_level:
                dict_data[target_attribute_name] = source_value
            else:
                if data_type == "array":
                    obj[target_attribute_name] = source_value
                else:
                    dict_data[child_entity_name][target_attribute_name] = source_value
    if data_type == "array" and not first_level:
        dict_data[child_entity_name].append(obj)

    if "Placement" in child_json and child_json["Placement"] == "Reference":
        logger.info("This is reference..")
        return sources_dict

    if "children" in child_json:
        logger.info("Children")
        for child in child_json["children"]:
            if not first_level:
                await create_children_jinja(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=dict_data[child_entity_name],
                    df_entity=df_entity,
                    first_level=False,
                )
            else:
                await create_children_jinja(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=jinja_dict,
                    df_entity=df_entity,
                    first_level=False,
                )

    logger.info(f"jinja_dict (final) : {jinja_dict}")
    return sources_dict


# async def handle_multi_mapping():
#     multi_mapping_template = f'{{% if {source_entity_name} != None and {source_attribute_name} != None %}},{{% endif %}}{{% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}} \
#                 {{"{target_attribute_name}": "{{{{{source_attribute_name}}}}}"
#                 }}{{% if not loop.last %}},{{% endif %}}{{% endfor %}}'


async def jinja_creation(top_level_json, visited_dict_add_columns, visited_dict_keep_column, df_entity):
    logger.info("  ********* In jinja_creation_v6 ************")
    logger.info(f"top_level_json : {top_level_json}")
    logger.info(f"visited_dict_add_columns : {visited_dict_add_columns}")
    logger.info(f"visited_dict_keep_column : {visited_dict_keep_column}")

    parent_data_type = top_level_json["target_entity_obj_type"]

    # Adding all direct attributes as a columns in jinja for child entity (1st layer after the root)
    for attribute in top_level_json["attributes"]:
        # logger.info(f"source : {source}")
        for target_attribute_name, attribute_mapping_list in attribute.items():
            # logger.info(f"source_entity : {source_entity}")
            # logger.info(f"attribute_mapping : {attribute_mapping}")
            for attribute_mapping in attribute_mapping_list:
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                # source_value = source_entity+"."+ re.sub(r'[.\n: ]', '', source_attribute)
                source_value = await create_attribute_jinja(
                    attribute_mapping=attribute_mapping, target_attribute_name=target_attribute_name
                )
                sub_jinja = "  {% raw %}\n"
                # TODO : need to add code to check attribute type and create jinja based on that. Right now ww are assuming this as an array.
                sub_jinja += "  [ {\n"
                sub_jinja += f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
                sub_jinja += f'      "{target_attribute_name}": "{source_value}"\n'
                sub_jinja += "  } ]\n"
                sub_jinja += "  {% endraw %}"
                visited_dict_add_columns[target_attribute_name] = sub_jinja
                visited_dict_keep_column.append(target_attribute_name)

    # adding all children (immediate children to root) as a column in jinja
    if "children" in top_level_json:
        for child in top_level_json["children"]:
            sources_dict = {}
            jinja_dict = {}
            child_entity_name = (df_entity[df_entity["Id"] == child["id"]])["Name"].unique().tolist()[0]
            logger.info(f"child_entity_name : {child_entity_name}")
            data_type = child["target_entity_obj_type"]
            template_str_part_1 = "  {% raw %}\n"
            if data_type == "array":
                template_str_part_1 += "  [ {\n"
            else:
                template_str_part_1 += "  {\n"

            await create_children_jinja(
                child_json=child,
                sources_dict=sources_dict,
                jinja_dict=jinja_dict,
                df_entity=df_entity,
                first_level=True,
            )

            for source, jinja_str in sources_dict.items():
                template_str_part_1 += jinja_str

            if data_type == "array":
                template_str_part_2 = "  } ]\n"
            else:
                template_str_part_2 = "  }\n"
            template_str_part_2 += "  {% endraw %}"

            # jinja_string_part = yaml.dump(jinja_dict, default_flow_style=False).strip('{}')
            # final_jinja_str = template_str_part_1 + jinja_string_part + template_str_part_2
            final_jinja_str = template_str_part_1 + json.dumps(jinja_dict, indent=4).strip("{}") + template_str_part_2

            logger.info(f"final_jinja_str : {final_jinja_str}")
            visited_dict_add_columns[child_entity_name] = final_jinja_str
            visited_dict_keep_column.append(child_entity_name)


async def create_attribute_jinja(attribute_mapping: dict, target_attribute_name: str):
    logger.info(" ~~~~~~~~~ Creating attribute jinja ~~~~~~~~~~ ")
    source_entity = attribute_mapping["source_entity"]
    source_entity_obj_type = attribute_mapping["source_entity_obj_type"]

    source_attribute = attribute_mapping["source_attribute"]
    source_attribute_obj_type = attribute_mapping["source_attribute_obj_type"]
    source_attribute_data_type = attribute_mapping["source_attribute_data_type"]

    target_attribute_obj_type = attribute_mapping["target_attribute_obj_type"]
    target_attribute_data_type = attribute_mapping["target_attribute_data_type"]

    expression = attribute_mapping["expression"]

    logger.info(f"source_entity : {source_entity}")
    logger.info(f"source_entity_obj_type : {source_entity_obj_type}")
    logger.info(f"source_attribute : {source_attribute}")
    logger.info(f"source_attribute_obj_type : {source_attribute_obj_type}")
    logger.info(f"source_attribute_data_type : {source_attribute_data_type}")
    logger.info(f"target_attribute_obj_type : {target_attribute_obj_type}")
    logger.info(f"target_attribute_data_type : {target_attribute_data_type}")
    logger.info(f"expression : {expression}")

    source_value = ""
    if target_attribute_obj_type == "array" and source_attribute_obj_type == "array":
        logger.info("Both source and target attribute are arrays..")
        if "=" in expression or "get" in expression or "addAll" in expression:
            loop_value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
            source_value = "  [\n"
            source_value += f"    {{% for {target_attribute_name} in {loop_value} %}}\n"
            # Use the correct placement for the double curly braces and quotes
            source_value += f'    "{{{{{target_attribute_name}}}}}"{{% if not loop.last %}},{{% endif %}}\n'
            source_value += "    {% endfor %}\n"
            source_value += "  ]\n"

            # source_value =f'''{{% for {target_attribute_name} in {loop_value} %}}"{{{{{target_attribute_name}}}}}"{{% if not loop.last %}},{{% endif %}}{{% endfor %}}'''

    if target_attribute_obj_type == "object" and source_attribute_obj_type == "array":
        logger.info("Target is object and source is array")
        # TODO: Convert target to array, now just sending entity.attribute as return value
        value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
        source_value = f"{{{{{value}}}}}"

    if target_attribute_obj_type == "array" and source_attribute_obj_type == "object":
        logger.info("Target is array and source is object")
        # TODO: Target array with one object, now just sending entity.attribute as return value
        value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
        source_value = f"{{{{{value}}}}}"

    if target_attribute_obj_type == "object" and source_attribute_obj_type == "object":
        logger.info("Both source and target attribute are objects..")
        if "=" in expression or "get" in expression:
            value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
            source_value = f"{{{{{value}}}}}"
    logger.info(f"source_value : {source_value}")
    logger.info(" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ")
    return source_value


async def get_base_model_ids(session: AsyncSession, data_model_id: int):
    # Initialize the list with the given extension model id
    base_model_ids = [data_model_id]

    # Start with the given extension model ID
    current_model_id = data_model_id

    while current_model_id:
        # Query to get the BaseDataModelId for the current model
        query = select(DataModel.BaseDataModelId).where(DataModel.Id == current_model_id)
        result = await session.execute(query)
        base_data_model_id = result.scalar()

        # If there is a base model, add it to the list and continue
        if base_data_model_id:
            base_model_ids.append(base_data_model_id)
            current_model_id = base_data_model_id  # Set the current model ID to the base model ID
        else:
            break  # No more base models

    return base_model_ids


async def update_schema_for_lif_1(
    session: AsyncSession, tree_for_target_df, child_id_list_for_target_df, parent_id_list_for_target_df, lif_v1_Id
):
    # This means our target is LIF 1.0
    # Getting Person entity id
    query = select(Entity.Id).where(Entity.Name == "Person", Entity.DataModelId == lif_v1_Id, Entity.Deleted == False)
    result = await session.execute(query)
    person_lif_v1_Id = result.scalar()
    logger.info(f"person_lif_v1_Id: {person_lif_v1_Id}")

    # Getting CompetencyFramework entity id
    query = select(Entity.Id).where(
        Entity.Name == "CompetencyFramework", Entity.DataModelId == lif_v1_Id, Entity.Deleted == False
    )
    result = await session.execute(query)
    competency_framework_lif_v1_Id = result.scalar()
    logger.info(f"person_lif_v1_Id: {person_lif_v1_Id}")
    logger.info(f"competency_framework_lif_v1_Id : {competency_framework_lif_v1_Id}")

    if person_lif_v1_Id in tree_for_target_df.keys():
        for parent, child_list in tree_for_target_df.items():
            if (
                parent != person_lif_v1_Id
                and parent != competency_framework_lif_v1_Id
                and parent not in child_id_list_for_target_df
            ):
                tree_for_target_df[person_lif_v1_Id].append(parent)
    else:
        tree_for_target_df[person_lif_v1_Id] = []
        for parent, child_list in tree_for_target_df.items():
            if parent != competency_framework_lif_v1_Id and parent not in child_id_list_for_target_df:
                tree_for_target_df[person_lif_v1_Id].append(parent)
    logger.info(f"\n  +++++++++++++++++++++ tree_for_target_df : {tree_for_target_df} --- \n")
    for parent, child_list in tree_for_target_df.items():
        if parent not in parent_id_list_for_target_df:
            parent_id_list_for_target_df.append(parent)
        for child in child_list:
            if child not in child_id_list_for_target_df:
                child_id_list_for_target_df.append(child)
    logger.info(f"\n --- UPDATED parent_id_list_for_target_df : {parent_id_list_for_target_df} --- \n")
    logger.info(f"\n ---UPDATED child_id_list_for_target_df : {child_id_list_for_target_df} --- \n")


async def update_mapping_json_for_reference(inter_entity_placement, tree_for_target_df, mapping_json):
    # This is the code to copy all the attribute to where this entity is being referenced
    for child_entity_id, data in inter_entity_placement.items():
        # if data["Placement"] and data["Placement"] == 'Reference':
        if data["Placement"]:
            # This reference so adding it to top most parent - in LIF
            ancestor_list = await find_ancestors(
                tree_for_target_df, child_entity_id, inter_entity_placement=inter_entity_placement
            )
            logger.info(f"child_entity_id: {child_entity_id}")
            logger.info(f"placement is reference : ancestor list {ancestor_list}")

            attribute_data_to_copy = None
            children_data_to_copy = None
            if len(ancestor_list) > 0:
                if ancestor_list[0] == data["ParentEntityId"]:
                    # If only ancestor is the current parent then create entity at the root level
                    # tree_for_target_df[child_entity_id]=[]
                    attribute_data_to_copy = mapping_json[child_entity_id]["attributes"]
                    if data["Placement"] == EntityPlacementType.Embedded:
                        children_data_to_copy = mapping_json[child_entity_id]["children"]

                else:
                    # tree_for_target_df[ancestor_list[0]].append(child_entity_id)
                    for child in mapping_json[ancestor_list[0]]["children"]:
                        if child["id"] == child_entity_id:
                            attribute_data_to_copy = child["attributes"]
                            if data["Placement"] == EntityPlacementType.Embedded:
                                children_data_to_copy = child["children"]

            logger.info(f"data_to_copy: {attribute_data_to_copy}")
            if attribute_data_to_copy:
                logger.info(f"parent_entity_id: {data['ParentEntityId']}")
                ancestor_for_parent_id = await find_ancestors(tree_for_target_df, data["ParentEntityId"])
                logger.info(f"ancestor_for_parent_id: {ancestor_for_parent_id}")
                ancestor_for_parent_id.append(data["ParentEntityId"])
                # Adding child entity id to get the final JSON and confirm the child is there in
                ancestor_for_parent_id.append(child_entity_id)
                logger.info(f" final ancestor_for_parent_id: {ancestor_for_parent_id}")
                target_json = mapping_json[ancestor_for_parent_id[0]]
                target_found = False
                for ancestor in ancestor_for_parent_id[1:]:
                    logger.info(f"ancestor:{ancestor}")
                    for child in target_json["children"]:
                        if ancestor == child["id"]:
                            logger.info(f"child['id']:{child['id']}")
                            target_json = child
                            break
                    if ancestor == child_entity_id:
                        logger.info("Target found")
                        target_found = True
                logger.info(f"target_found : {target_found}")

                if target_found:
                    logger.info(f"Target Json found : {target_json}")
                    target_json["attributes"] = attribute_data_to_copy
                    if data["Placement"] == EntityPlacementType.Embedded:
                        target_json["children"] = children_data_to_copy


async def create_children_jinja_v2(child_json, sources_dict, jinja_dict, df_entity, first_level=False):
    logger.info(" ..... In create_children_jinja_v2 .... ")
    logger.info(f"child_json : {child_json}")
    logger.info(f"sources_dict : {sources_dict}")
    logger.info(f"jinja_dict : {jinja_dict}")
    # logger.info(f"parent_table_details : {parent_table_details}")
    # logger.info(f"tree_for_target_df : {tree_for_target_df}")
    # logger.info(f"jinja_dict : {jinja_dict}")

    # if parent_entity_name in tree_with_entity_names:
    #     for child_entity_name in tree_with_entity_names[parent_entity_name]:
    data_type = child_json["target_entity_obj_type"]
    child_entity_name = (df_entity[df_entity["Id"] == child_json["id"]])["Name"].unique().tolist()[0]
    logger.info(f"child_entity_name : {child_entity_name}")
    if "Relationship" in child_json:
        child_entity_name = child_json["Relationship"] + child_entity_name

    if isinstance(jinja_dict, list):
        dict_data = jinja_dict[0]
    else:
        dict_data = jinja_dict
    if not first_level:
        if data_type == "array":
            dict_data[child_entity_name] = []
            obj = {}
        else:
            dict_data[child_entity_name] = {}

    logger.info(f"dict_data : {dict_data}")
    # if "Placement" in child_json and child_json['Placement'] == 'Reference':
    #     logger.info("This is reference..")
    #     return sources_dict

    for attribute in child_json["attributes"]:
        logger.info(f"attribute : {attribute}")
        jinja_template = ""
        multi_map = False
        for target_attribute_name, attribute_mapping_list in attribute.items():
            if len(attribute_mapping_list) > 1:
                target_attribute_obj_type = "array"
                array_value = []
                multi_map = True
            #     "Identifier": [
            #     {
            #       "identifier": "{{credentialSubject.achievement.creator.id}}"
            #     }{% if credentialSubject.achievement.creator.otherIdentifier != None and credentialSubject.achievement.creator.otherIdentifier.identifier != None %},{% endif %}
            #     {% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}
            #     {
            #       "identifier": "{{otherIdentifier.identifier}}",
            #       "identifierType": "{{otherIdentifier.identifierType}}"
            #     }{% if not loop.last %},{% endif %}
            #     {% endfor %}
            #   ],
            for attribute_mapping in attribute_mapping_list:
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                source_entity_obj_type = attribute_mapping["source_entity_obj_type"]
                # Handle if source entity is object or array
                if source_entity_obj_type == "object":
                    # Add single object handling
                    jinja_template += f"{{{{ {source_entity}.{source_attribute} }}}}\n"
                elif source_entity_obj_type == "array":
                    # Add array handling with for loop
                    jinja_template += f"{{% if {source_entity} != None and {source_entity}.{source_attribute} != None %}},{{% endif %}}\n"
                    jinja_template += (
                        f"{{% for {source_entity} in credentialSubject.achievement.creator.otherIdentifier %}}\n"
                    )
                    jinja_template += f"{{{{ {source_entity}.{source_attribute} }}}}\n"
                    jinja_template += "{% if not loop.last %},{% endif %}\n"
                    jinja_template += "{% endfor %}\n"
                if multi_map:
                    obj = {target_attribute_name: jinja_template}
                    array_value.append(jinja_template)
            if multi_map:
                logger.info(f"array_value : {array_value}")
            if first_level:
                if multi_map:
                    dict_data[target_attribute_name] = array_value
                else:
                    dict_data[target_attribute_name] = jinja_template
            else:
                if data_type == "array":
                    if multi_map:
                        obj[target_attribute_name] = array_value
                    else:
                        obj[target_attribute_name] = jinja_template
                else:
                    if multi_map:
                        dict_data[child_entity_name][target_attribute_name] = array_value
                    else:
                        dict_data[child_entity_name][target_attribute_name] = jinja_template
    if data_type == "array" and not first_level:
        dict_data[child_entity_name].append(obj)

    if "Placement" in child_json and child_json["Placement"] == "Reference":
        logger.info("This is reference..")
        return sources_dict

    if "children" in child_json:
        logger.info("Children")
        for child in child_json["children"]:
            if not first_level:
                await create_children_jinja_v2(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=dict_data[child_entity_name],
                    df_entity=df_entity,
                    first_level=False,
                )
            else:
                await create_children_jinja_v2(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=jinja_dict,
                    df_entity=df_entity,
                    first_level=False,
                )

    logger.info(f"jinja_dict (final) : {jinja_dict}")
    return sources_dict


async def jinja_creation_v2(top_level_json, visited_dict_add_columns, visited_dict_keep_column, df_entity):
    logger.info("  ********* In jinja_creation_v6 ************")
    logger.info(f"top_level_json : {top_level_json}")
    logger.info(f"visited_dict_add_columns : {visited_dict_add_columns}")
    logger.info(f"visited_dict_keep_column : {visited_dict_keep_column}")

    parent_data_type = top_level_json["target_entity_obj_type"]

    # Adding all direct attributes as a columns in jinja for child entity (1st layer after the root)
    for attribute in top_level_json["attributes"]:
        # logger.info(f"source : {source}")
        for target_attribute_name, attribute_mapping_list in attribute.items():
            # logger.info(f"source_entity : {source_entity}")
            # logger.info(f"attribute_mapping : {attribute_mapping}")
            for attribute_mapping in attribute_mapping_list:
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                # source_value = source_entity+"."+ re.sub(r'[.\n: ]', '', source_attribute)
                source_value = await create_attribute_jinja(
                    attribute_mapping=attribute_mapping, target_attribute_name=target_attribute_name
                )
                sub_jinja = "  {% raw %}\n"
                # TODO : need to add code to check attribute type and create jinja based on that. Right now ww are assuming this as an array.
                sub_jinja += "  [ {\n"
                sub_jinja += f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
                sub_jinja += f'      "{target_attribute_name}": "{source_value}"\n'
                sub_jinja += "  } ]\n"
                sub_jinja += "  {% endraw %}"
                visited_dict_add_columns[target_attribute_name] = sub_jinja
                visited_dict_keep_column.append(target_attribute_name)

    # adding all children (immediate children to root) as a column in jinja
    if "children" in top_level_json:
        for child in top_level_json["children"]:
            sources_dict = {}
            jinja_dict = {}
            child_entity_name = (df_entity[df_entity["Id"] == child["id"]])["Name"].unique().tolist()[0]
            logger.info(f"child_entity_name : {child_entity_name}")
            data_type = child["target_entity_obj_type"]
            template_str_part_1 = "  {% raw %}\n"
            if data_type == "array":
                template_str_part_1 += "  [ {\n"
            else:
                template_str_part_1 += "  {\n"

            await create_children_jinja_v2(
                child_json=child,
                sources_dict=sources_dict,
                jinja_dict=jinja_dict,
                df_entity=df_entity,
                first_level=True,
            )

            for source, jinja_str in sources_dict.items():
                template_str_part_1 += jinja_str

            if data_type == "array":
                template_str_part_2 = "  } ]\n"
            else:
                template_str_part_2 = "  }\n"
            template_str_part_2 += "  {% endraw %}"

            # jinja_string_part = yaml.dump(jinja_dict, default_flow_style=False).strip('{}')
            # final_jinja_str = template_str_part_1 + jinja_string_part + template_str_part_2
            final_jinja_str = template_str_part_1 + json.dumps(jinja_dict, indent=4).strip("{}") + template_str_part_2

            logger.info(f"final_jinja_str : {final_jinja_str}")
            visited_dict_add_columns[child_entity_name] = final_jinja_str
            visited_dict_keep_column.append(child_entity_name)


async def create_children_jinja_v3(child_json, sources_dict, jinja_dict, df_entity, first_level=False):
    logger.info(" ..... In create_children_jinja_v2 .... ")
    logger.info(f"child_json : {child_json}")
    logger.info(f"sources_dict : {sources_dict}")
    logger.info(f"jinja_dict : {jinja_dict}")
    # logger.info(f"parent_table_details : {parent_table_details}")
    # logger.info(f"tree_for_target_df : {tree_for_target_df}")
    # logger.info(f"jinja_dict : {jinja_dict}")

    # if parent_entity_name in tree_with_entity_names:
    #     for child_entity_name in tree_with_entity_names[parent_entity_name]:
    data_type = child_json["target_entity_obj_type"]
    child_entity_name = (df_entity[df_entity["Id"] == child_json["id"]])["Name"].unique().tolist()[0]
    logger.info(f"child_entity_name : {child_entity_name}")
    if "Relationship" in child_json:
        child_entity_name = child_json["Relationship"] + child_entity_name

    if isinstance(jinja_dict, list):
        dict_data = jinja_dict[0]
    else:
        dict_data = jinja_dict
    if not first_level:
        if data_type == "array":
            dict_data[child_entity_name] = []
            obj = {}
        else:
            dict_data[child_entity_name] = {}

    logger.info(f"dict_data : {dict_data}")
    # if "Placement" in child_json and child_json['Placement'] == 'Reference':
    #     logger.info("This is reference..")
    #     return sources_dict

    for attribute in child_json["attributes"]:
        logger.info(f"attribute : {attribute}")
        for target_attribute_name, attribute_mapping_list in attribute.items():
            multi_value_map = False
            if len(attribute_mapping_list) > 1:
                target_attribute_obj_type = "array"
                array_value = []
                multi_value_map = True
            #     "Identifier": [
            #     {
            #       "identifier": "{{credentialSubject.achievement.creator.id}}"
            #     }{% if credentialSubject.achievement.creator.otherIdentifier != None and credentialSubject.achievement.creator.otherIdentifier.identifier != None %},{% endif %}
            #     {% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}
            #     {
            #       "identifier": "{{otherIdentifier.identifier}}",
            #       "identifierType": "{{otherIdentifier.identifierType}}"
            #     }{% if not loop.last %},{% endif %}
            #     {% endfor %}
            #   ],
            for index, attribute_mapping in enumerate(attribute_mapping_list):
                logger.info(f"target_attribute_name : {target_attribute_name}")
                logger.info(f"attribute_mapping : {attribute_mapping}")
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                # check if

                if source_entity not in sources_dict:
                    sources_dict[source_entity] = f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
                # source_value = source_entity+"."+ re.sub(r'[.\n: ]', '', source_attribute)
                source_value = await create_attribute_jinja(
                    attribute_mapping=attribute_mapping, target_attribute_name=target_attribute_name
                )
                if multi_value_map:
                    if index == 0:
                        multi_mapping_template = f"{{{target_attribute_name}:{source_value}}}"
                    else:
                        multi_mapping_template = (
                            f'{{% if {source_entity} != None and {source_attribute} != None %}},{{% endif %}}{{% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}} \
                                                    {{"{target_attribute_name}": "{{{{{source_value}}}}}" \
                                                    }}{{% if not loop.last %}},{{% endif %}}{{% endfor %}}'
                        )
                    array_value.append(multi_mapping_template)

            if multi_value_map:
                source_value = array_value
            if first_level:
                dict_data[target_attribute_name] = source_value
            else:
                if data_type == "array":
                    obj[target_attribute_name] = source_value
                else:
                    dict_data[child_entity_name][target_attribute_name] = source_value
    if data_type == "array" and not first_level:
        dict_data[child_entity_name].append(obj)

    if "Placement" in child_json and child_json["Placement"] == "Reference":
        logger.info("This is reference..")
        return sources_dict

    if "children" in child_json:
        logger.info("Children")
        for child in child_json["children"]:
            if not first_level:
                await create_children_jinja(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=dict_data[child_entity_name],
                    df_entity=df_entity,
                    first_level=False,
                )
            else:
                await create_children_jinja(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=jinja_dict,
                    df_entity=df_entity,
                    first_level=False,
                )

    logger.info(f"jinja_dict (final) : {jinja_dict}")
    return sources_dict


# async def handle_multi_mapping():
#     multi_mapping_template = f'{{% if {source_entity_name} != None and {source_attribute_name} != None %}},{{% endif %}}{{% for otherIdentifier in credentialSubject.achievement.creator.otherIdentifier %}} \
#                 {{"{target_attribute_name}": "{{{{{source_attribute_name}}}}}"
#                 }}{{% if not loop.last %}},{{% endif %}}{{% endfor %}}'


async def jinja_creation_v3(top_level_json, visited_dict_add_columns, visited_dict_keep_column, df_entity):
    logger.info("  ********* In jinja_creation_v6 ************")
    logger.info(f"top_level_json : {top_level_json}")
    logger.info(f"visited_dict_add_columns : {visited_dict_add_columns}")
    logger.info(f"visited_dict_keep_column : {visited_dict_keep_column}")

    target_entity_obj_type = top_level_json["target_entity_obj_type"]

    # Adding all direct attributes as a columns in jinja for child entity (1st layer after the root)
    for attribute in top_level_json["attributes"]:
        # logger.info(f"source : {source}")
        await create_attribute_jinja_v3(attribute=attribute, target_entity_obj_type=target_entity_obj_type)
        # for target_attribute_name, attribute_mapping_list in attribute.items():
        #     # logger.info(f"source_entity : {source_entity}")
        #     # logger.info(f"attribute_mapping : {attribute_mapping}")
        #     for attribute_mapping in attribute_mapping_list:
        #         source_entity = attribute_mapping["source_entity"]
        #         source_attribute = attribute_mapping["source_attribute"]
        #         # source_value = source_entity+"."+ re.sub(r'[.\n: ]', '', source_attribute)
        #         source_value = await create_attribute_jinja(attribute_mapping=attribute_mapping, target_attribute_name=target_attribute_name)
        #         sub_jinja = '  {% raw %}\n'
        #         # TODO : need to add code to check attribute type and create jinja based on that. Right now ww are assuming this as an array.
        #         sub_jinja += '  [ {\n'
        #         sub_jinja += f'    {{% set {source_entity} = fromjson({source_entity}) %}}\n'
        #         sub_jinja += f'      "{target_attribute_name}": "{source_value}"\n'
        #         sub_jinja += '  } ]\n'
        #         sub_jinja += '  {% endraw %}'
        #         visited_dict_add_columns[target_attribute_name] = sub_jinja
        #         visited_dict_keep_column.append(target_attribute_name)

    # adding all children (immediate children to root) as a column in jinja
    if "children" in top_level_json:
        for child in top_level_json["children"]:
            sources_dict = {}
            jinja_dict = {}
            child_entity_name = (df_entity[df_entity["Id"] == child["id"]])["Name"].unique().tolist()[0]
            logger.info(f"child_entity_name : {child_entity_name}")
            data_type = child["target_entity_obj_type"]
            template_str_part_1 = "  {% raw %}\n"
            if data_type == "array":
                template_str_part_1 += "  [ {\n"
            else:
                template_str_part_1 += "  {\n"

            await create_children_jinja(
                child_json=child,
                sources_dict=sources_dict,
                jinja_dict=jinja_dict,
                df_entity=df_entity,
                first_level=True,
            )

            for source, jinja_str in sources_dict.items():
                template_str_part_1 += jinja_str

            if data_type == "array":
                template_str_part_2 = "  } ]\n"
            else:
                template_str_part_2 = "  }\n"
            template_str_part_2 += "  {% endraw %}"

            # jinja_string_part = yaml.dump(jinja_dict, default_flow_style=False).strip('{}')
            # final_jinja_str = template_str_part_1 + jinja_string_part + template_str_part_2
            final_jinja_str = template_str_part_1 + json.dumps(jinja_dict, indent=4).strip("{}") + template_str_part_2

            logger.info(f"final_jinja_str : {final_jinja_str}")
            visited_dict_add_columns[child_entity_name] = final_jinja_str
            visited_dict_keep_column.append(child_entity_name)


async def create_attribute_jinja_v3(attribute: dict, target_entity_obj_type: str):
    logger.info(" ~~~~~~~~~ Creating attribute jinja ~~~~~~~~~~ ")

    for target_attribute_name, attribute_mapping_list in attribute.items():
        # logger.info(f"source_entity : {source_entity}")
        # logger.info(f"attribute_mapping : {attribute_mapping}")
        for attribute_mapping in attribute_mapping_list:
            source_entity = attribute_mapping["source_entity"]
            source_attribute = attribute_mapping["source_attribute"]
            # source_value = source_entity+"."+ re.sub(r'[.\n: ]', '', source_attribute)
            source_value = await create_attribute_jinja(
                attribute_mapping=attribute_mapping, target_attribute_name=target_attribute_name
            )
            sub_jinja = "  {% raw %}\n"
            # TODO : need to add code to check attribute type and create jinja based on that. Right now ww are assuming this as an array.
            sub_jinja += "  [ {\n"
            sub_jinja += f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
            sub_jinja += f'      "{target_attribute_name}": "{source_value}"\n'
            sub_jinja += "  } ]\n"
            sub_jinja += "  {% endraw %}"
            # visited_dict_add_columns is not defined, but the calling method is not referenced anywhere.
            visited_dict_add_columns[target_attribute_name] = sub_jinja  # noqa: F821
            visited_dict_keep_column.append(target_attribute_name)  # noqa: F821

    source_entity = attribute_mapping["source_entity"]
    source_entity_obj_type = attribute_mapping["source_entity_obj_type"]

    source_attribute = attribute_mapping["source_attribute"]
    source_attribute_obj_type = attribute_mapping["source_attribute_obj_type"]
    source_attribute_data_type = attribute_mapping["source_attribute_data_type"]

    target_attribute_obj_type = attribute_mapping["target_attribute_obj_type"]
    target_attribute_data_type = attribute_mapping["target_attribute_data_type"]

    expression = attribute_mapping["expression"]

    logger.info(f"source_entity : {source_entity}")
    logger.info(f"source_entity_obj_type : {source_entity_obj_type}")
    logger.info(f"source_attribute : {source_attribute}")
    logger.info(f"source_attribute_obj_type : {source_attribute_obj_type}")
    logger.info(f"source_attribute_data_type : {source_attribute_data_type}")
    logger.info(f"target_attribute_obj_type : {target_attribute_obj_type}")
    logger.info(f"target_attribute_data_type : {target_attribute_data_type}")
    logger.info(f"expression : {expression}")

    source_value = ""
    if target_attribute_obj_type == "array" and source_attribute_obj_type == "array":
        logger.info("Both source and target attribute are arrays..")
        if "=" in expression or "get" in expression or "addAll" in expression:
            loop_value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
            source_value = "  [\n"
            source_value += f"    {{% for {target_attribute_name} in {loop_value} %}}\n"
            # Use the correct placement for the double curly braces and quotes
            source_value += f'    "{{{{{target_attribute_name}}}}}"{{% if not loop.last %}},{{% endif %}}\n'
            source_value += "    {% endfor %}\n"
            source_value += "  ]\n"

            # source_value =f'''{{% for {target_attribute_name} in {loop_value} %}}"{{{{{target_attribute_name}}}}}"{{% if not loop.last %}},{{% endif %}}{{% endfor %}}'''

    if target_attribute_obj_type == "object" and source_attribute_obj_type == "array":
        logger.info("Target is object and source is array")
        # TODO: Convert target to array, now just sending entity.attribute as return value
        value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
        source_value = f"{{{{{value}}}}}"

    if target_attribute_obj_type == "array" and source_attribute_obj_type == "object":
        logger.info("Target is array and source is object")
        # TODO: Target array with one object, now just sending entity.attribute as return value
        value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
        source_value = f"{{{{{value}}}}}"

    if target_attribute_obj_type == "object" and source_attribute_obj_type == "object":
        logger.info("Both source and target attribute are objects..")
        if "=" in expression or "get" in expression:
            value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
            source_value = f"{{{{{value}}}}}"
    logger.info(f"source_value : {source_value}")
    logger.info(" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ")
    return source_value
